"""Is this recall notice searchable at all?

WHY THIS FILE EXISTS
--------------------
UNSEARCHABLE RATE is the floor number: it is computed from free government APIs,
no scraper can contaminate it, and it survives every collector failing. Its
accuracy is therefore load-bearing in a way nothing else here is.

The rule the plan started with was: "alphanumeric, contains a digit, length >= 4,
not a bare year." Running it against real CPSC notices shows it is wrong in a
direction that hurts us. These are all real values from the model field, pulled
16 Aug 2026, and every one of them passes that rule while being useless to search:

    Serial numbers starting with "M2"      Batch numbers: 10 23, 12 23, 02 24
    Sizes 2T-6T, 7/8, 9/10                 expiration dates 01/2026-10/2026
    2024, 2025, 2026 model years           Size Small (S)
    Lot numbers: 0066J4, 0065J4            batch number 26082

Counting those as searchable inflates the searchable population, which DEFLATES
the unsearchable rate. The bug argues against our own headline, so fixing it can
only help, and shipping it unfixed would be the kind of error a judge finds by
reading twenty notices.

THE DESIGN, AND WHY THE MODEL IS SECOND
---------------------------------------
The rule is primary and it is the thing that decides. It is deterministic,
inspectable, and a human can check any single verdict in five seconds.

A language model runs a SECOND, independent pass over the same text. It never
overrides the rule. Its only job is to disagree, and every disagreement is
written to a ledger for a human to adjudicate against the golden set. What gets
published is the adjudicated rule plus the disagreement rate.

That ordering is the whole point. An LLM deciding searchability directly would
put a black box under a headline number, in a project whose entire argument is
that every claim is checkable by eye. A model that only ever raises its hand
adds recall to our error-finding without touching the evidence chain.

The model call is injected, so this module runs, and is fully tested, with no
API key and no network. A clean clone must work offline.

Standard library only.
"""

import re

# --------------------------------------------------------------------- verdicts

SEARCHABLE = "searchable"
UNSEARCHABLE = "unsearchable"

# Patterns that mean "this is not a product identifier", checked BEFORE the
# permissive alphanumeric test. Order matters: these are all rejections.
DISQUALIFIERS = [
    ("serial_range", re.compile(r"\bserial\s*(numbers?|nos?\.?)\b", re.I)),
    ("batch_code", re.compile(r"\bbatch\s*(numbers?|codes?|nos?\.?)\b", re.I)),
    ("lot_code", re.compile(r"\blot\s*(numbers?|codes?|nos?\.?)\b", re.I)),
    ("date_code", re.compile(r"\b(expiration|expiry|manufactured|production)\b", re.I)),
    ("model_year", re.compile(r"\bmodel\s*years?\b", re.I)),
    ("clothing_size", re.compile(r"\bsizes?\b", re.I)),
    ("date_range", re.compile(r"\b\d{1,2}/\d{4}\s*[-–]\s*\d{1,2}/\d{4}\b")),
    ("bare_years", re.compile(r"^\s*(19|20)\d{2}(\s*,\s*(19|20)\d{2})*\s*$")),
    ("dimensions", re.compile(r"\d+\s*(\"|inch|cm|mm)\s*[wWhHdD]\b")),
    ("not_specified", re.compile(r"^\s*(not specified|n/?a|none|various|multiple)\s*$", re.I)),
    # A CAPACITY IS NOT A MODEL NUMBER, and this one reached the wall.
    #
    # CPSC 26537 recalls "Kitchen HQ Thermal Insulated Bowls" and publishes
    # "10-cup" in the model field. It has letters, it has digits, it is four
    # characters, so STRONG accepted it and the sweep went looking for "10-cup"
    # on three marketplaces. It found a 10 Cup Programmable Coffee Maker and
    # adjudicated it RED against a recall about bowls catching fire.
    #
    # The rule the accepting branch states about itself is "distinctive enough
    # that a marketplace search returns the product rather than a category". A
    # capacity is the definition of a category.
    # A CAPACITY IS NOT A MODEL NUMBER, and this one reached the wall.
    #
    # CPSC 26537 recalls "Kitchen HQ Thermal Insulated Bowls" and publishes
    # "10-cup" in the model field. It has letters, digits and four characters,
    # so the accepting branch took it and the sweep searched three marketplaces
    # for "10-cup". It found a 10 Cup Programmable Coffee Maker and adjudicated
    # it RED against a recall about bowls catching fire. That branch claims the
    # token is "distinctive enough that a marketplace search returns the product
    # rather than a category", and a capacity is the definition of a category.
    #
    # SINGLE-LETTER UNITS REQUIRE A SEPARATOR. The first version of this pattern
    # allowed the unit to sit flush against the number, so it read the trailing
    # W of "11064W" as watts and disqualified a real model number, silently
    # dropping CPSC 26529 (Broqixin Pool Drain Covers) out of the corpus. A rule
    # written to stop a false RED had started causing false NOT-SEARCHABLE,
    # which is the quieter and worse direction.
    ("capacity", re.compile(
        r"^\s*\d+(\.\d+)?\s*[-\s]\s*(cup|cups|qt|quart|quarts|litre|litres|liter|liters|ml|oz|ounce|ounces|"
        r"gal|gallon|gallons|lb|lbs|pound|pounds|kg|gram|grams|pack|count|piece|"
        r"pieces|inch|inches|foot|feet|watt|watts|volt|volts|amp|amps|l|g|w|v|"
        r"m|ct|pk|pc|pcs|in|ft|mm|cm|ah|mah)\s*$", re.I)),
    # Multi-character units may sit flush against the number: "500ml", "12pack".
    ("capacity_flush", re.compile(
        r"^\s*\d+(\.\d+)?\s*(cups?|quarts?|litres?|liters?|ml|ounces?|gallons?|pounds?|grams?|"
        r"packs?|pieces?|inches|watts?|volts?|amps?|mah)\s*$", re.I)),
    # Battery designations name a cell type, not a product a shopper can find:
    # searching CR2032 returns every CR2032 on the marketplace.
    ("battery_type", re.compile(
        r"^\s*(cr|lr|sr|aa|aaa|9v)\s*-?\s*\d{0,4}\s*$", re.I)),
]

# A token that survives as an actual identifier.
STRONG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{2,}$")
GTIN = re.compile(r"^\d{8,14}$")


def gtin_check_digit_ok(raw):
    """Validate a GTIN-8/12/13/14 modulo-10 check digit.

    Mirrors collector/normalize.py so the same arithmetic decides searchability
    at seed time and identity at adjudication time. If these two ever disagree,
    a notice can be counted as searchable and then be unassertable, which is a
    contradiction the wall has no way to render.
    """
    digits = re.sub(r"\D", "", "" if raw is None else str(raw))
    if len(digits) not in (8, 12, 13, 14):
        return False
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(c) * (3 if i % 2 == 0 else 1)
                for i, c in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def classify(model, gtin=None, product_name=""):
    """Decide whether a notice carries a machine-searchable identifier.

    Returns a verdict dict. `kind` names the mechanism so the WHAT WE DID NOT SEE
    panel can break the unsearchable population down by cause rather than
    reporting one opaque count.
    """
    if gtin and GTIN.match(str(gtin).strip()):
        g = str(gtin).strip()
        # Shape is not validity. A GTIN carries a modulo-10 check digit, and a
        # number that fails it is either a typo in the notice or not a GTIN at
        # all. Accepting it on digit-count alone would count a broken barcode as
        # searchable and inflate our own coverage.
        #
        # This check used to live in collector/publish.py, which meant two rules
        # for one question and two different published rates. There is one rule
        # and it is here. Six EU alerts fail it.
        if not gtin_check_digit_ok(g):
            return _v(UNSEARCHABLE, "gtin_check_digit_failed", g,
                      "The barcode fails its own modulo-10 check digit, so it is "
                      "either mistyped in the notice or is not a GTIN.")
        return _v(SEARCHABLE, "gtin", g,
                  "A GTIN is globally unique and survives a marketplace search intact.")

    raw = "" if model is None else str(model).strip()
    if not raw:
        return _v(UNSEARCHABLE, "absent", None,
                  "The notice named no identifier at all. The matcher cannot form a query.")

    for kind, pat in DISQUALIFIERS:
        if pat.search(raw):
            return _v(UNSEARCHABLE, kind, raw,
                      f"Recognised as a {kind.replace('_', ' ')}, which identifies a "
                      f"production run rather than a product a shopper can search for.")

    # Multi-value model fields ("A, B, C") are searchable if any single token is.
    tokens = [t.strip() for t in re.split(r"[,;]| or ", raw) if t.strip()]
    for tok in tokens:
        has_alpha = any(c.isalpha() for c in tok)
        has_digit = any(c.isdigit() for c in tok)
        if has_alpha and has_digit and len(tok) >= 4 and STRONG.match(tok):
            return _v(SEARCHABLE, "model_token", tok,
                      "Mixed letters and digits at length four or more: distinctive "
                      "enough that a marketplace search returns the product rather "
                      "than a category.")

    for tok in tokens:
        if tok.isdigit() and len(tok) >= 4:
            return _v(UNSEARCHABLE, "bare_numeric_sku",
                      tok, "A bare numeric SKU collides with unrelated products across "
                           "marketplaces. Searching it returns noise, not the product.")

    return _v(UNSEARCHABLE, "too_generic", raw,
              "No token is distinctive enough to search: letters-only codes and "
              "short fragments match everything.")


def _v(verdict, kind, token, why):
    return {"verdict": verdict, "kind": kind, "token": token, "why": why,
            "decided_by": "rule"}


# ------------------------------------------------------------- second opinion

SECOND_OPINION_PROMPT = """You are auditing a product-recall notice for one thing only.

Question: does this notice contain an identifier that a shopper could type into a
marketplace search box and land on THIS EXACT product?

A serial-number range, batch code, lot code, production date, clothing size, or
model year is NOT such an identifier. A distinctive model number or a GTIN is.

Notice product name: {name}
Notice model field: {model}
Notice GTIN field: {gtin}

Answer with exactly one word, searchable or unsearchable, then a second line
giving your reason in under fifteen words."""


def second_opinion(model, gtin, product_name, call_model):
    """Run an independent model pass. `call_model` is injected.

    `call_model(prompt) -> str`. Anything callable works: a real API client, a
    local model, or a stub. Injecting it keeps this module runnable and testable
    with no key and no network, which the clean-clone check requires.
    """
    prompt = SECOND_OPINION_PROMPT.format(
        name=product_name or "(none given)",
        model=model if model else "(empty)",
        gtin=gtin if gtin else "(empty)")
    raw = (call_model(prompt) or "").strip()
    head = raw.split("\n")[0].strip().lower()
    reason = raw.split("\n")[1].strip() if "\n" in raw else ""
    if head.startswith("searchable"):
        verdict = SEARCHABLE
    elif head.startswith("unsearchable"):
        verdict = UNSEARCHABLE
    else:
        verdict = None  # unparseable: counts as no opinion, never as agreement
    return {"verdict": verdict, "why": reason, "decided_by": "model", "raw": raw}


def adjudicate(notices, call_model=None):
    """Score the rule over a corpus and, if a model is supplied, log disagreements.

    The rule always decides. The model only ever produces an entry in the ledger.
    What gets published is the rule's rate plus the disagreement rate, so a reader
    knows how much the two passes argued.
    """
    results, disagreements = [], []
    for n in notices:
        model_field = n.get("model")
        gtin = n.get("gtin")
        name = n.get("name", "")
        ruling = classify(model_field, gtin, name)
        entry = {"ref": n.get("ref"), "name": name, "model": model_field,
                 "gtin": gtin, "rule": ruling}

        if call_model is not None:
            other = second_opinion(model_field, gtin, name, call_model)
            entry["model_pass"] = other
            if other["verdict"] and other["verdict"] != ruling["verdict"]:
                entry["needs_adjudication"] = True
                disagreements.append(entry)
        results.append(entry)

    n_total = len(results)
    n_unsearchable = sum(1 for r in results if r["rule"]["verdict"] == UNSEARCHABLE)
    by_kind = {}
    for r in results:
        if r["rule"]["verdict"] == UNSEARCHABLE:
            by_kind[r["rule"]["kind"]] = by_kind.get(r["rule"]["kind"], 0) + 1

    return {
        "n": n_total,
        "unsearchable": n_unsearchable,
        "rate": round(n_unsearchable / n_total, 4) if n_total else None,
        "by_kind": by_kind,
        "second_opinion_run": call_model is not None,
        "disagreements": len(disagreements),
        "disagreement_rate": (round(len(disagreements) / n_total, 4)
                              if n_total and call_model is not None else None),
        "ledger": disagreements,
        "note": ("The rule decides. The model's only power is to flag a case for human "
                 "adjudication against the golden set. Published figures are the rule's, "
                 "with the disagreement rate stated alongside so a reader knows how "
                 "contested the classification was."),
    }
