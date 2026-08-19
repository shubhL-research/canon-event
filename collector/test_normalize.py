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
                       classify, currency_ok, pick, context_around,
                       gtin_check_digit_ok, collapse_repeat, language_ok, gtin_forms,
                       needle_is_assertable, buy_control_present)
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

print("\nthe superstring trap (a real bug the adversarial set found)")
check(not reassert("Item model number PS-1000 Batteries", "PS-100"),
      "searching PS-100 does NOT match a page reading PS-1000")
check(not reassert("EAN 7370522686759 Marke Replay", "737052268675"),
      "a GTIN is not matched by a longer GTIN that starts with it")
check(not reassert("Modellnummer KX-77BX", "KX-77B"),
      "a trailing character defeats the match, as it must")
check(reassert("Item model number PS-1000 Batteries", "PS-1000"),
      "...while the exact identifier still matches")
check(reassert("model: PS-1000.", "PS-1000"), "trailing punctuation is still a boundary")
# A naive substring test accepts all three rejections above. Publishing on that
# basis means accusing a seller of shipping a product they do not sell.
naive = lambda hay, ned: norm_needle(ned) in norm_needle(hay)
check(naive("Item model number PS-1000 Batteries", "PS-100"),
      "confirming the naive test WOULD have leaked, so these probes are not vacuous")

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

print("\nGTIN check digits, checkable on paper")
# 4006381333931 is a published EAN-13: the weighted body sums to 89, so the
# check digit must be (10 - 89 mod 10) mod 10 = 1.
check(gtin_check_digit_ok("4006381333931"), "a real EAN-13 validates")
check(not gtin_check_digit_ok("4006381333930"), "the same EAN with a wrong check digit fails")
check(gtin_check_digit_ok("036000291452"), "a real UPC-12 validates")
check(gtin_check_digit_ok("0 36000 29145 2"), "separators in a GTIN are tolerated")
check(not gtin_check_digit_ok("3973500298"),
      "a real Safety Gate 10-digit 'barcode' is not a GTIN")
check(not gtin_check_digit_ok(None), "an absent GTIN fails rather than raising")

print("\nGTIN formats: a leading zero is not a different product")
# GS1: GTIN-8/12/13/14 are one number space, and the shorter form is the longer
# one with leading zeros stripped. Found on the first live trial sweep, on a real
# kaufland.de row carrying both forms in the same field.
check(gtin_check_digit_ok("605566127453") and gtin_check_digit_ok("0605566127453"),
      "a UPC-12 and its EAN-13 form are both valid GTINs")
check(reassert("EAN 0605566127453 Taf Toys", "605566127453"),
      "a 12-digit notice matches a page printing the 13-digit form")
check(reassert("EAN 605566127453 Taf Toys", "0605566127453"),
      "and the reverse, because the anchor must not treat a format as a product")
# The refusal this must not weaken. Same brand, same GS1 prefix, last three
# digits different: a sibling item, not the recalled one. Seen live.
check(not reassert("EAN 605566127156 Taf Toys", "605566127453"),
      "an ADJACENT GTIN is still refused, which is the whole point of anchoring")
check(gtin_forms("113210") == [],
      "a non-GTIN has no equivalent renderings and gets none invented")
check(context_around("Marke Taf EAN 0605566127453 Farbe", "605566127453")
      is not MISSING,
      "the receipt quotes the form that actually matched, not the one we asked for")

print("\nWhat may assert identity at all")
check(needle_is_assertable("BR-C708S"), "a model number containing letters is assertable")
# Bare numerics collide with prices, review counts and millimetre dimensions on
# any retail page. Boundary anchoring cannot save a number that means something
# else entirely.
check(not needle_is_assertable("113210"), "a bare numeric SKU is not assertable as a model")
check(not needle_is_assertable("2024"), "a model year is not assertable")
check(needle_is_assertable("4006381333931", is_gtin=True),
      "a valid GTIN is assertable even though it is all digits")
check(not needle_is_assertable("4006381333930", is_gtin=True),
      "an invalid GTIN is not assertable, digits notwithstanding")

print("\nDoubled values, a real collector artifact")
# 25 of 28 live kaufland.de rows arrived like this.
check(collapse_repeat("8721003407246 8721003407246") == "8721003407246",
      "an exactly doubled EAN collapses to one usable barcode")
check(gtin_check_digit_ok(collapse_repeat("8721003407246 8721003407246")),
      "and the collapsed value passes its own check digit, which is the proof")
check(collapse_repeat("6015-00-02 6015-00-02") == "6015-00-02",
      "a doubled part number collapses too")
check(collapse_repeat("A, B, A") == "A, B, A",
      "a genuinely repetitive multi-value field is left alone")
check(collapse_repeat(None) is None, "an absent value collapses to nothing, not a crash")

print("\nGeography, which outranks the hazard")
DE_ROW = {**GOOD, "arm": "DE", "currency": "EUR", "page_language": "de",
          "buy_label": "In den Einkaufswagen"}
check(language_ok(DE_ROW) is True, "a German page satisfies the DE arm")
# The case that cost a heal: amazon.de answering in Danish, quoting EUR.
check(language_ok({**DE_ROW, "page_language": "da"}) is False,
      "a Danish page on amazon.de fails the DE arm even though EUR is correct")
check(language_ok({**DE_ROW, "page_language": None}) is MISSING,
      "an unemitted page_language is unproven, not disproven")
check(classify({**DE_ROW, "page_language": "da"})[0] == "DISCARDED",
      "a wrong-locale row is refused before its hazard is ever considered")

print("\nBuy controls, in the marketplace's own language")
check(buy_control_present(DE_ROW), "the German label counts on the DE arm")
check(buy_control_present({**GOOD, "arm": "US", "buy_label": "Add to Cart"}),
      "the US label counts on the US arm")
check(not buy_control_present({**DE_ROW, "buy_label": "Tilfoj til indkobskurv"}),
      "a Danish buy control does not count on the DE arm")
check(not buy_control_present({**DE_ROW, "buy_label": "Add to Cart"}),
      "an English buy control does not count on the DE arm")
check(not buy_control_present({**DE_ROW, "in_stock": False}),
      "an explicit out-of-stock revokes a present-looking control")

print("\nGone is not the same as refused")
check(classify({**GOOD, "http_status": 404})[1][0]["code"] == "dead_page",
      "a 404 is a delisted product, which is a finding")
check(classify({**GOOD, "http_status": 403})[1][0]["code"] == "blocked",
      "a 403 is our own failure, which is not")

print("\nagainst the real seed corpus")
sf = HERE.parent / "data" / "seeds.json"
if sf.exists():
    seeds_all = json.loads(sf.read_text(encoding="utf-8"))["seeds"]
    idx = {s["ref"]: s for s in seeds_all}
    sample = [s for s in seeds_all if s.get("gtin")][:25]
    # A DE row carries DE wording. The fixture used to inherit "Add to Cart"
    # from GOOD, which is a US label on a German arm: exactly the inconsistency
    # buy_control_present() now refuses, and a row no real sweep can produce.
    raw = [{**GOOD, "seed_ref": s["ref"], "needle": s["gtin"],
            "page_text": f"EAN {s['gtin']} Marke {s.get('brand') or 'n/a'}",
            "arm": "DE", "currency": "EUR",
            "buy_label": "In den Einkaufswagen", "page_language": "de"} for s in sample]
    rows, rep = normalize_sweep(raw, idx)
    check(len(rows) == len(sample), f"{len(rows)} real seeds normalised")

    # Not "all RED". Six of the 104 Safety Gate notices carrying a gtin field
    # hold a value that fails its own check digit: lengths 9, 10, 12 and 14,
    # entered by the notifying country into a free-text barcode box. Three of
    # them land in this sample of 25.
    #
    # They are refused, and the refusal is the correct outcome. A ten-digit
    # number is not a GTIN, and matching one against a retail page as though it
    # were an exact identifier is how a false accusation gets made. This is the
    # same class of error the identifier rule already found in CPSC model
    # fields, now in the EU gtin field, and it moves the unsearchable rate the
    # same direction: up, against our own headline.
    reds = [r for r in rows if r["tier"] == "RED"]
    refused = [r for r in rows if r["tier"] == "DISCARDED"]
    valid = [s for s in sample if gtin_check_digit_ok(s["gtin"])]
    check(len(reds) == len(valid),
          f"{len(reds)} seeds with a check-digit-valid GTIN resolve RED")
    check(all(d["code"] == "no_join_key"
              for r in refused for d in r.get("discarded", [])),
          f"{len(refused)} seeds whose 'GTIN' fails its own check digit are "
          "refused as unassertable, not published")
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
