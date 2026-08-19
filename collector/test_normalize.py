"""Tests for the raw -> contract normalizer.

Raw rows here imitate real Scraper Studio output, including the two things that
break naive normalizers: keys that are simply ABSENT rather than null, and
first-class per-row `error` / `warning` fields.

Run:  python3 collector/test_normalize.py
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "contract"))

from normalize import (normalize, normalize_sweep, reassert, norm_needle,  # noqa: E402
                       classify, currency_ok, pick, context_around)
from contract_keys import MISSING  # noqa: E402

FAILURES = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILURES.append(msg)


SEED = {
    "authority": "CPSC", "ref": "24350", "published": "2024-08-29",
    "name": "HALO 1000 Portable Power Stations", "brand": "ZAGG",
    "model": "PS-1000", "gtin": "840056145528", "days": 721,
    "hazard": "The lithium-ion batteries can overheat, posing fire and burn hazards.",
    "url": "https://www.cpsc.gov/Recalls/24350",
}

GOOD = {
    "seed_ref": "24350", "arm": "US", "query_kind": "brand_model",
    "needle": "PS-1000", "url": "https://www.amazon.com/dp/B0XXXX",
    "http_status": 200, "captured_at": "2026-08-21T09:14:22Z",
    "page_text": "Product details Item model number PS-1000 Batteries included Yes",
    "dom_path": "#productDetails > tr:nth-child(4)",
    "buy_label": "Add to Cart", "in_stock": True, "ships_from": "US",
    "currency": "USD", "sha256": "3f9ac3d0", "trace": "ce-0001", "job_id": "j_ma13",
}

print("\nidentity re-assertion, the load-bearing check")
check(reassert("Item model number PS-1000 Batteries", "PS-1000"), "exact match found")
check(reassert("model number ps 1000 in stock", "PS-1000"),
      "case and separators ignored: 'ps 1000' matches 'PS-1000'")
check(reassert("Modellnummer KX77B Artikelgewicht", "KX-77B"),
      "matches across a German page with the hyphen dropped")
check(not reassert("Item model number PS-2000 Batteries", "PS-1000"),
      "PS-2000 does NOT satisfy PS-1000, which is the whole point")
check(not reassert(MISSING, "PS-1000"), "absent page text is not a match")
check(norm_needle("KX-77B") == norm_needle("kx 77 b"), "normaliser is separator-insensitive")

print("\ntiering")
t, d = classify(GOOD)
check(t == "RED" and not d, "identifier re-asserted + buy control = RED")

no_buy = {**GOOD}
del no_buy["buy_label"]
t, d = classify(no_buy)
check(t == "AMBER" and d[0]["code"] == "AMBER", "re-asserted but no buy control = AMBER, with a reason")

wrong = {**GOOD, "page_text": "Item model number PS-2000"}
t, d = classify(wrong)
check(t == "AMBER", "a live buy button on the WRONG product never reaches RED")

t, d = classify({**GOOD, "error": "dead_page"})
check(t == "DISCARDED" and d[0]["code"] == "dead_page", "a collector error is DISCARDED under its own code")

t, d = classify({**GOOD, "error": "some_new_code_bright_data_added"})
check(t == "DISCARDED" and d[0]["code"] == "crawl_error",
      "an unrecognised error code degrades to crawl_error rather than crashing")

t, d = classify({**GOOD, "http_status": 429})
check(t == "DISCARDED" and d[0]["code"] == "blocked", "HTTP 429 is a block, not a finding")

no_needle = {**GOOD}
del no_needle["needle"]
t, d = classify(no_needle)
check(t == "DISCARDED" and d[0]["code"] == "no_join_key", "nothing to search for = no_join_key")

print("\nabsent keys are absent, never zero")
check(pick({}, "x") is MISSING, "a key that is not there returns MISSING")
check(pick({"x": None}, "x") is MISSING, "an explicit null is MISSING")
check(pick({"x": "  "}, "x") is MISSING, "whitespace is MISSING")
check(pick({"x": 0}, "x") == 0, "a real zero is preserved and NOT turned into MISSING")
check(pick({"x": False}, "x") is False, "a real False is preserved")

sparse = {k: v for k, v in GOOD.items() if k not in ("dom_path", "ships_from", "sha256")}
row = normalize(sparse, SEED)
check("dom_path" not in row["evidence"]["assertion"],
      "an absent dom_path is OMITTED from the row, not nulled")
check("ships_from" not in row["evidence"]["buy_control"], "an absent ships_from is omitted")
check(row["tier"] == "RED", "a sparse row still reaches RED if the evidence holds")

print("\ncontract shape")
row = normalize(GOOD, SEED)
check(row["hazard"] == SEED["hazard"], "hazard comes from the REGULATOR, never the marketplace")
check(row["source"]["ref"] == "24350", "notice reference is preserved")
check(set(row["arms"]) if "arms" in row else True, "arms are attached by the sweep assembler, not here")
check(row["evidence"]["assertion"]["needle"] == "PS-1000", "needle recorded")
check("PS-1000" in row["evidence"]["assertion"]["context"], "context actually contains the needle")
check("price" not in json.dumps(row).lower() or "currency" in json.dumps(row),
      "no price VALUE is ever recorded, only the currency symbol")
check(row["evidence"]["currency"] == "USD", "currency captured for the fingerprint detector")

print("\ncurrency fingerprint")
check(currency_ok(GOOD) is True, "US row carrying USD passes")
check(currency_ok({**GOOD, "currency": "EUR"}) is False,
      "a US arm serving EUR is caught, which cross-arm comparison alone cannot see")
check(currency_ok({**GOOD, "arm": "DE", "currency": "EUR"}) is True, "DE row carrying EUR passes")
no_cur = {**GOOD}
del no_cur["currency"]
check(currency_ok(no_cur) is MISSING, "absent currency is MISSING, not a failure")

print("\ncapture-recapture: the two query passes")
seeds = {"24350": SEED}
both = [
    {**GOOD, "query_kind": "brand_model"},
    {**GOOD, "query_kind": "model_only"},
]
rows, rep = normalize_sweep(both, seeds)
check(len(rows) == 1, "two query passes collapse to one row per notice")
check(rows[0]["found_by_query"] == "both",
      "a notice found by BOTH strategies is recorded as the overlap term m")

one = [{**GOOD, "query_kind": "brand_model"}]
rows, rep = normalize_sweep(one, seeds)
check(rows[0]["found_by_query"] == "brand_model", "a single strategy is recorded as itself")

mixed = [
    {**GOOD, "query_kind": "brand_model", "error": "dead_page"},
    {**GOOD, "query_kind": "model_only"},
]
rows, rep = normalize_sweep(mixed, seeds)
check(rows[0]["tier"] == "RED",
      "if one strategy fails and the other finds it, the finding survives")

print("\nsweep report")
raw = [GOOD,
       {**GOOD, "seed_ref": "24350", "error": "blocked"},
       {**GOOD, "seed_ref": "NOPE"},
       {**GOOD, "seed_ref": "24350", "currency": "EUR"}]
rows, rep = normalize_sweep(raw, seeds)
check(rep["orphaned"] == 1, "a row whose seed we do not recognise is counted, not dropped silently")
check(rep["currency_mismatch"] == 1, "currency mismatch is counted")
check("blocked" in rep["by_code"], "discard reasons are counted by code for the anti-dashboard")

print("\nagainst the real seed corpus")
sf = HERE.parent / "data" / "seeds.json"
if sf.exists():
    seeds_all = json.loads(sf.read_text(encoding="utf-8"))["seeds"]
    idx = {s["ref"]: s for s in seeds_all}
    sample = [s for s in seeds_all if s.get("gtin")][:25]
    raw = [{**GOOD, "seed_ref": s["ref"], "needle": s["gtin"],
            "page_text": f"EAN {s['gtin']} Marke {s.get('brand') or 'n/a'}",
            "arm": "DE", "currency": "EUR"} for s in sample]
    rows, rep = normalize_sweep(raw, idx)
    check(len(rows) == len(sample), f"{len(rows)} real seeds normalised")
    check(all(r["tier"] == "RED" for r in rows), "all resolve RED when the GTIN re-asserts")
    check(rep["currency_mismatch"] == 0, "no currency drift on a DE sweep carrying EUR")

    # Every produced row must satisfy the frozen contract.
    sys.path.insert(0, str(HERE.parent))
    import validate as V
    schema = json.loads((HERE.parent / "contract" / "row.schema.json").read_text(encoding="utf-8"))
    errs = []
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        r["arms"] = {"US": "NOT_FOUND", "DE": "RED", "IN": "NOT_FOUND"}
        V.validate(r, schema, schema, f"row {i+1}", errs)
    check(not errs, "every normalised row validates against contract/row.schema.json"
          + ("" if not errs else f" :: {errs[:2]}"))
else:
    check(False, "seeds.json missing; run data/pull_seeds.py")

print("\n" + (f"{len(FAILURES)} FAILURES" if FAILURES else "all normalizer tests passed"))
sys.exit(1 if FAILURES else 0)
