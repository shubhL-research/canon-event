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

def collectors():
    """The collector map, with an explicit local override.

    The ids above are the ones that produced the published payload, and the
    comment on them says publishing them is what lets a judge re-run any figure
    against the same scraper. Silently swapping them for a different account's
    would break exactly that.

    So a second account is an override rather than an edit:
    data/collectors.local.json, untracked, read only if present. Whatever is
    actually used ends up in the payload's provenance block, so the wall always
    names the collectors that produced the rows on it rather than the ones the
    source file happens to list.
    """
    override = pathlib.Path(__file__).parent.parent / "data" / "collectors.local.json"
    if override.exists():
        loaded = json.loads(override.read_text(encoding="utf-8"))
        return {**COLLECTORS, **loaded}
    return dict(COLLECTORS)


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

# Except that 40 is a property of the storefront, not of the sweep, and one global
# number cost two hours for nothing.
#
# amazon.com is far slower per page than either regional marketplace. Three
# consecutive 40-URL jobs against it hit the CLI's one-hour poll ceiling and
# returned zero listings each time, while the same batch size on kaufland.de and
# flipkart.com completed fine. The batch has to fit inside the timeout, and how
# many pages fit in an hour is a fact about the site.
#
# Measured: kaufland returned 40 URLs in roughly twenty minutes, flipkart in
# forty. amazon.com did not finish 40 in sixty. 10 leaves a wide margin, at the
# cost of four times as many jobs, which is the correct trade — a job that times
# out costs an hour and yields nothing, so a smaller job that returns is cheaper
# in every sense.
ARM_BATCH_SIZE = {"US": 10}


def batch_size_for(arm, override=None):
    """URLs per job for this arm. An override wins, then the arm, then the default."""
    if override:
        return override
    return ARM_BATCH_SIZE.get(arm, BATCH_SIZE)

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
    #
    # CPSC's brand field is the RECALLING FIRM'S LEGAL NAME, not the consumer
    # brand. Used verbatim it produces queries no shopper would ever type:
    #
    #   Zhongshanboshangkedianzishangwuyouxiangongsi, dba beberoadlove, of China TB999-1
    #   Samsung Electronics America Inc., of Ridgefield Park, N.J. NE58K9430SS
    #
    # The consumer brand is in the product title, which CPSC writes as brand
    # first: "Beberoad New Moon Travel Bassinets", "ECHO gas-powered backpack
    # blowers". So a legal-entity brand is replaced by the title's first token,
    # and a short brand field is trusted as given.
    if _is_legal_entity(brand):
        brand = name.split()[0] if name else brand.split()[0]
    if not brand and name:
        brand = name.split()[0]
    if not brand:
        return None
    tail = model or name
    if not tail or tail == brand:
        return None
    return "%s %s" % (brand, tail)


# Markers of a corporate registration rather than a shelf brand. Any of these,
# or more than three words, and the field is a filing rather than a name.
_ENTITY_MARKERS = (", of ", " inc", " inc.", " llc", " ltd", " co.", " corp",
                   " gmbh", " company", " dba ", " l.p.", " s.a.", " b.v.")


def _is_legal_entity(brand):
    if not brand:
        return False
    low = " " + brand.lower().strip()
    if any(m in low for m in _ENTITY_MARKERS):
        return True
    return len(brand.split()) > 3


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
    # Listings the arm actually brought back, counted from the adapter rather than
    # from the normaliser: normalize_sweep also sees the synthetic rows injected
    # when a batch fails, and a placeholder for a failed fetch is not a listing.
    # Counting those made a blocked arm look like it had returned something.
    report["listings"] = sum(a["rows_out"] for a in adapters)
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
        batch_size=None, on_batch=None, raw_sink=None):
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
                                 captured_at=captured_at,
                                 batch_size=batch_size_for(arm, batch_size),
                                 on_batch=on_batch, raw_sink=raw_sink)
        per_arm[arm] = rows
        reports.append(report)

        reds = sum(1 for r in rows if r["tier"] == "RED")
        joined = sum(1 for r in rows if r["tier"] in ("RED", "AMBER"))
        # listings is everything the arm brought back and decided; rows is what
        # reddened. The detector needs the first, the wall shows the second.
        listings = report.get("listings", 0)
        arms[arm] = dict(
            health.arm_state(arm, listings, len(seeds),
                             len(report["fetch_errors"]), joined),
            rows=reds, listings=listings, fails=len(report["fetch_errors"]),
            inputs=len(seeds), joined=joined, collector_id=collector_id,
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


def adjudicate_from_raw(seeds, arms=None, now=None):
    """Re-decide every verdict from the archived raw rows. No network, no spend.

    WHY THIS EXISTS
    ---------------
    Every raw row is written to data/sweeps/raw/<ARM>.jsonl the moment it arrives,
    because Bright Data snapshots expire after 16 days and an expired snapshot is
    indistinguishable from a sweep that found nothing. That archive turns out to be
    worth more than insurance: it means the matcher can be changed and every past
    sweep re-scored for free.

    That matters because the matcher HAS changed twice in one day, both times in a
    direction that altered published verdicts — the GTIN leading-zero fix recovered
    real matches, and the check-digit rule removed rows that should never have been
    RED. Without this function each of those corrections would have cost another
    full sweep to observe.

    Reconstruction works because every row carries the `input.url` that produced
    it, and the plan that generated those URLs is deterministic: plan_arm() rebuilt
    from the same seeds yields the same url -> (ref, strategy, needle) mapping. No
    state is stored between runs and none needs to be.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    captured_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    raw_dir = pathlib.Path(__file__).parent.parent / "data" / "sweeps" / "raw"
    seeds_by_ref = {s["ref"]: s for s in seeds}
    arms = arms or sorted(ARM_SEARCH)

    per_arm, reports, arm_states = {}, [], {}
    for arm in arms:
        path = raw_dir / ("%s.jsonl" % arm)
        if not path.exists():
            continue
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

        by_url = {url: (ref, strategy, needle)
                  for url, ref, strategy, needle in plan_arm(arm, seeds)}
        grouped = group_by_input(rows)

        flat, adapters, unclaimed = [], [], 0
        for url, got in grouped.items():
            meta = by_url.get(url)
            if not meta:
                # A URL the current plan no longer generates. Counted rather than
                # dropped: it means the corpus or the query rule changed since the
                # sweep, and that is a fact about the archive worth reporting.
                unclaimed += len(got)
                continue
            ref, strategy, needle = meta
            converted, report = convert(got, ref, arm, strategy, needle, captured_at)
            flat.extend(converted)
            adapters.append(report)

        arm_rows, report = normalize_sweep(flat, seeds_by_ref)
        report["listings"] = sum(a["rows_out"] for a in adapters)
        report["arm"] = arm
        report["collector_id"] = COLLECTORS.get(arm, "replayed-from-archive")
        report["planned_loads"] = len(by_url)
        report["batches"] = 0
        report["fetch_errors"] = []
        report["replayed"] = True
        report["raw_rows"] = len(rows)
        report["unclaimed_rows"] = unclaimed
        report["unmapped_fields"] = sorted({f for a in adapters
                                           for f in a["unmapped_fields"]})
        report["with_language"] = sum(a["with_language"] for a in adapters)
        report["with_currency"] = sum(a["with_currency"] for a in adapters)
        per_arm[arm] = arm_rows
        reports.append(report)

        reds = sum(1 for r in arm_rows if r["tier"] == "RED")
        joined = sum(1 for r in arm_rows if r["tier"] in ("RED", "AMBER"))
        listings = report.get("listings", 0)
        arm_states[arm] = dict(
            health.arm_state(arm, listings, len(seeds), 0, joined),
            rows=reds, listings=listings, fails=0, inputs=len(seeds),
            joined=joined, collector_id=COLLECTORS.get(arm, "replayed-from-archive"),
        )

    if not per_arm:
        return [], None

    rows = combine(seeds, per_arm)
    sweep_id = "s_" + now.strftime("%Y-%m-%dT%H:%MZ") + "-replay"
    doc = health.build(sweep_id, now, arm_states, rows, reports, now=now)
    doc["replayed_from_archive"] = True
    return rows, doc


def already_swept():
    """Refs the raw archive already holds rows for, per arm and pooled.

    A notice is only worth re-fetching if something about the query changed. The
    archive is committed to disk and --from-raw re-scores it for free, so
    sweeping a notice we already own rows for spends money to learn nothing.
    """
    raw = pathlib.Path(__file__).parent.parent / "data" / "sweeps" / "raw"
    seen = set()
    for path in sorted(raw.glob("*.jsonl")):
        arm = path.stem
        seeds = load_seeds()
        by_url = {url: ref for url, ref, _s, _n in plan_arm(arm, seeds)}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            src = row.get("input")
            url = src.get("url") if isinstance(src, dict) else None
            if url in by_url:
                seen.add(by_url[url])
    return seen


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
    replay = "--from-raw" in argv
    batch_override = None
    arms = collectors()
    for i, a in enumerate(argv):
        if a == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1])
        if a == "--batch-size" and i + 1 < len(argv):
            batch_override = int(argv[i + 1])
        if a == "--arms" and i + 1 < len(argv):
            wanted = argv[i + 1].split(",")
            arms = {k: v for k, v in collectors().items() if k in wanted}

    seeds = load_seeds(limit=limit)

    if "--unswept" in argv:
        done = already_swept()
        seeds = [s for s in seeds if s["ref"] not in done]
        print("skipping %d notices already in the archive" % len(done))

    if replay:
        # Re-score the archive. Costs nothing and needs no network, so it is the
        # right way to observe a change to the matcher.
        rows, doc = adjudicate_from_raw(seeds, arms=sorted(arms))
        if doc is None:
            print("no archived raw rows in data/sweeps/raw/. Run a sweep first.")
            return 1
        return _write(rows, doc, seeds, limit, replayed=True)

    plans = {arm: plan_arm(arm, seeds) for arm in arms}
    sizes = {arm: batch_size_for(arm, batch_override) for arm in arms}
    loads = sum(len(p) for p in plans.values())
    batches = sum((len(p) + sizes[a] - 1) // sizes[a] for a, p in plans.items())

    print("seeds     %d%s" % (len(seeds), " (TRIAL SLICE)" if limit else ""))
    print("arms      " + ", ".join("%s=%s" % kv for kv in sorted(arms.items())))
    print("loads     %d search loads, 2 queries per notice per arm" % loads)
    print("batches   %d jobs" % batches)
    for arm in sorted(plans):
        print("  %-3s %4d loads -> %2d batches at %d urls each"
              % (arm, len(plans[arm]),
                 (len(plans[arm]) + sizes[arm] - 1) // sizes[arm], sizes[arm]))
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

    rows, doc = run(seeds, arms, on_batch=on_batch, raw_sink=raw_sink,
                    batch_size=batch_override)
    return _write(rows, doc, seeds, limit)


def _write(rows, doc, seeds, limit, replayed=False):
    """Persist a sweep and report it. Shared by the live and replay paths so the
    two cannot drift in how they label or count what they produced."""
    out = pathlib.Path(__file__).parent.parent / "data" / "sweeps"
    out.mkdir(parents=True, exist_ok=True)

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
    if replayed:
        print("REPLAYED from data/sweeps/raw/. No network, no credits spent.")
    print("rows      %d   RED %d   AMBER %d" % (len(rows), reds, ambers))
    for arm, state in sorted(doc["arms"].items()):
        print("  %-3s %-10s red=%-4d fails=%-3d %s"
              % (arm, state["state"], state["rows"], state["fails"],
                 state["reason"] or ""))
    for r in doc.get("reports", []):
        if r.get("replayed"):
            print("  %-3s replayed %d raw rows, %d unclaimed by the current plan"
                  % (r["arm"], r.get("raw_rows", 0), r.get("unclaimed_rows", 0)))
    fired = [k for k, v in doc["detectors"].items() if v["fired"]]
    print("detectors fired: %s" % (", ".join(fired) if fired else "none"))
    print()
    print("verdict   " + doc["verdict"])
    print("written   data/sweeps/%s.jsonl" % stem)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
