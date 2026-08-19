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
import tempfile
from urllib.parse import quote_plus

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import health                                                    # noqa: E402
from fromstudio import convert                                   # noqa: E402
from normalize import normalize_sweep, gtin_check_digit_ok       # noqa: E402

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
    "IN": "https://www.flipkart.com/search?q={q}",
}

# The live collectors, by arm. Not secrets — a collector id is a handle, and
# publishing them is what lets a judge re-run any figure on this wall against the
# same scraper that produced it.
#
# All three measure. The US arm was recorded as broken for several hours on the
# strength of a wait_element_timeout, which turned out to be the collector working
# correctly on a query that could not succeed: we were searching amazon.com for a
# barcode. With the query fixed it returns 1,636 rows across 24 search pages with
# zero errors. The correction is at the end of heals/2026-08-19-us-001.md.
COLLECTORS = {
    "DE": "c_mt00jidz6zhqjbpew",   # kaufland.de, built clean, first try
    "IN": "c_mt03cj5z2fo651wy8q",  # flipkart.com, built clean, first try
    "US": "c_mt01usw31e8y5ubqjs",  # amazon.com, one refused heal, measures
}

# amazon.de, healed twice and approved. Held separately because it is a SECOND
# German storefront rather than a fourth arm: it exists to demonstrate the heal
# loop on a property that fought back, and the DE arm's published rows come from
# kaufland. Running both into one arm would double-count German listings.
AMAZON_DE = "c_mt000dde2qdd6uln7z"

# Row tier to the verdict the wall renders for that arm. The distinction that
# matters is DISCARDED splitting two ways: a blocked fetch is our own failure and
# withholds, while a dead page is a genuine absence and is a finding.
BLOCKING_CODES = {"blocked", "crawl_error", "detect_block", "captcha_timeout",
                  "wait_element_timeout", "timeout", "ajax_request_error"}


# URLs per batch job. The ceiling is not the CLI's, it is the platform's: the
# docs warn about a 16MB per-session accumulation cap and a too_many_pages error
# on high fan-out, and each of our search URLs returns 30 to 400 rows. 40 keeps a
# worst-case batch under a few MB while still collapsing the sweep by 40x.
BATCH_SIZE = 40

# Batch jobs poll rather than stream, so the wait is per batch, not per URL.
BATCH_TIMEOUT_S = 3600


def cli_batch(collector_id, urls, timeout_s=BATCH_TIMEOUT_S):
    """Run one collector against MANY urls as a single job. Returns (rows, error).

    WHY THIS IS BATCHED AND THE OBVIOUS VERSION IS NOT
    --------------------------------------------------
    The first version of this function ran one URL per invocation, which is the
    natural way to write it and is unusable at the size of this project. Measured
    on the real trial sweep: about six minutes per call, dominated by `npx`
    re-resolving the package and by a fresh job being queued each time. The full
    corpus is 207 notices x 2 query strategies x 3 arms = 1,242 loads, so
    sequential single-URL calls come to roughly 124 hours. The sweep was not slow,
    it was impossible.

    `bdata scraper run --input-file` submits every URL as one job through
    /dca/trigger and polls once. The same 1,242 loads become 32 batch jobs.

    Inputs go through a file rather than `--urls`, because a comma-separated list
    of 40 search URLs runs into the shell's argument limits and, worse, does it
    intermittently depending on how long the query strings happen to be.

    The mapping back to seeds is possible because every returned row carries the
    `input.url` that produced it. That is the only reason batching is safe here:
    without it, one batch would be an undifferentiated pile of rows and there
    would be no way to say which recall any listing answered.
    """
    if not urls:
        return [], None

    fd = None
    try:
        fd = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8")
        fd.write("\n".join(urls) + "\n")
        fd.close()
        cmd = ["npx", "-p", "@brightdata/cli", "bdata", "scraper", "run",
               collector_id, "--input-file", fd.name, "--json",
               "--timeout", str(timeout_s)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout_s + 120)
        except subprocess.TimeoutExpired:
            return None, "cli timeout after %ds on a batch of %d" % (timeout_s, len(urls))
        except OSError as exc:
            return None, "cli not runnable: %s" % exc

        if proc.returncode != 0:
            return None, (proc.stderr or proc.stdout or "").strip()[:400]
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            return None, "unparseable CLI output: %s" % exc
        return payload if isinstance(payload, list) else _rows_of_payload(payload), None
    finally:
        if fd is not None:
            try:
                pathlib.Path(fd.name).unlink()
            except OSError:
                pass


def _rows_of_payload(payload):
    if isinstance(payload, dict):
        for key in ("data", "results", "rows", "items", "output"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def group_by_input(rows):
    """Split a batch's rows by the input URL that produced them.

    Every Scraper Studio row carries `input.url`. A row that somehow does not is
    kept under None rather than dropped: it is still a measurement, and losing it
    silently would shrink a denominator.
    """
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        src = row.get("input")
        url = src.get("url") if isinstance(src, dict) else None
        out.setdefault(url, []).append(row)
    return out


def query_for(seed, strategy):
    """The search string for one notice under one strategy, or None.

    WHAT WE TYPE IS NOT WHAT WE ASSERT
    ----------------------------------
    These were the same value, and that was why the first 30-seed sweep returned
    3,177 rows and zero findings. `needle_for()` prefers the GTIN, because a
    barcode is the strongest thing to re-assert on a page, and that same GTIN was
    being handed to the search box:

        brand_model  ->  "Taf toys 605566127156"
        model_only   ->  "605566127156"

    A marketplace search indexes product text, not barcodes. Neither query can
    find the product, so the matcher was fed same-brand siblings and correctly
    refused all of them. The seed had `name: "Foam mat"` and `model: "12715"`
    sitting unused.

    The two are different jobs. A query has to be findable by a search engine
    built for shoppers; a needle has to be unambiguous on a page. So the query is
    built from the model number and the product name, and the GTIN stays where it
    belongs, in `needle_for()`.

    Returns None rather than falling back to the other strategy. A silent
    fallback would record a hit under a strategy that never ran, corrupting the
    capture-recapture input and with it the only floor we have on what we missed.
    """
    model = (seed.get("model") or "").strip()
    name = (seed.get("name") or "").strip()
    brand = (seed.get("brand") or "").strip()

    if strategy == MODEL_ONLY:
        # The identifier alone. A GTIN is the last resort rather than the first
        # choice: some storefronts do index barcodes, so it is worth one of the
        # two passes when there is no model number, but it is never the pass we
        # rely on.
        return model or (seed.get("gtin") or "").strip() or None

    # brand_model: what a person looking for this product would actually type.
    # The product name carries it when there is no model number, because "Taf
    # toys Foam mat" is a real search and "Taf toys" alone is a catalogue.
    if not brand and name:
        brand = name.split()[0]
    if not brand:
        return None
    tail = model or name
    if not tail or tail == brand:
        return None
    return "%s %s" % (brand, tail)


def needle_for(seed):
    """What identity will be re-asserted against. GTIN preferred: it is the
    stronger claim and it validates itself."""
    return seed.get("gtin") or seed.get("model")


def plan_arm(arm, seeds):
    """Every URL this arm will fetch, with what each one is asking.

    Planning the whole arm before fetching anything is what makes batching
    possible, and it also makes the sweep inspectable: `--dry-run` prints exactly
    what would be spent without spending it. A sweep whose cost can only be
    discovered by running it is a sweep that gets run twice.

    Returns a list of (url, seed_ref, strategy, needle). Two entries per notice,
    always, for the reason in the module docstring.
    """
    plan = []
    for seed in seeds:
        needle = needle_for(seed)
        if not needle:
            continue
        for strategy in (BRAND_MODEL, MODEL_ONLY):
            query = query_for(seed, strategy)
            if not query:
                continue
            url = ARM_SEARCH[arm].format(q=quote_plus(query))
            plan.append((url, seed["ref"], strategy, needle))
    return plan


def sweep_arm(arm, collector_id, seeds, runner=cli_batch, captured_at=None,
              batch_size=BATCH_SIZE, on_batch=None, raw_sink=None):
    """Sweep one arm in batches, then adjudicate. Returns (rows, report).

    `rows` carry this arm's verdict only; the caller widens them into the
    three-arm shape.

    `raw_sink`, if given, is called with every raw row as it arrives. The docs
    warn that snapshots expire after 16 days and are unrecoverable, and that an
    empty result often means expiry rather than zero rows. Persisting on receipt
    is the difference between a sweep we can re-adjudicate later and a sweep we
    would have to pay for again.
    """
    captured_at = captured_at or _now()
    seeds_by_ref = {s["ref"]: s for s in seeds}
    plan = plan_arm(arm, seeds)
    by_url = {url: (ref, strategy, needle) for url, ref, strategy, needle in plan}

    flat, adapters, errors = [], [], []

    for start in range(0, len(plan), batch_size):
        chunk = plan[start:start + batch_size]
        urls = [u for u, _, _, _ in chunk]
        rows, error = runner(collector_id, urls)

        if error:
            # The whole batch failed. Every URL in it becomes a row carrying the
            # error rather than vanishing: normalize.classify() turns each into a
            # counted discard, which keeps the failure visible instead of
            # quietly shrinking the denominator under every published
            # proportion. This is also why a batch failure cannot silently look
            # like "nothing is on sale".
            for url, ref, strategy, needle in chunk:
                errors.append({"ref": ref, "strategy": strategy, "error": error})
                flat.append({"seed_ref": ref, "arm": arm, "query_kind": strategy,
                             "needle": needle, "captured_at": captured_at,
                             "error": "crawl_error"})
            if on_batch:
                on_batch(arm, start // batch_size + 1, len(chunk), 0, error)
            continue

        if raw_sink:
            raw_sink(arm, rows)

        grouped = group_by_input(rows)
        for url, ref, strategy, needle in chunk:
            got = grouped.get(url, [])
            if not got:
                # This query found nothing. That is a legitimate result and not
                # an error, so no row is emitted: found_by_query records hits
                # only, and a miss under one strategy is exactly what the
                # capture-recapture overlap is measuring.
                continue
            converted, adapter_report = convert(got, ref, arm, strategy, needle,
                                                captured_at)
            flat.extend(converted)
            adapters.append(adapter_report)

        if on_batch:
            on_batch(arm, start // batch_size + 1, len(chunk), len(rows), None)

    rows, report = normalize_sweep(flat, seeds_by_ref)
    report["arm"] = arm
    report["collector_id"] = collector_id
    report["planned_loads"] = len(plan)
    report["batches"] = (len(plan) + batch_size - 1) // batch_size
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


def run(seeds, collectors, runner=cli_batch, previous=None, now=None,
        batch_size=BATCH_SIZE, on_batch=None, raw_sink=None):
    """One full sweep across every configured arm. Returns (rows, health).

    Writes nothing and prints nothing itself, so a caller can drive it from saved
    payloads in a test. Progress and persistence are injected: `on_batch` reports,
    `raw_sink` archives.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    captured_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sweep_id = "s_" + now.strftime("%Y-%m-%dT%H:%MZ")

    per_arm, reports, arms = {}, [], {}
    for arm, collector_id in sorted(collectors.items()):
        rows, report = sweep_arm(arm, collector_id, seeds, runner=runner,
                                 captured_at=captured_at, batch_size=batch_size,
                                 on_batch=on_batch, raw_sink=raw_sink)
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


def load_seeds(limit=None, authority=None):
    """Read the corpus. `limit` exists for trial sweeps, and says so on the run.

    A trial slice is honest only if it is labelled. An unlabelled partial sweep
    published next to a full one is indistinguishable from it, and the
    denominators differ.
    """
    path = pathlib.Path(__file__).parent.parent / "data" / "seeds.json"
    seeds = json.loads(path.read_text(encoding="utf-8"))["seeds"]
    if authority:
        seeds = [s for s in seeds if s["authority"] == authority]
    # Order by how strong an identifier the notice carries, because a trial slice
    # is only informative if it can actually reach a verdict. A check-digit-valid
    # GTIN is the strongest; a `gtin` field that fails its own check digit is
    # worth less than a model number, since it will be refused as unassertable.
    # This is ordering only — a full sweep still gets every notice.
    def strength(seed):
        gtin = seed.get("gtin")
        if gtin and gtin_check_digit_ok(gtin):
            return 0
        if seed.get("model"):
            return 1
        return 2 if gtin else 3

    seeds.sort(key=lambda s: (strength(s), s["ref"]))
    return seeds[:limit] if limit else seeds


def main(argv):
    """Run a sweep and write it to data/sweeps/. Trial slices are labelled."""
    limit = None
    dry = "--dry-run" in argv
    arms = dict(COLLECTORS)
    for i, a in enumerate(argv):
        if a == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1])
        if a == "--arms" and i + 1 < len(argv):
            wanted = argv[i + 1].split(",")
            arms = {k: v for k, v in COLLECTORS.items() if k in wanted}

    seeds = load_seeds(limit=limit)
    plans = {arm: plan_arm(arm, seeds) for arm in arms}
    loads = sum(len(p) for p in plans.values())
    batches = sum((len(p) + BATCH_SIZE - 1) // BATCH_SIZE for p in plans.values())

    print("seeds     %d%s" % (len(seeds), " (TRIAL SLICE)" if limit else ""))
    print("arms      " + ", ".join("%s=%s" % kv for kv in sorted(arms.items())))
    print("loads     %d search loads, 2 queries per notice per arm" % loads)
    print("batches   %d jobs at %d urls each" % (batches, BATCH_SIZE))
    for arm in sorted(plans):
        print("  %-3s %4d loads -> %2d batches"
              % (arm, len(plans[arm]),
                 (len(plans[arm]) + BATCH_SIZE - 1) // BATCH_SIZE))
    if limit:
        print("\nTRIAL SLICE of %d notices. Not a full sweep, and stamped as such."
              % limit)
    if dry:
        print("\n--dry-run: nothing fetched, no credits spent.")
        return 0
    print()

    out = pathlib.Path(__file__).parent.parent / "data" / "sweeps"
    out.mkdir(parents=True, exist_ok=True)

    def on_batch(arm, n, urls_in, rows_out, error):
        print("  %-3s batch %-3d %3d urls -> %5s rows  %s"
              % (arm, n, urls_in, rows_out, error or ""), flush=True)

    # Persist raw rows on receipt. Snapshots expire after 16 days and are
    # unrecoverable, and an empty result often means expiry rather than zero
    # rows. Archiving as they arrive is what makes re-adjudicating a sweep free
    # instead of a second purchase.
    raw_path = out / "raw"
    raw_path.mkdir(exist_ok=True)

    def raw_sink(arm, rows):
        with (raw_path / ("%s.jsonl" % arm)).open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    rows, doc = run(seeds, arms, on_batch=on_batch, raw_sink=raw_sink)
    if limit:
        doc["trial_slice"] = limit
        doc["_STATUS"] = ("TRIAL SLICE, %d of %d notices. Denominators are not "
                          "the full corpus." % (limit, len(load_seeds())))

    stem = doc["sweep_id"].replace(":", "").replace("-", "")
    (out / (stem + ".jsonl")).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8")
    (out / (stem + "-health.json")).write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    reds = sum(1 for r in rows if r["tier"] == "RED")
    ambers = sum(1 for r in rows if r["tier"] == "AMBER")
    print()
    print("rows      %d   RED %d   AMBER %d" % (len(rows), reds, ambers))
    for arm, state in sorted(doc["arms"].items()):
        print("  %-3s %-10s red=%-4d fails=%-3d %s"
              % (arm, state["state"], state["rows"], state["fails"],
                 state["reason"] or ""))
    fired = [k for k, v in doc["detectors"].items() if v["fired"]]
    print("detectors fired: %s" % (", ".join(fired) if fired else "none"))
    print()
    print("verdict   " + doc["verdict"])
    print("written   data/sweeps/%s.jsonl" % stem)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
