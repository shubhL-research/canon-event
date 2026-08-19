"""Does this listing earn a RED verdict?

WHY THIS FILE EXISTS
--------------------
Everything else in this project measures. This file is the only place that
ACCUSES. A RED row is a public claim that a named seller is still shipping a
product a government recalled for burning or choking people, and it names a
listing that a human can open. The cost of a false positive is therefore not a
worse f-score, it is a wrong accusation against an identifiable party.

So the gate is deliberately narrow and it is deliberately dumb. Two conditions,
both checked against the FETCHED PRODUCT PAGE and nothing else:

  1. The exact model number or GTIN is re-asserted from that page's own text.
  2. An active buy control is present on that same page.

THE MISTAKE THIS GUARDS
-----------------------
Amazon substitutes ASINs on stale URLs. Ask for a delisted product and you are
quietly handed a different, living one. A search result URL, a canonical link
and a redirect target all agree with each other while pointing at the wrong
product. Only the page body disagrees.

Without re-assertion, a live buy button on the WRONG product scores as a hazard
still on sale. That is the worst mistake this system can make: it is the one
that is both maximally damaging and maximally invisible, because every field in
the row looks right.

WHY THE NEEDLE RULES ARE STRICTER THAN "SUBSTRING"
--------------------------------------------------
`extract/identifier.py` already establishes that many real CPSC model values are
useless to search: batch codes, sizes, model years, bare numeric SKUs. The same
values are also unsafe to MATCH. "113210" appears on an Amazon page as a price,
a review count, a dimension in millimetres, and an unrelated part number. A
bare-numeric substring hit is not evidence of identity, so this file refuses to
assert identity on one unless it arrives as a GTIN with a valid check digit.

That refusal costs us recall. It is the correct trade: an AMBER row we shown and
excluded from the statistics is a survivable error, and a wrong RED is not.

WHY CURRENCY IS AN ATTESTATION AND NOT A DETAIL
-----------------------------------------------
The project's claim is geographic: this product is buyable *from a German exit
IP*. A collector that silently egresses through the wrong country produces rows
that are individually well-formed and collectively meaningless.

The storefront's own currency symbol is the cheapest possible proof of which
market actually answered, and it comes from inside the page rather than from our
own configuration. A DE arm returning USD has not found a German listing, it has
found an American one, and the honest verdict is that we do not know. So a
currency that contradicts the arm withholds the row instead of reddening it.

Price VALUE is never recorded, here or anywhere. Only the symbol. The project
makes no claim about what anything costs and collecting the figure would invite
one.

Standard library only, and no network. The whole gate must be runnable and
testable from a clean clone so that any judge can feed it a listing by hand and
check the verdict by eye.
"""

import re

# Verdicts this module can return for a single arm. WITHHELD is not an error
# state: it is the honest answer when the evidence is self-contradictory.
RED = "RED"
NOT_FOUND = "NOT_FOUND"
WITHHELD = "WITHHELD"

# Discard reason codes. Every rejection is counted and reported by cause, because
# an opaque "no match" count is indistinguishable from a broken matcher.
AMBER = "AMBER"
DEAD_PAGE = "dead_page"
BLOCKED = "blocked"
NO_JOIN_KEY = "no_join_key"
IDENTITY_MISMATCH = "identity_mismatch"

# The currency each arm's storefront must quote. Any other symbol means the
# request did not land where we believe it did.
ARM_CURRENCY = {"US": "USD", "DE": "EUR", "IN": "INR"}

# Buy-control wording, in each marketplace's own language. Matching the
# marketplace's words rather than a translated guess keeps the evidence quotable:
# the label stored on the row is the string a human will see on the page.
BUY_LABELS = {
    "US": ("add to cart", "buy now", "add to basket"),
    # "in den warenkorb" is kaufland.de's wording, "in den einkaufswagen" is
    # amazon.de's. Both are German and both are real; neither is a translation
    # we chose. Note what is deliberately ABSENT: Danish "tilføj til
    # indkøbskurv", observed on amazon.de from a non-German exit. It is a valid
    # buy control on a page that is not in this arm's market, so it must not
    # count. See heals/2026-08-19-de-001.md.
    "DE": ("in den einkaufswagen", "in den warenkorb", "jetzt kaufen"),
    "IN": ("add to cart", "buy now"),
}

# A needle must survive normalisation and still carry a letter, or be a
# check-digit-valid GTIN. Four characters is the floor below which coincidental
# collision on a dense retail page stops being unlikely.
MIN_NEEDLE_LEN = 4

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def fold(s):
    """Uppercase and strip separators, so BR-C708S matches "BR C708S".

    Marketplaces reformat manufacturer part numbers freely: hyphens become
    spaces, spaces vanish, case drifts. Folding both sides of the comparison is
    what makes a real match survive that, and it is the only liberty taken.
    """
    if s is None:
        return ""
    return _NON_ALNUM.sub("", str(s)).upper()


def gtin_check_digit_ok(raw):
    """Validate a GTIN-8/12/13/14 modulo-10 check digit.

    A GTIN that fails its own check digit is either a typo in the notice or a
    number that is not a GTIN at all. Either way it must not be trusted as an
    identity assertion, and the arithmetic is short enough that a judge can
    verify any single case on paper.
    """
    digits = re.sub(r"\D", "", "" if raw is None else str(raw))
    if len(digits) not in (8, 12, 13, 14):
        return False
    body, check = digits[:-1], int(digits[-1])
    # Weights alternate 3,1 from the rightmost body digit leftwards.
    total = 0
    for i, ch in enumerate(reversed(body)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10 == check


def needle_is_assertable(needle, is_gtin=False):
    """May this identifier be used to assert identity from page text?

    A GTIN with a valid check digit always may. Anything else must contain a
    letter: a bare numeric token cannot be distinguished from the prices, review
    counts and millimetre dimensions that saturate a retail page, so treating one
    as proof of identity manufactures false positives at scale.
    """
    if is_gtin:
        return gtin_check_digit_ok(needle)
    folded = fold(needle)
    if len(folded) < MIN_NEEDLE_LEN:
        return False
    return any(c.isalpha() for c in folded)


def find_assertion(needle, page_text, is_gtin=False, dom_path=None, context_chars=60):
    """Locate `needle` in the page's own text and return the quotable evidence.

    `page_text` may be a single string or a sequence of the page's field values.
    A sequence is searched FIELD BY FIELD and never joined, because folding
    strips separators: concatenating a title ending "BR-C708" with a brand
    beginning "S-Line" would manufacture the match "BRC708S", which exists in
    neither field. An identifier has to be asserted inside one field to mean
    anything, so no join is safe and none is performed.

    Returns None when the needle is absent or not assertable. The returned
    context is raw surrounding page text, kept so the row carries what a reader
    needs to contest it without re-fetching anything.
    """
    if not needle_is_assertable(needle, is_gtin):
        return None

    if not isinstance(page_text, str):
        for field in (page_text or ()):
            hit = find_assertion(needle, field, is_gtin, dom_path, context_chars)
            if hit:
                return hit
        return None

    haystack, target = fold(page_text), fold(needle)
    if not target or target not in haystack:
        return None

    # Map the fold-space hit back to an offset in the original text, so the
    # context quoted on the row is the page's real wording rather than the
    # stripped form we matched against.
    keep = [i for i, c in enumerate(str(page_text)) if not _NON_ALNUM.match(c)]
    at = haystack.index(target)
    start = keep[at] if at < len(keep) else 0
    end_idx = at + len(target) - 1
    end = keep[end_idx] + 1 if end_idx < len(keep) else len(str(page_text))

    lo = max(0, start - context_chars)
    hi = min(len(str(page_text)), end + context_chars)
    evidence = {"needle": str(needle), "context": str(page_text)[lo:hi].strip()}
    if dom_path:
        evidence["dom_path"] = dom_path
    return evidence


def buy_control(listing, arm):
    """Read the buy control off the listing in the marketplace's own words.

    `present` is only true when the page offers an active control. An out-of-stock
    page frequently still renders a disabled button, so an explicit in_stock=False
    revokes presence: a greyed-out control is not a way to buy something.
    """
    label = listing.get("buy_label")
    in_stock = listing.get("in_stock")
    present = False
    if label:
        wanted = BUY_LABELS.get(arm, ())
        present = any(w in str(label).strip().lower() for w in wanted)
    if in_stock is False:
        present = False

    control = {"present": present}
    if label:
        control["label"] = str(label)
    if in_stock is not None:
        control["in_stock"] = bool(in_stock)
    if listing.get("ships_from"):
        control["ships_from"] = str(listing["ships_from"])
    return control


def currency_agrees(listing, arm):
    """Does the storefront's currency match the market we believe we reached?

    Returns (agrees, symbol_or_None). An absent symbol is not a contradiction —
    plenty of pages omit it — so it yields agreement with no proof, and the
    caller decides whether unproven geo is good enough. A PRESENT symbol that
    disagrees is a contradiction, and that is a withholding matter.
    """
    got = listing.get("currency")
    if not got:
        return True, None
    got = str(got).upper()
    return got == ARM_CURRENCY.get(arm), got


def adjudicate(notice, listing, arm, captured_at, require_currency_proof=True):
    """Decide one arm's verdict for one recall notice against one listing.

    `notice` supplies the identifiers to assert: model and/or gtin.
    `listing` is one normalised candidate: page_text, buy_label, in_stock,
    currency, ships_from, http, url, dom_path.

    Returns {"verdict", "evidence"|None, "discard"|None}. The caller stores the
    verdict on the arm and appends any discard to the row's reason ledger; this
    function never mutates anything and never fetches anything, so a judge can
    replay any published row through it by hand.
    """
    http = listing.get("http")
    if http in (404, 410):
        return _out(NOT_FOUND, discard=(DEAD_PAGE, "page %s at capture" % http))
    if http in (403, 429, 503):
        # A block is not an absence. Saying NOT_FOUND here would convert our own
        # failure into evidence that the product is gone, which is the exact
        # inversion this project exists to refuse.
        return _out(WITHHELD, discard=(BLOCKED, "page %s at capture" % http))

    page_text = listing.get("page_text") or ""
    if not page_text:
        return _out(WITHHELD, discard=(BLOCKED, "no page body captured"))

    agrees, symbol = currency_agrees(listing, arm)
    if not agrees:
        return _out(WITHHELD, discard=(
            BLOCKED,
            "storefront quoted %s, %s arm expects %s: exit country unproven"
            % (symbol, arm, ARM_CURRENCY.get(arm)),
        ))

    # GTIN first. It is the stronger claim and it is self-validating, so when a
    # notice carries both we prefer to rest the accusation on the better one.
    evidence = None
    if notice.get("gtin"):
        evidence = find_assertion(notice["gtin"], page_text, is_gtin=True,
                                  dom_path=listing.get("dom_path"))
    if evidence is None and notice.get("model"):
        evidence = find_assertion(notice["model"], page_text,
                                  dom_path=listing.get("dom_path"))

    if evidence is None:
        # Distinguish "we had nothing to match on" from "we had something and the
        # page contradicted it". Collapsing the two would hide whether the corpus
        # or the matcher is the bottleneck.
        if not _has_assertable_key(notice):
            return _out(NOT_FOUND, discard=(NO_JOIN_KEY,
                        "no assertable identifier in the notice"))
        return _out(NOT_FOUND, discard=(IDENTITY_MISMATCH,
                    "identifier absent from the fetched page body"))

    control = buy_control(listing, arm)
    if not control["present"]:
        # Identity confirmed, no way to buy it. That is the system working, and
        # it is deliberately not a RED row.
        return _out(NOT_FOUND, discard=(AMBER, "identity asserted, no active buy control"),
                    evidence=_evidence_block(evidence, control, listing, arm, captured_at, symbol))

    if require_currency_proof and symbol is None:
        # Both conditions hold, but nothing in the page proves which market
        # answered. The row is real; its geography is not established.
        return _out(WITHHELD, discard=(BLOCKED, "no currency symbol on page: exit country unproven"),
                    evidence=_evidence_block(evidence, control, listing, arm, captured_at, symbol))

    return _out(RED, evidence=_evidence_block(evidence, control, listing, arm,
                                              captured_at, symbol))


def _has_assertable_key(notice):
    return (needle_is_assertable(notice.get("gtin"), is_gtin=True)
            or needle_is_assertable(notice.get("model")))


def _evidence_block(assertion, control, listing, arm, captured_at, symbol):
    """Assemble the evidence chain, OMITTING absent keys rather than nulling them.

    Absence is part of the contract. Writing `null` or `0` into a field we never
    observed would convert a gap in our own measurement into a claim about the
    world, so a key we cannot fill simply does not appear and renders as MISSING.
    """
    ev = {"captured_at": captured_at, "assertion": assertion, "buy_control": control}
    if listing.get("http") is not None:
        ev["http"] = int(listing["http"])
    if listing.get("viewport"):
        ev["viewport"] = str(listing["viewport"])
    if symbol:
        ev["currency"] = symbol
    for key in ("sha256", "trace", "job_id"):
        if listing.get(key):
            ev[key] = str(listing[key])
    return ev


def _out(verdict, evidence=None, discard=None):
    return {
        "verdict": verdict,
        "evidence": evidence,
        "discard": ({"code": discard[0], "reason": discard[1]} if discard else None),
    }
