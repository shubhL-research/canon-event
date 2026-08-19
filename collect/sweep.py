"""Drive the collectors, adjudicate what comes back, emit the contract.

WHY THIS FILE EXISTS
--------------------
`adjudicate.py` decides one row. `normalise.py` translates one payload.
`health.py` decides whether to believe any of it. This is the orchestrator that
holds them together and is the only module that shells out to Bright Data.

Keeping the subprocess in exactly one place is what makes the other three
runnable offline from a saved payload, and it is why `verify.sh` needs no
account and no network. The runner is injected for the same reason
`extract/identifier.py` injects its model call: a clean clone must be able to
replay a sweep from disk and get the same rows.

TWO QUERIES PER NOTICE PER ARM, ALWAYS
--------------------------------------
Every recall is searched twice on every arm: once as brand plus model, once as
model alone. This is not redundancy and it is not a retry.

The project cannot measure its own recall directly. We can hand-verify that the
rows we published are right; we cannot know how many live listings we walked
straight past. Two independent query strategies turn that from unknowable into
bounded: Chapman's capture-recapture over which strategy found what puts a FLOOR
under the miss count.

So `found_by_query` must be recorded on every hit — brand_model, model_only, or
both — or the floor cannot be computed at all. A sweep that skips the second
query to save credits does not merely lose rows, it loses the ability to say
anything honest about what it missed. The two strategies share the model token
and are positively correlated, which biases the estimate downward, so the result
is a lower bound on our blindness rather than an estimate of it.

WHY A FAILED ARM IS NOT AN EXCEPTION
------------------------------------
Nothing here raises on a collector failure. A raised exception ends the sweep,
and a sweep that ends early writes a partial file that looks exactly like a
complete one with fewer hazards in it. Every failure becomes a recorded verdict
instead: the arm carries its state, the health file carries the detector that
noticed, and the wall renders black rather than empty.

Standard library only.
"""

import datetime
import json
import subprocess

from . import health
from .adjudicate import RED, WITHHELD, adjudicate
from .normalise import normalise_job

# Query strategies, in the order they are attempted. The names are contract
# values: contract/row.schema.json enumerates found_by_query as brand_model,
# model_only or both, and stats/recapture.py reads exactly these.
BRAND_MODEL = "brand_model"
MODEL_ONLY = "model_only"

# Per-arm search URL templates. `{q}` is the URL-encoded query. Held here rather
# than in a config file because the arm-to-storefront mapping is a claim the
# project makes on screen and should be visible in the diff when it changes.
ARM_SEARCH = {
    "DE": "https://www.kaufland.de/s/?search_value={q}",
    "US": "https://www.amazon.com/s?k={q}",
    "IN": "https://www.amazon.in/s?k={q}",
}


def cli_runner(collector_id, url, timeout_s=900):
    """Run one collector against one URL through the Bright Data CLI.

    Returns (payload, error). Never raises on a collector failure: a sweep that
    dies on one bad arm writes a partial file indistinguishable from a complete
    one, which is the failure mode this whole project is about.
    """
    cmd = ["npx", "-p", "@brightdata/cli", "bdata", "scraper", "run",
           collector_id, url, "--json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return None, "cli timeout after %ds" % timeout_s
    except OSError as exc:
        return None, "cli not runnable: %s" % exc

    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "").strip()[:400]
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, "unparseable CLI output: %s" % exc


def query_for(notice, strategy):
    """The search string for one notice under one strategy, or None.

    Returns None when the notice cannot support the strategy, rather than
    falling back to the other one. A silent fallback would record a hit under a
    strategy that never ran, which corrupts the capture-recapture input and so
    corrupts the only floor we have on what we missed.
    """
    model = (notice.get("model") or "").strip()
    name = (notice.get("name") or "").strip()
    if not model:
        return None
    if strategy == MODEL_ONLY:
        return model
    brand = name.split()[0] if name else ""
    return ("%s %s" % (brand, model)).strip() if brand else None


def found_by(hits):
    """Collapse the strategies that hit into the contract's enum."""
    if len(hits) > 1:
        return "both"
    return next(iter(hits)) if hits else None


def sweep_arm(arm, collector_id, notices, runner=cli_runner, captured_at=None,
              search_urls=None):
    """Sweep one arm across every notice, both strategies, and adjudicate.

    Returns (verdicts, report, telemetry). `verdicts` maps a notice ref to its
    best result on this arm, where "best" means RED beats WITHHELD beats
    NOT_FOUND: a product found buyable under either strategy is buyable, and a
    block under either is a reason to doubt the negative.
    """
    captured_at = captured_at or _now_iso()
    urls = search_urls or ARM_SEARCH
    verdicts, reports, errors = {}, [], []

    for notice in notices:
        ref = notice.get("ref")
        for strategy in (BRAND_MODEL, MODEL_ONLY):
            query = query_for(notice, strategy)
            if not query:
                continue
            url = urls[arm].format(q=_quote(query))
            payload, error = runner(collector_id, url)
            if error:
                # A failed fetch is a recorded absence of knowledge, not an
                # absence of hazard. It withholds; it never reports NOT_FOUND.
                errors.append({"ref": ref, "strategy": strategy, "error": error})
                _record(verdicts, ref, {"verdict": WITHHELD, "evidence": None,
                                        "discard": {"code": "blocked",
                                                    "reason": error}}, strategy)
                continue

            listings, report = normalise_job(payload, arm)
            reports.append(report)
            for listing in listings:
                result = adjudicate(notice, listing, arm, captured_at)
                _record(verdicts, ref, result, strategy)

    return verdicts, _merge_reports(arm, reports, errors), {
        "arm": arm,
        "collector_id": collector_id,
        "inputs": len(notices),
        "errors": len(errors),
    }


def _record(verdicts, ref, result, strategy):
    """Keep the strongest verdict per notice, and every strategy that hit it."""
    slot = verdicts.setdefault(ref, {"verdict": None, "evidence": None,
                                     "discards": [], "hits": set()})
    if result.get("discard"):
        slot["discards"].append(result["discard"])
    if result["verdict"] == RED:
        slot["hits"].add(strategy)
    if _rank(result["verdict"]) > _rank(slot["verdict"]):
        slot["verdict"] = result["verdict"]
        slot["evidence"] = result["evidence"]


def _rank(verdict):
    """RED outranks WITHHELD outranks NOT_FOUND outranks nothing.

    WITHHELD sits above NOT_FOUND deliberately. If one strategy was blocked and
    the other found nothing, we do not know whether the product is gone, and the
    honest arm state is the one that says so.
    """
    return {RED: 3, WITHHELD: 2, "NOT_FOUND": 1}.get(verdict, 0)


def _merge_reports(arm, reports, errors):
    """One normaliser report per arm, summed across every query it ran."""
    merged = {
        "arm": arm,
        "rows_in": sum(r["rows_in"] for r in reports),
        "rows_normalised": sum(r["rows_normalised"] for r in reports),
        "with_currency": sum(r["with_currency"] for r in reports),
        "with_buy_label": sum(r["with_buy_label"] for r in reports),
        "with_language": sum(r.get("with_language", 0) for r in reports),
        "repaired_doubles": sum(r.get("repaired_doubles", 0) for r in reports),
        "unmapped_fields": sorted({f for r in reports for f in r["unmapped_fields"]}),
        "wrong_language": sorted({l for r in reports for l in r.get("wrong_language", ())}),
        "fetch_errors": errors,
    }
    return merged


def build_rows(notices, per_arm, captured_at=None):
    """Assemble contract rows from each arm's verdicts.

    A row's tier is RED only if some arm reddened it. Rows nothing found are
    still emitted with their arms recorded, because a recall that no arm could
    find is a measurement result and dropping it would silently shrink the
    denominator under every published proportion.
    """
    captured_at = captured_at or _now_iso()
    rows = []
    for notice in notices:
        ref = notice.get("ref")
        arms, evidence, discards, hits = {}, None, [], set()
        for arm in sorted(per_arm):
            slot = per_arm[arm].get(ref)
            if not slot:
                arms[arm] = "NOT_FOUND"
                continue
            arms[arm] = slot["verdict"] or "NOT_FOUND"
            discards.extend(slot["discards"])
            hits |= slot["hits"]
            if slot["verdict"] == RED and evidence is None:
                evidence = slot["evidence"]

        row = {
            "name": notice.get("name"),
            "hazard": notice.get("hazard"),
            "source": notice.get("source"),
            "days": notice.get("days"),
            "tier": RED if RED in arms.values() else "DISCARDED",
            "arms": arms,
        }
        for key in ("model", "gtin"):
            if notice.get(key):
                row[key] = notice[key]
        fbq = found_by(hits)
        if fbq:
            row["found_by_query"] = fbq
        if evidence:
            row["evidence"] = evidence
        if discards:
            row["discarded"] = discards
        rows.append(row)

    # Rank is assigned after the fact, most-recent hazard first, so the wall's
    # ordering is a property of the data rather than of iteration order.
    rows.sort(key=lambda r: (r["tier"] != RED, r.get("days") or 0))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def run(notices, collectors, runner=cli_runner, previous=None, now=None):
    """One full sweep across every configured arm. Returns (rows, health).

    This is the whole product in one call: search, adjudicate, detect, decide
    what may be said. It writes nothing and prints nothing, so a caller can run
    it against saved payloads in a test.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    captured_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sweep_id = "s_" + now.strftime("%Y-%m-%dT%H:%MZ")

    per_arm, reports, arms = {}, [], {}
    for arm, collector_id in sorted(collectors.items()):
        verdicts, report, telemetry = sweep_arm(
            arm, collector_id, notices, runner=runner, captured_at=captured_at)
        per_arm[arm] = verdicts
        reports.append(report)

        joined = sum(1 for v in verdicts.values() if v["verdict"] in (RED, "NOT_FOUND"))
        returned = sum(1 for v in verdicts.values() if v["verdict"] == RED)
        arms[arm] = dict(
            health.arm_state(arm, returned, telemetry["inputs"],
                             telemetry["errors"], joined),
            rows=returned, fails=telemetry["errors"], inputs=telemetry["inputs"],
            joined=joined, collector_id=collector_id,
        )

    rows = build_rows(notices, per_arm, captured_at)
    doc = health.build(sweep_id, now, arms, rows, reports, previous=previous, now=now)
    return rows, doc


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quote(text):
    """Percent-encode a search term. urllib is stdlib but this keeps the
    dependency surface of the module visible in one line."""
    from urllib.parse import quote_plus
    return quote_plus(text)
