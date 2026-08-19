"""Raw Scraper Studio output -> contract rows.

DIVISION OF LABOUR
------------------
The collector emits whatever Scraper Studio gives it. This module turns that
into rows that satisfy contract/row.schema.json. Nobody writing a collector
should have to think about our schema, and nobody reading the wall should have
to think about Bright Data's output shape.

So: emit the RAW_FIELDS below and stop. This file does the rest, and
test_normalize.py proves it against realistic raw input including failures.

THE RULE THAT MATTERS MOST
--------------------------
Bright Data OMITS absent keys rather than nulling them. A key that is not there
is not an error and is not a zero, and if it is silently coerced to 0 or "" then
a gap in our own measurement becomes a claim about the world. Every read goes
through pick(), which returns MISSING, and MISSING is preserved all the way to
the screen where it renders as a struck field name.

Standard library only.
"""

import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "contract"))
from contract_keys import MISSING  # noqa: E402

# What a collector must emit per input. Anything else is ignored.
RAW_FIELDS = [
    "seed_ref",        # our recall reference, passed in as collector input
    "arm",             # US | DE | IN
    "query_kind",      # brand_model | model_only   <- capture-recapture input
    "needle",          # the identifier we searched for
    "url",             # the product page actually fetched
    "http_status",
    "page_text",       # text used for identity re-assertion
    "dom_path",        # where the needle was found
    "buy_label",       # the marketplace's own words, in its own language
    "in_stock",
    "ships_from",
    "currency",        # EUR | USD | INR. SYMBOL ONLY, never a price value.
    "sha256",
    "trace",
    "job_id",
    "error",           # a Bright Data error code, if the input failed
    "warning",
]

# Bright Data's documented error taxonomy. `blocked` means our own code called
# blocked(); `block` is the fetch layer. They are different events and the wall
# reports them separately, so do not collapse them.
FATAL_ERRORS = {
    "dead_page", "bad_input", "blocked", "crawl_error", "detect_block",
    "wait_element_timeout", "ajax_request_error", "captcha_timeout",
    "click_timeout", "timeout", "ERR_INVALID_URL", "not_supported_cmd",
    "detached_element", "load_more_timeout", "close_popup_fail",
    "collector_request_validation", "load_sitemap", "tag_response",
    "child_input_size_validation",
}

# Statuses the docs list as block-layer responses.
BLOCK_STATUSES = {400, 401, 403, 404, 405, 409, 410, 418, 429, 500, 503}

CURRENCY_FOR_ARM = {"US": "USD", "DE": "EUR", "IN": "INR"}


def pick(row, key):
    """Read a key that may simply not be there.

    Never use row[key] or row.get(key, "") on collector output. An omitted key
    and an empty string are different facts: one means we did not measure, the
    other means we measured nothing.
    """
    if key not in row:
        return MISSING
    v = row[key]
    if v is None or (isinstance(v, str) and not v.strip()):
        return MISSING
    return v


def present(v):
    return v is not MISSING


def norm_needle(s):
    """Identifier comparison is case- and separator-insensitive.

    Marketplaces render a model as KX-77B, kx77b or KX 77B. Treating those as
    different strings would reject a correct match and silently count the
    product as no longer on sale, which is the failure direction that matters.
    """
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def needle_pattern(needle):
    """A separator-tolerant, boundary-anchored pattern for an identifier.

    Marketplaces render PS-1000 as "PS-1000", "PS 1000" or "PS1000", so the
    match has to tolerate separators. But it must NOT tolerate extra characters
    at either end, and that distinction is the difference between a correct
    finding and a false accusation:

        searching PS-100  against a page reading PS-1000  ->  MUST NOT match
        searching PS-1000 against a page reading PS-1000  ->  must match

    A naive substring test accepts the first, which means publishing a hazard
    claim against a seller shipping a DIFFERENT product. The adversarial
    precision set exists to catch exactly this, and it did.
    """
    chars = [c for c in str(needle) if c.isalnum()]
    if not chars:
        return None
    sep = r"[\W_]*"
    body = sep.join(re.escape(c) for c in chars)
    return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", re.I)


def reassert(page_text, needle):
    """Did the identifier actually reappear on the page we fetched?

    This is the load-bearing check in the whole project. Amazon substitutes
    ASINs on stale URLs, so a live buy control on the WRONG product would score
    as a hazard still on sale. The identifier must be present in the fetched
    page's own text, not merely in the URL we asked for, and it must appear as
    a whole token rather than as a fragment of a longer one.
    """
    if not present(page_text) or not present(needle):
        return False
    pat = needle_pattern(needle)
    return bool(pat and pat.search(str(page_text)))


def context_around(page_text, needle, width=90):
    """A short excerpt containing the needle, for the two-receipt card."""
    if not present(page_text) or not present(needle):
        return MISSING
    pat = needle_pattern(needle)
    m = pat.search(str(page_text)) if pat else None
    if not m:
        return MISSING
    start = max(0, m.start() - width)
    end = min(len(str(page_text)), m.end() + width)
    return ("..." if start else "") + str(page_text)[start:end] + ("..." if end < len(str(page_text)) else "")


def classify(raw):
    """RED, AMBER or DISCARDED, with the reason recorded either way."""
    err = pick(raw, "error")
    if present(err):
        code = str(err) if str(err) in FATAL_ERRORS else "crawl_error"
        return "DISCARDED", [{"code": code, "reason": f"collector reported {err}"}]

    status = pick(raw, "http_status")
    if present(status) and int(status) in BLOCK_STATUSES:
        return "DISCARDED", [{"code": "blocked",
                              "reason": f"HTTP {status} from the fetch layer"}]

    needle = pick(raw, "needle")
    if not present(needle):
        return "DISCARDED", [{"code": "no_join_key",
                              "reason": "no machine-matchable identifier to search for"}]

    matched = reassert(pick(raw, "page_text"), needle)
    buy = pick(raw, "buy_label")

    if matched and present(buy):
        return "RED", []
    if matched and not present(buy):
        return "AMBER", [{"code": "AMBER",
                          "reason": "identifier re-asserted but no active buy control at capture time"}]
    return "AMBER", [{"code": "AMBER",
                      "reason": "identifier not re-asserted on the fetched page"}]


def currency_ok(raw):
    """Currency fingerprint. One line of code, kills a whole failure class.

    Every DE row must carry EUR, every IN row INR, every US row USD. If an arm
    silently drifts to another country's storefront, cross-arm comparison is
    structurally blind to it but the currency is not.
    """
    arm, cur = pick(raw, "arm"), pick(raw, "currency")
    if not present(arm) or not present(cur):
        return MISSING
    return cur == CURRENCY_FOR_ARM.get(arm)


def normalize(raw, seed):
    """One raw collector row + its seed notice -> one contract row.

    `seed` is the recall notice from data/seeds.json. The regulator's fields are
    never taken from the marketplace: the hazard sentence, reference and
    publication date come from the notice, always.
    """
    tier, discarded = classify(raw)
    needle = pick(raw, "needle")

    row = {
        "name": seed["name"],
        "hazard": seed["hazard"],
        "source": {
            "authority": seed["authority"],
            "ref": seed["ref"],
            "published": seed["published"],
            "url": seed["url"],
        },
        "days": seed["days"],
        "days_frozen": False,
        "tier": tier,
    }
    if seed.get("model"):
        row["model"] = seed["model"]
    if seed.get("gtin"):
        row["gtin"] = seed["gtin"]

    qk = pick(raw, "query_kind")
    if present(qk):
        row["found_by_query"] = qk

    if tier == "RED":
        ev = {
            "captured_at": raw.get("captured_at"),
            "assertion": {"needle": needle,
                          "context": context_around(pick(raw, "page_text"), needle)},
            "buy_control": {"present": True},
        }
        for src, dst, parent in [
            ("dom_path", "dom_path", "assertion"),
            ("buy_label", "label", "buy_control"),
            ("in_stock", "in_stock", "buy_control"),
            ("ships_from", "ships_from", "buy_control"),
        ]:
            v = pick(raw, src)
            if present(v):
                ev[parent][dst] = v
        for src in ("http_status", "currency", "sha256", "trace", "job_id"):
            v = pick(raw, src)
            if present(v):
                ev["http" if src == "http_status" else src] = v
        # Drop MISSING from the assertion so the key is ABSENT, not null. That
        # absence is what the wall renders as MISSING.
        if ev["assertion"]["context"] is MISSING:
            del ev["assertion"]["context"]
        row["evidence"] = ev

    if discarded:
        row["discarded"] = discarded
    return row


def normalize_sweep(raw_rows, seeds_by_ref):
    """Whole sweep. Returns (rows, report).

    The report is not decoration: it feeds the WHAT WE DID NOT SEE panel and the
    detectors. A row that fails is still a measurement and is still counted.
    """
    rows, report = [], {"in": len(raw_rows), "out": 0, "orphaned": 0,
                        "by_code": {}, "currency_mismatch": 0, "by_query": {}}

    for raw in raw_rows:
        ref = pick(raw, "seed_ref")
        seed = seeds_by_ref.get(ref) if present(ref) else None
        if seed is None:
            report["orphaned"] += 1
            continue

        row = normalize(raw, seed)
        rows.append(row)
        report["out"] += 1

        for d in row.get("discarded", []):
            report["by_code"][d["code"]] = report["by_code"].get(d["code"], 0) + 1
        if currency_ok(raw) is False:
            report["currency_mismatch"] += 1
        qk = row.get("found_by_query")
        if qk:
            report["by_query"][qk] = report["by_query"].get(qk, 0) + 1

    # Two queries run per recall per arm, so the same seed can appear twice.
    # Collapse to one row per (seed, arm) and record that BOTH strategies found
    # it, which is exactly the capture-recapture overlap.
    return merge_query_strategies(rows), report


def merge_query_strategies(rows):
    """Collapse the two query passes into one row per notice.

    A seed found by brand+model AND by model alone is the overlap term `m` in
    the Chapman estimator. Losing that here would silently destroy the recall
    floor, so it is computed rather than assumed.
    """
    by_ref, order = {}, []
    for r in rows:
        ref = r["source"]["ref"]
        if ref not in by_ref:
            by_ref[ref] = r
            order.append(ref)
            continue
        keep, other = by_ref[ref], r
        # Prefer the row that actually established a finding.
        rank = {"RED": 3, "AMBER": 2, "DISCARDED": 1}
        if rank[other["tier"]] > rank[keep["tier"]]:
            keep, other = other, keep
        a, b = keep.get("found_by_query"), other.get("found_by_query")
        if a and b and a != b:
            keep["found_by_query"] = "both"
        by_ref[ref] = keep
    return [by_ref[r] for r in order]
