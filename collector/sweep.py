"""Drive the collectors, and assemble three arms into one contract row.

WHY THIS FILE EXISTS
--------------------
`fromstudio.py` speaks Bright Data. `normalize.py` decides RED. `health.py`
decides whether to believe any of it. This is the orchestrator that holds them
together, and the only module in the project that shells out to a network.

Keeping the subprocess in exactly one place is what lets the other three run
offline from a saved payload, and it is why `verify.sh` needs no account and no
connection. The runner is injected for the same reason `extract/identifier.py`
injects its model call: a clean clone must be able to replay a sweep from disk.

WHY THE ARMS ARE COMBINED HERE AND NOT IN normalize.py
------------------------------------------------------
`merge_query_strategies()` collapses rows by recall reference, which is exactly
right for the two query passes and exactly wrong across arms: fed all three at
once it would fold a German verdict and an American one into a single row and
lose the dimension the whole project is built on.

So each arm is normalised on its own, producing its own verdict per notice, and
this module is what widens those into the `arms` object the contract requires.
Each arm's rows never meet another arm's rows until that point.

TWO QUERIES PER NOTICE PER ARM, ALWAYS
--------------------------------------
Every recall is searched twice on every arm: brand plus model, then model alone.
This is not a retry and it is not redundancy.

The project cannot measure its own recall directly. We can hand-verify that the
rows we published are right; we cannot know how many live listings we walked
past. Two independent query strategies turn that from unknowable into bounded,
because Chapman's estimator over which strategy found what puts a FLOOR under
the miss count. A sweep that drops the second query to save credits does not
merely lose rows, it loses the ability to say anything honest about what it
missed, and that cannot be reconstructed afterwards.

WHY A FAILED ARM IS NOT AN EXCEPTION
------------------------------------
Nothing here raises on a collector failure. An exception ends the sweep, and a
sweep that ends early writes a partial file indistinguishable from a complete
one with fewer hazards in it. Every failure becomes a recorded verdict instead:
the arm carries its state, the health file carries the detector that noticed,
and the wall goes black rather than empty.

Standard library only.
"""

import datetime
import json
import pathlib
import subprocess
import sys
from urllib.parse import quote_plus

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import health                                                    # noqa: E402
from fromstudio import convert                                   # noqa: E402
from normalize import normalize_sweep                            # noqa: E402

# Contract values. contract/row.schema.json enumerates found_by_query as
# brand_model, model_only or both, and stats/recapture.py reads exactly these.
BRAND_MODEL = "brand_model"
MODEL_ONLY = "model_only"

# Arm to storefront. Held in code rather than a config file because the mapping
# is a claim the project makes on screen, and it should be visible in the diff
# on the day it changes.
ARM_SEARCH = {
    "DE": "https://www.kaufland.de/s/?search_value={q}",
    "US": "https://www.amazon.com/s?k={q}",
    "IN": "https://www.amazon.in/s?k={q}",
}

# Row tier to the verdict the wall renders for that arm. The distinction that
# matters is DISCARDED splitting two ways: a blocked fetch is our own failure and
# withholds, while a dead page is a genuine absence and is a finding.
BLOCKING_CODES = {"blocked", "crawl_error", "detect_block", "captcha_timeout",
                  "wait_element_timeout", "timeout", "ajax_request_error"}


def cli_runner(collector_id, url, timeout_s=900):
    """Run one collector against one URL. Returns (payload, error).

    Never raises on a collector failure, for the reason in the module docstring.
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


def query_for(seed, strategy):
    """The search string for one notice under one strategy, or None.

    Returns None rather than falling back to the other strategy. A silent
    fallback would record a hit under a strategy that never ran, corrupting the
    capture-recapture input and with it the only floor we have on what we
    missed.
    """
    needle = (seed.get("gtin") or seed.get("model") or "").strip()
    if not needle:
        return None
    if strategy == MODEL_ONLY:
        return needle
    brand = (seed.get("brand") or "").strip()
    if not brand:
        name = (seed.get("name") or "").strip()
        brand = name.split()[0] if name else ""
    return ("%s %s" % (brand, needle)).strip() if brand else None


def needle_for(seed):
    """What identity will be re-asserted against. GTIN preferred: it is the
    stronger claim and it validates itself."""
    return seed.get("gtin") or seed.get("model")


def sweep_arm(arm, collector_id, seeds, runner=cli_runner, captured_at=None):
    """Sweep one arm across every seed, both strategies. Returns (rows, report).

    `rows` are contract rows carrying this arm's verdict only; the caller widens
    them into the three-arm shape.
    """
    captured_at = captured_at or _now()
    seeds_by_ref = {s["ref"]: s for s in seeds}
    flat, adapters, errors = [], [], []

    for seed in seeds:
        needle = needle_for(seed)
        if not needle:
            continue
        for strategy in (BRAND_MODEL, MODEL_ONLY):
            query = query_for(seed, strategy)
            if not query:
                continue
            url = ARM_SEARCH[arm].format(q=quote_plus(query))
            payload, error = runner(collector_id, url)
            if error:
                # A failed fetch is recorded as a row carrying the error, not
                # dropped. normalize.classify() turns it into a counted discard,
                # which is how a failure stays visible instead of shrinking the
                # denominator underneath every published proportion.
                errors.append({"ref": seed["ref"], "strategy": strategy,
                               "error": error})
                flat.append({"seed_ref": seed["ref"], "arm": arm,
                             "query_kind": strategy, "needle": needle,
                             "captured_at": captured_at, "error": "crawl_error"})
                continue
            rows, adapter_report = convert(payload, seed["ref"], arm, strategy,
                                           needle, captured_at)
            flat.extend(rows)
            adapters.append(adapter_report)

    rows, report = normalize_sweep(flat, seeds_by_ref)
    report["arm"] = arm
    report["collector_id"] = collector_id
    report["fetch_errors"] = errors
    report["unmapped_fields"] = sorted({f for a in adapters
                                        for f in a["unmapped_fields"]})
    report["with_language"] = sum(a["with_language"] for a in adapters)
    report["with_currency"] = sum(a["with_currency"] for a in adapters)
    return rows, report


def arm_verdict(row):
    """One arm's row tier, as the verdict the wall renders for that arm."""
    if row["tier"] == "RED":
        return "RED"
    codes = {d["code"] for d in row.get("discarded", [])}
    if codes & BLOCKING_CODES:
        return "WITHHELD"
    return "NOT_FOUND"


def combine(seeds, per_arm):
    """Widen each arm's rows into one contract row per notice.

    A notice no arm could find is still emitted. Dropping it would silently
    shrink the denominator under every published proportion, which is the same
    class of error as rendering an absent field as zero.
    """
    arms_present = sorted(per_arm)
    by_arm = {arm: {r["source"]["ref"]: r for r in rows}
              for arm, rows in per_arm.items()}
    out = []

    for seed in seeds:
        ref = seed["ref"]
        base, arms, discarded, strategies = None, {}, [], set()

        for arm in arms_present:
            row = by_arm[arm].get(ref)
            if row is None:
                arms[arm] = "NOT_FOUND"
                continue
            arms[arm] = arm_verdict(row)
            discarded.extend(row.get("discarded", []))
            if row.get("found_by_query"):
                strategies.add(row["found_by_query"])
            # The published evidence comes from an arm that actually reddened,
            # so the receipt on screen is the one that supports the claim.
            if arms[arm] == "RED" and base is None:
                base = row

        template = base or _any_row(by_arm, ref) or _stub(seed)
        row = {k: v for k, v in template.items()
               if k not in ("arms", "discarded", "found_by_query", "rank")}
        row["arms"] = {a: arms.get(a, "NOT_FOUND") for a in ("US", "DE", "IN")}
        row["tier"] = "RED" if "RED" in arms.values() else (
            "AMBER" if template.get("tier") == "AMBER" else "DISCARDED")
        if base is None:
            row.pop("evidence", None)
        if discarded:
            row["discarded"] = discarded
        if strategies:
            row["found_by_query"] = "both" if len(strategies) > 1 else strategies.pop()
        out.append(row)

    # Rank after the fact, RED first then youngest hazard, so ordering is a
    # property of the data rather than of iteration order.
    out.sort(key=lambda r: (r["tier"] != "RED", r.get("days") or 0))
    for i, row in enumerate(out, 1):
        row["rank"] = i
    return out


def run(seeds, collectors, runner=cli_runner, previous=None, now=None):
    """One full sweep across every configured arm. Returns (rows, health).

    Writes nothing and prints nothing, so a caller can drive it from saved
    payloads in a test.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    captured_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sweep_id = "s_" + now.strftime("%Y-%m-%dT%H:%MZ")

    per_arm, reports, arms = {}, [], {}
    for arm, collector_id in sorted(collectors.items()):
        rows, report = sweep_arm(arm, collector_id, seeds, runner=runner,
                                 captured_at=captured_at)
        per_arm[arm] = rows
        reports.append(report)

        reds = sum(1 for r in rows if r["tier"] == "RED")
        joined = sum(1 for r in rows if r["tier"] in ("RED", "AMBER"))
        arms[arm] = dict(
            health.arm_state(arm, reds, len(seeds), len(report["fetch_errors"]),
                             joined),
            rows=reds, fails=len(report["fetch_errors"]), inputs=len(seeds),
            joined=joined, collector_id=collector_id,
        )

    rows = combine(seeds, per_arm)
    doc = health.build(sweep_id, now, arms, rows, reports, previous=previous, now=now)
    return rows, doc


def _any_row(by_arm, ref):
    for rows in by_arm.values():
        if ref in rows:
            return rows[ref]
    return None


def _stub(seed):
    """A row for a notice no arm returned anything for. It is still a
    measurement, and it still counts in the denominator."""
    return {
        "name": seed["name"], "hazard": seed["hazard"],
        "source": {"authority": seed["authority"], "ref": seed["ref"],
                   "published": seed["published"], "url": seed["url"]},
        "days": seed["days"], "days_frozen": False, "tier": "DISCARDED",
    }


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
