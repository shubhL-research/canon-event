"""Tests for the RED gate. Standard library only, no pytest required.

Run:  python3 collect/test_adjudicate.py

This is the accusation path, so the tests are written as an adversary rather than
as a author. Every case below is a way the gate could produce a wrong RED, and
the assertion is that it does not. The GTIN check digits are real published
values whose arithmetic can be redone on paper, and the model numbers and hazard
wording are real CPSC values, so no case here can drift into testing the code
against its own behaviour.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from adjudicate import (                                   # noqa: E402
    RED, NOT_FOUND, WITHHELD,
    AMBER, DEAD_PAGE, BLOCKED, NO_JOIN_KEY, IDENTITY_MISMATCH,
    adjudicate, buy_control, currency_agrees, fold,
    find_assertion, gtin_check_digit_ok, needle_is_assertable,
)

FAILURES = []
AT = "2026-08-19T11:00:00Z"


def check(cond, msg):
    if cond:
        print("  ok   " + msg)
    else:
        print("  FAIL " + msg)
        FAILURES.append(msg)


def listing(**kw):
    """A listing that would earn RED, so each test can spoil exactly one thing."""
    base = {
        "page_text": "Besrey Twins Stroller BR C708S lightweight double pushchair",
        "buy_label": "In den Einkaufswagen",
        "in_stock": True,
        "currency": "EUR",
        "http": 200,
        "ships_from": "Amazon",
    }
    base.update(kw)
    return base


# ------------------------------------------------------------------ GTIN maths
print("GTIN check digits, checkable on paper")

# 4006381333931 is a published EAN-13. Weighted sum of the body is 89, so the
# check digit must be (10 - 89 mod 10) mod 10 = 1, which is what it carries.
check(gtin_check_digit_ok("4006381333931"), "a real EAN-13 validates")
check(not gtin_check_digit_ok("4006381333930"), "the same EAN with a wrong check digit fails")

# 036000291452 is the textbook UPC-12. Body sums to 58, so the check digit is 2.
check(gtin_check_digit_ok("036000291452"), "a real UPC-12 validates")
check(gtin_check_digit_ok("0 36000 29145 2"), "separators in a GTIN are tolerated")
check(not gtin_check_digit_ok("40063813339"), "a GTIN of illegal length fails")
check(not gtin_check_digit_ok(None), "an absent GTIN fails rather than raising")


# ------------------------------------------------------- what may assert identity
print("\nWhich identifiers are allowed to assert identity")

check(needle_is_assertable("BR-C708S"), "a model number containing letters is assertable")
check(needle_is_assertable("PAPABLIC61A"), "a real CPSC model value is assertable")
# The bare-numeric refusal is the single most important line in the module: these
# are real CPSC model values that collide with prices and review counts.
check(not needle_is_assertable("113210"), "a bare numeric SKU is NOT assertable as a model")
check(not needle_is_assertable("13110003"), "a longer bare numeric SKU is still not assertable")
check(not needle_is_assertable("2024"), "a model year is not assertable")
check(not needle_is_assertable("W52"), "a token below the length floor is not assertable")
check(needle_is_assertable("4006381333931", is_gtin=True),
      "a valid GTIN is assertable even though it is all digits")
check(not needle_is_assertable("4006381333930", is_gtin=True),
      "an invalid GTIN is not assertable, digits notwithstanding")


# ------------------------------------------------------------------- folding
print("\nFolding, so real reformatting survives and nothing else does")

check(fold("BR-C708S") == fold("BR C708S") == "BRC708S", "hyphen and space fold alike")
check(fold(None) == "", "an absent value folds to empty rather than raising")
found = find_assertion("BR-C708S", "Besrey Twins Stroller BR C708S double")
check(found is not None, "a hyphenated model is found in space-separated page text")
check(found["needle"] == "BR-C708S", "the needle stored is the notice's own value")
check("BR C708S" in found["context"], "the context quotes the page's real wording, not the folded form")
check(find_assertion("BR-C708S", "Besrey Twins Stroller BR C708T double") is None,
      "a one-character difference does not match")
check(find_assertion("113210", "crib 113210 panel") is None,
      "a bare numeric needle is refused even when the page contains it")


# --------------------------------------------------------------- buy controls
print("\nBuy controls, read in the marketplace's own language")

check(buy_control({"buy_label": "In den Einkaufswagen"}, "DE")["present"],
      "the German add-to-cart label counts as a buy control")
check(buy_control({"buy_label": "Add to Cart"}, "US")["present"],
      "the US label counts on the US arm")
check(not buy_control({"buy_label": "In den Einkaufswagen"}, "US")["present"],
      "a German label does not count on the US arm")
check(not buy_control({"buy_label": "Currently unavailable"}, "DE")["present"],
      "an unavailability notice is not a buy control")
# A disabled control still renders. Presence without stock is not a way to buy.
check(not buy_control({"buy_label": "In den Einkaufswagen", "in_stock": False}, "DE")["present"],
      "an explicit out-of-stock revokes a present-looking control")
check("in_stock" not in buy_control({"buy_label": "Add to Cart"}, "US"),
      "an unobserved in_stock is omitted, not defaulted to False")


# ------------------------------------------------------------------- currency
print("\nCurrency as proof of which market answered")

check(currency_agrees({"currency": "EUR"}, "DE") == (True, "EUR"), "EUR agrees with the DE arm")
check(currency_agrees({"currency": "USD"}, "DE") == (False, "USD"), "USD contradicts the DE arm")
check(currency_agrees({}, "DE") == (True, None), "an absent symbol is not a contradiction")


# ------------------------------------------------------------------ the verdict
print("\nThe verdict, one spoiled condition at a time")

notice = {"model": "BR-C708S", "gtin": None}

r = adjudicate(notice, listing(), "DE", AT)
check(r["verdict"] == RED, "both conditions holding on a proven market earns RED")
check(r["discard"] is None, "a RED row carries no discard reason")
check(r["evidence"]["assertion"]["needle"] == "BR-C708S", "the RED row carries its assertion")
check(r["evidence"]["buy_control"]["label"] == "In den Einkaufswagen",
      "the RED row quotes the buy control verbatim")
check(r["evidence"]["currency"] == "EUR", "the RED row records the symbol that proved the market")

# The thesis. A block is our failure, and reporting it as absence would convert
# that failure into a clean bill of health for a product still on sale.
for code in (403, 429, 503):
    r = adjudicate(notice, listing(http=code), "DE", AT)
    check(r["verdict"] == WITHHELD and r["discard"]["code"] == BLOCKED,
          "a %d WITHHOLDS the verdict and never reports NOT_FOUND" % code)

for code in (404, 410):
    r = adjudicate(notice, listing(http=code), "DE", AT)
    check(r["verdict"] == NOT_FOUND and r["discard"]["code"] == DEAD_PAGE,
          "a %d is a genuine absence" % code)

r = adjudicate(notice, listing(page_text=""), "DE", AT)
check(r["verdict"] == WITHHELD, "an empty page body withholds rather than reporting absence")

# The geo guard. Every field is well-formed; only the currency betrays that the
# request egressed through the wrong country.
r = adjudicate(notice, listing(currency="USD"), "DE", AT)
check(r["verdict"] == WITHHELD and "exit country unproven" in r["discard"]["reason"],
      "a USD storefront on the DE arm withholds instead of reddening")

r = adjudicate(notice, listing(currency=None), "DE", AT)
check(r["verdict"] == WITHHELD, "an unproven exit country withholds under require_currency_proof")
r = adjudicate(notice, listing(currency=None), "DE", AT, require_currency_proof=False)
check(r["verdict"] == RED, "the proof requirement is explicit and can be relaxed deliberately")

# Identity confirmed, nothing to click. The system working, not a hazard.
r = adjudicate(notice, listing(buy_label="Currently unavailable"), "DE", AT)
check(r["verdict"] == NOT_FOUND and r["discard"]["code"] == AMBER,
      "identity without an active buy control is AMBER, not RED")
check(r["evidence"] is not None, "an AMBER row still carries its evidence for review")

# The ASIN-substitution case: a living page, a working buy button, wrong product.
r = adjudicate(notice, listing(page_text="Besrey Twins Stroller BR C999X double"), "DE", AT)
check(r["verdict"] == NOT_FOUND and r["discard"]["code"] == IDENTITY_MISMATCH,
      "a live buy control on the WRONG product does not earn RED")

r = adjudicate({"model": "113210", "gtin": None}, listing(page_text="crib 113210"), "DE", AT)
check(r["discard"]["code"] == NO_JOIN_KEY,
      "a notice whose only identifier is unassertable is NO_JOIN_KEY, not a mismatch")

# GTIN is preferred when both are present, because it is the stronger claim.
r = adjudicate({"model": "BR-C708S", "gtin": "4006381333931"},
               listing(page_text="Stroller EAN 4006381333931 BR C708S"), "DE", AT)
check(r["verdict"] == RED and r["evidence"]["assertion"]["needle"] == "4006381333931",
      "when a notice carries both, the accusation rests on the GTIN")


# ------------------------------------------------------------------- absence
print("\nAbsence is preserved, never filled")

r = adjudicate(notice, {"page_text": "Stroller BR C708S", "buy_label": "In den Einkaufswagen",
                        "currency": "EUR"}, "DE", AT)
ev = r["evidence"]
check("http" not in ev, "an unobserved http status is omitted rather than zeroed")
check("viewport" not in ev, "an unobserved viewport is omitted")
check("sha256" not in ev and "trace" not in ev and "job_id" not in ev,
      "unobserved provenance keys are omitted rather than nulled")
check("ships_from" not in ev["buy_control"], "an unobserved seller is omitted")

print("\n" + ("%d FAILURES" % len(FAILURES) if FAILURES else "all adjudication tests passed"))
sys.exit(1 if FAILURES else 0)
