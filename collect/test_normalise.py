"""Tests for the platform-to-contract boundary. Standard library only.

Run:  python3 collect/test_normalise.py

The interesting cases here are all absence cases. Anyone can test that a present
field maps across; the failures that would actually hurt this project are the
ones where a field the collector could not fill arrives as a default and gets
published as a measurement. So most of what follows asserts that a key is NOT
there.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from normalise import (                                    # noqa: E402
    currency_of, mapped_keys, normalise, normalise_job,
    pick, searchable_text, stock_of,
)

FAILURES = []


def check(cond, msg):
    if cond:
        print("  ok   " + msg)
    else:
        print("  FAIL " + msg)
        FAILURES.append(msg)


# ------------------------------------------------------------------- aliasing
print("Aliasing, because the AI names the fields, not us")

check(pick({"model_number": "BR-C708S"}, "model") == "BR-C708S",
      "model_number is read as model")
check(pick({"manufacturer_part_number": "BR-C708S"}, "model") == "BR-C708S",
      "manufacturer_part_number is read as model")
check(pick({"add_to_cart_text": "In den Einkaufswagen"}, "buy_label") == "In den Einkaufswagen",
      "add_to_cart_text is read as the buy label")
check(pick({"model": "A", "model_number": "B"}, "model") == "A",
      "the first alias listed wins when a row carries several")
check(pick({}, "model") is None, "an absent field yields None")
check(pick({"model": ""}, "model") is None, "an empty string is not an observation")
check(pick({"model": None}, "model") is None, "an explicit null is not an observation")
check(pick({"model": "", "model_number": "B"}, "model") == "B",
      "an empty preferred alias falls through to a populated one")


# ------------------------------------------------------------------- currency
print("\nCurrency, the only in-page proof of which market answered")

check(currency_of("€24,99") == "EUR", "a euro symbol reads as EUR")
check(currency_of("$24.99") == "USD", "a dollar symbol reads as USD")
check(currency_of("₹1,499") == "INR", "a rupee symbol reads as INR")
check(currency_of("EUR") == "EUR", "an ISO code reads too")
check(currency_of(None, "24,99 €") == "EUR", "the first readable of several inputs wins")
check(currency_of("24,99") is None, "a bare number proves nothing and yields None")
check(currency_of(None, None) is None, "nothing observed yields None, not a guess")
check(currency_of("£24.99") is None,
      "an unmeasured market is NOT coerced into one of ours")


# ---------------------------------------------------------------------- stock
print("\nStock, from the marketplace's own wording")

check(stock_of("In Stock") is True, "in-stock English reads True")
check(stock_of("Auf Lager") is True, "in-stock German reads True")
check(stock_of("Currently unavailable") is False, "unavailability reads False")
check(stock_of("Derzeit nicht verfügbar") is False, "German unavailability reads False")
check(stock_of("Only 3 left in stock - order soon") is True,
      "a low-stock sentence still reads True")
# The ordering trap: this sentence contains "in stock" inside a negation.
check(stock_of("Temporarily out of stock") is False,
      "out-of-stock is matched before in-stock, so a negation is not misread")
check(stock_of("Ships in 2-3 weeks") is None, "unrecognised wording stays unknown")
check(stock_of(None) is None, "absent availability stays unknown")
check(stock_of("") is None, "empty availability stays unknown")


# ------------------------------------------------------------------- haystack
print("\nThe identity haystack")

hay = searchable_text({"title": "Besrey Stroller", "model_number": "BR-C708S"})
check("Besrey Stroller" in hay and "BR-C708S" in hay, "title and model both reach the haystack")
# Folding strips punctuation, so the joiner must not let two values fuse into a
# match that exists in neither of them.
fused = searchable_text({"title": "Model BR-C708", "brand": "S-Line"})
from adjudicate import find_assertion                       # noqa: E402
check(find_assertion("BR-C708S", fused) is None,
      "two adjacent fields cannot fuse into a false identifier match")


# ------------------------------------------------------------------ normalise
print("\nNormalising a full row")

raw = {
    "product_title": "  Besrey  Twins Stroller  ",
    "model_number": "BR-C708S",
    "price": "249,99 €",
    "availability": "Auf Lager",
    "add_to_cart_text": "In den Einkaufswagen",
    "seller_name": "Besrey Official",
    "product_url": "https://www.amazon.de/dp/B08XYZ",
}
n = normalise(raw, "DE", http=200, job_id="j_test")

check(n["title"] == "Besrey Twins Stroller", "whitespace in the title is collapsed")
check(n["currency"] == "EUR", "the currency is recovered from the price string")
check("price" not in n and "price_raw" not in n,
      "the price VALUE never crosses the boundary, only its symbol")
check(n["in_stock"] is True, "availability becomes a boolean")
check(n["buy_label"] == "In den Einkaufswagen", "the buy label is kept in the page's own language")
check(n["ships_from"] == "Besrey Official",
      "a named seller stands in for an unnamed fulfiller")
check(n["http"] == 200 and n["job_id"] == "j_test", "provenance is carried through")
check(n["arm"] == "DE", "the arm is stamped on the listing")

# Absence, which is the whole point.
sparse = normalise({"product_title": "Something"}, "DE")
check("currency" not in sparse, "an unobserved currency is absent, not None and not USD")
check("in_stock" not in sparse, "unobserved stock is absent, not False")
check("buy_label" not in sparse, "an unobserved buy control is absent, not empty string")
check("ships_from" not in sparse, "an unobserved seller is absent")
check("http" not in sparse, "an unpassed http status is absent, not 0")

# Strangers are counted, never dropped.
drifted = normalise({"product_title": "X", "surprise_field": 1, "another_one": 2}, "DE")
check(drifted["unmapped"] == ["another_one", "surprise_field"],
      "unrecognised fields are recorded so schema drift is visible")
check("unmapped" not in normalise({"product_title": "X"}, "DE"),
      "a clean row carries no unmapped key at all")


# ---------------------------------------------------------------------- jobs
print("\nWhole job payloads, in whatever envelope the CLI used")

rows = [
    {"product_title": "A", "price": "10 €", "add_to_cart_text": "In den Einkaufswagen"},
    {"product_title": "B"},
]
for envelope, label in (
    (rows, "a bare list"),
    ({"data": rows}, "a {data: [...]} envelope"),
    ({"results": rows}, "a {results: [...]} envelope"),
):
    listings, report = normalise_job(envelope, "DE", job_id="j_1")
    check(len(listings) == 2, "%s yields both rows" % label)

listings, report = normalise_job({"data": rows}, "DE", job_id="j_1")
check(report["rows_in"] == 2 and report["rows_normalised"] == 2, "the report counts rows")
check(report["with_currency"] == 1, "the report counts how many rows proved their market")
check(report["with_buy_label"] == 1, "the report counts how many rows had a buy control")
check(report["unmapped_fields"] == [], "a clean job reports no drift")

_, drift_report = normalise_job([{"product_title": "A", "new_field": 1}], "DE")
check(drift_report["unmapped_fields"] == ["new_field"],
      "job-level drift is aggregated for the health file")

check(normalise_job({}, "DE")[0] == [], "an unrecognisable payload yields no rows, not a crash")
check(normalise_job(None, "DE")[0] == [], "a null payload yields no rows, not a crash")
single, _ = normalise_job({"product_title": "Solo", "price": "5 €"}, "DE")
check(len(single) == 1, "a single row returned bare is still found")

print("\n" + ("%d FAILURES" % len(FAILURES) if FAILURES else "all normaliser tests passed"))
sys.exit(1 if FAILURES else 0)
