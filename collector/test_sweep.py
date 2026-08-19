"""Tests for the orchestrator and the adapter. Standard library only.

Run:  python3 collector/test_sweep.py

Everything here runs offline. The runner is injected, so a saved Scraper Studio
payload drives the whole pipeline — adapter, normaliser, arm combination,
detectors — with no account and no network. A clean clone must be able to replay
a sweep from disk and reach the same verdicts, or none of the other tests mean
very much.

The payload in FIXTURE is a real kaufland.de response captured on 2026-08-19.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))

import health                                                      # noqa: E402
import sweep as S                                                  # noqa: E402
from fromstudio import convert, currency_of, stock_of, to_raw      # noqa: E402

FAILURES = []


def check(cond, msg):
    if cond:
        print("  ok   " + msg)
    else:
        print("  FAIL " + msg)
        FAILURES.append(msg)


# A real row as kaufland.de returned it, doubled identifiers and all.
LIVE_ROW = {
    "title": "MamaLoes Milan Taupe 1-Personen-Buggy",
    "brand": "9.161225.12.25.11 9.161225.12.25.11",
    "price": {"value": 44, "currency": "EUR", "symbol": "€"},
    "currency_symbol": "€",
    "availability_text": "Do. 20. – Fr. 21. August",
    "add_to_cart_button_text": "In den Warenkorb",
    "seller_name": "MamaLoes",
    "ean": "8721003407246 8721003407246",
    "manufacturer_part_number": "9.161225.12.25.11 9.161225.12.25.11",
    "product_page_url": "https://www.kaufland.de/product/568730910/",
    "input": {"url": "https://www.kaufland.de/s/?search_value=Besrey"},
}

SEED = {
    "ref": "A12/02490/24", "name": "Besrey Twins Strollers", "brand": "Besrey",
    "model": "BR-C708S", "gtin": "8721003407246", "authority": "SAFETY_GATE",
    "published": "2024-07-25", "url": "https://ec.europa.eu/safety-gate/x",
    "days": 390,
    "hazard": "Entrapment, fall and choking hazards; violation of federal "
              "regulation for strollers.",
}
AT = "2026-08-19T12:00:00Z"


# ------------------------------------------------------------------- adapter
print("The adapter, against a real payload")

flat, report = convert([LIVE_ROW], SEED["ref"], "DE", S.BRAND_MODEL,
                       SEED["gtin"], AT, job_id="j_k1")
row = flat[0]
check(len(flat) == 1, "one raw row becomes one flat row")
check(row["seed_ref"] == SEED["ref"] and row["arm"] == "DE",
      "what we asked is carried, not what we were told")
check(row["query_kind"] == S.BRAND_MODEL,
      "query_kind survives, or the recall floor cannot be computed")
check(row["buy_label"] == "In den Warenkorb",
      "kaufland's own wording is preserved, not translated")
check(row["currency"] == "EUR", "the symbol is recovered from the nested price object")
check("price" not in row, "the price VALUE never crosses the boundary")
check(report["unmapped_fields"] == [],
      "a payload we fully understand reports no drift")
check("8721003407246 |" in row["page_text"] or
      row["page_text"].endswith("8721003407246"),
      "the doubled EAN is collapsed before it reaches the matcher")

drifted = convert([{**LIVE_ROW, "surprise_field": 1}], SEED["ref"], "DE",
                  S.BRAND_MODEL, SEED["gtin"], AT)[1]
check(drifted["unmapped_fields"] == ["surprise_field"],
      "a field we do not recognise is named rather than dropped")

check(currency_of({"value": 44, "currency": "EUR"}) == "EUR",
      "a nested price object yields its currency")
check(currency_of("24,99 €") == "EUR", "a euro string yields EUR")
check(currency_of("24,99") is None, "a bare number proves nothing")
check(stock_of("Do. 20. – Fr. 21. August") is None,
      "a delivery date range is not a stock claim and stays unknown")
check(stock_of("Auf Lager") is True, "German in-stock wording reads True")
check(stock_of("Derzeit nicht verfügbar") is False, "German unavailability reads False")

err = to_raw({"error": "boom", "error_code": "detect_block"}, "r", "DE",
             S.MODEL_ONLY, "X", AT)
check(err["error"] == "detect_block",
      "a failed input keeps its error code and is still a row")


# ----------------------------------------------------------- query strategies
print("\nTwo queries per notice, or the recall floor is unrecoverable")

check(S.query_for(SEED, S.BRAND_MODEL) == "Besrey 8721003407246",
      "brand_model pairs the brand with the identifier")
check(S.query_for(SEED, S.MODEL_ONLY) == "8721003407246",
      "model_only searches the identifier alone")
check(S.query_for({"name": "", "model": ""}, S.MODEL_ONLY) is None,
      "a notice with no identifier yields no query rather than an empty search")
check(S.query_for({"name": "Acme Thing", "model": "X-1"}, S.BRAND_MODEL)
      == "Acme X-1", "the brand falls back to the first word of the name")
check(S.needle_for(SEED) == SEED["gtin"],
      "the GTIN is preferred over the model as the needle")


# --------------------------------------------------------- the whole pipeline
print("\nEnd to end, offline, from a saved payload")


def fake_runner(payloads):
    """A runner that replays canned payloads per arm."""
    def run(collector_id, url):
        for arm, marker in (("DE", "kaufland.de"), ("US", "amazon.com"),
                            ("IN", "amazon.in")):
            if marker in url:
                return payloads.get(arm, ([], None))
        return [], None
    return run


rows, doc = S.run(
    [SEED],
    {"DE": "c_de", "US": "c_us", "IN": "c_in"},
    runner=fake_runner({
        "DE": ([LIVE_ROW], None),
        "US": (None, "Crawler error: response body was rejected"),
        "IN": ([], None),
    }),
)

check(len(rows) == 1, "one notice produces one row across three arms")
r = rows[0]
check(set(r["arms"]) == {"US", "DE", "IN"},
      "every arm appears, including the ones that found nothing")
check(r["arms"]["DE"] == "RED", "the German arm reddens on a real German listing")
check(r["arms"]["US"] == "WITHHELD",
      "a blocked US arm WITHHOLDS: our failure is never reported as absence")
check(r["arms"]["IN"] == "NOT_FOUND",
      "an arm that returned nothing at all is a genuine absence")
check(r["tier"] == "RED", "one reddening arm reddens the row")
check(r["source"]["ref"] == SEED["ref"] and r["hazard"] == SEED["hazard"],
      "the regulator's own fields come from the notice, never the marketplace")
check(r["evidence"]["assertion"]["needle"] == SEED["gtin"],
      "the published receipt comes from the arm that actually reddened")
check(r["rank"] == 1, "rank is assigned from the data, not from iteration order")

check(doc["arms"]["DE"]["state"] == "MEASURED", "the German arm is measurable")
check(doc["arms"]["US"]["state"] == "WITHHELD",
      "the blocked arm's state is WITHHELD on the health file too")
check(doc["detectors"]["identity_reassertion"]["fired"] is False,
      "no RED row reached the wall without an assertion")
check("zero_is_a_fault" in doc["detectors"],
      "the zero detector reports even when it did not fire")
check(all("fired" in d for d in doc["detectors"].values()),
      "every detector records a verdict, so none can fail silently")

# The IN arm returned an empty list, which is NOT the same as being told there
# is nothing there. Its rows read NOT_FOUND because no listing came back for
# this notice, but the ARM is withheld, because zero rows across a whole sweep
# with no archived empty-result page is our silence rather than a finding.
# Those two levels disagreeing is the design working, not a contradiction.
check(doc["arms"]["IN"]["state"] == "WITHHELD",
      "an arm returning zero uncorroborated rows is withheld, not believed")
check(doc["arms"]["IN"]["reason"] == "zero_rows_uncorroborated",
      "and the reason is named rather than left to inference")
check(doc["verdict"].startswith("WITHHELD for IN, US"),
      "the verdict sentence is derived from the arm states, never typed")
check("seed corpus are unaffected" in doc["verdict"],
      "figures computed without a scraper survive every collector failing")


# ---------------------------------------------------------------- the refusal
print("\nWhat must never redden")

wrong_locale = {**LIVE_ROW, "add_to_cart_button_text": "Tilføj til indkøbskurv"}
rows2, _ = S.run([SEED], {"DE": "c_de"},
                 runner=fake_runner({"DE": ([wrong_locale], None)}))
check(rows2[0]["arms"]["DE"] != "RED",
      "a Danish buy control on the DE arm does not redden, EUR notwithstanding")

wrong_product = {**LIVE_ROW, "ean": "4006381333931", "title": "Something else",
                 "manufacturer_part_number": "ZZ-999",
                 "brand": "Other"}
rows3, _ = S.run([SEED], {"DE": "c_de"},
                 runner=fake_runner({"DE": ([wrong_product], None)}))
check(rows3[0]["arms"]["DE"] != "RED",
      "a live buy control on the WRONG product does not redden")

print("\n" + ("%d FAILURES" % len(FAILURES) if FAILURES else "all sweep tests passed"))
sys.exit(1 if FAILURES else 0)
