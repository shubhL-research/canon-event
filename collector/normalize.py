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
#
# 404 and 410 are deliberately NOT in this set. They are split out below,
# because "the page is gone" and "we were refused the page" are opposite claims
# that a single `blocked` code would flatten into one. A delisted product is a
# FINDING; a block is our own failure. Recording the first as the second
# understates what we measured, and recording the second as the first invents a
# result we never obtained.
BLOCK_STATUSES = {400, 401, 403, 405, 409, 418, 429, 500, 503}
DEAD_STATUSES = {404, 410}

CURRENCY_FOR_ARM = {"US": "USD", "DE": "EUR", "IN": "INR"}

# The language each arm's storefront must answer in.
#
# THIS OUTRANKS THE CURRENCY CHECK, and it was learned the hard way. A heal
# preview on 2026-08-19 returned a fully Danish page from amazon.de quoting EUR:
# "Pa lager", "Tilfoj til indkobskurv". The currency was right and the market
# was wrong. amazon.de quotes EUR to every visitor from every exit, so currency
# cannot separate a German session from a Danish one, and the three-arm
# comparison rests on exactly that separation.
#
# The page's own `lang` attribute can, because the storefront writes it in
# response to the session that reached it. See heals/2026-08-19-de-001.md.
LANGUAGE_FOR_ARM = {"US": ("en",), "DE": ("de",), "IN": ("en", "hi")}

# Buy-control wording, in each marketplace's own language. Matching the
# marketplace's words rather than merely checking that SOME label is present is
# what stops a valid buy control on a wrong-country page from earning RED.
BUY_LABELS = {
    "US": ("add to cart", "buy now", "add to basket"),
    "DE": ("in den einkaufswagen", "in den warenkorb", "jetzt kaufen"),
    "IN": ("add to cart", "buy now"),
}


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


def gtin_check_digit_ok(raw):
    """Validate a GTIN-8/12/13/14 modulo-10 check digit.

    A GTIN that fails its own check digit is either a typo in the notice or not
    a GTIN at all, and either way it must not be trusted as an identity claim.

    This is also the cheapest available detector for a mis-mapped collector
    field. A heal preview returned the review star rating in the `ean` slot,
    "4.1 ud af 5 stjerner", and the check digit is what refused it. The
    arithmetic is short enough to redo on paper for any single case.
    """
    digits = re.sub(r"\D", "", "" if raw is None else str(raw))
    if len(digits) not in (8, 12, 13, 14):
        return False
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(c) * (3 if i % 2 == 0 else 1)
                for i, c in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def gtin_forms(raw):
    """Every legal rendering of one GTIN, longest first. Empty if not a GTIN.

    WHY THIS EXISTS, AND WHAT IT COST TO FIND
    -----------------------------------------
    GS1 defines GTIN-8, -12, -13 and -14 as one number space: a shorter form is
    the longer form with leading zeros removed. `605566127453` and
    `0605566127453` are the SAME product, and a marketplace may print either.

    The boundary-anchored matcher rejects that pair. Searching for the 12-digit
    form against a page printing the 13-digit form fails the lookbehind, because
    the character before the match is `0`, which is alphanumeric. The anchor is
    right — it is what stops `PS-100` matching `PS-1000` — but a leading zero is
    not a different product, and treating it as one silently loses a real match.

    Found on the first live trial sweep, on a real kaufland.de row whose `ean`
    field carried both forms at once. **The error direction is the one that
    matters: it makes us MISS products that are still on sale, which understates
    the hazard and argues against our own headline.** Same direction as the
    identifier-rule correction in extract/identifier.py.

    Only check-digit-valid input produces forms. A number that is not a GTIN has
    no equivalent renderings, and inventing some for it would be a way to match
    more things rather than the right things.
    """
    digits = re.sub(r"\D", "", "" if raw is None else str(raw))
    if not gtin_check_digit_ok(digits):
        return []
    core = digits.lstrip("0") or "0"
    forms = {digits}
    for width in (8, 12, 13, 14):
        if len(core) <= width:
            forms.add(core.rjust(width, "0"))
    return sorted(forms, key=lambda f: (-len(f), f))


def collapse_repeat(value):
    """Collapse "X X" to "X" when both halves are byte-identical.

    Observed on 25 of 28 real kaufland.de rows: the generated extractor matches
    both a label node and its value node and concatenates them, so an EAN
    arrives as "8721003407246 8721003407246". That is 26 digits, fails its own
    check digit, and a usable identifier is thrown away.

    Restricted to exact repetition of the whole string, which is the only case
    where nothing can be lost: "X X" carries no information "X" does not. A
    genuinely repetitive multi-value field like "A, B, A" is left alone. All 28
    repaired EANs validated, which is the evidence the repair is right rather
    than merely convenient.
    """
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        return text
    parts = text.split(" ")
    for halves in (2, 3):
        if len(parts) % halves:
            continue
        size = len(parts) // halves
        chunks = [" ".join(parts[i * size:(i + 1) * size]) for i in range(halves)]
        if len(set(chunks)) == 1 and chunks[0]:
            return chunks[0]
    return text


def needle_is_assertable(needle, is_gtin=False):
    """May this identifier be used to assert identity from page text?

    A GTIN with a valid check digit always may. Anything else must contain a
    letter.

    The bare-numeric refusal costs recall and is worth it. "113210" is a real
    CPSC model value, and on a retail page it is also a price, a review count, a
    dimension in millimetres and an unrelated part number. Boundary anchoring
    stops PS-100 matching PS-1000, but it cannot stop a bare number matching a
    bare number that happens to mean something else entirely. An AMBER row
    excluded from the statistics is a survivable error; a RED row naming the
    wrong seller is not.
    """
    if is_gtin:
        return gtin_check_digit_ok(needle)
    folded = norm_needle(needle)
    if len(folded) < 4:
        return False
    return any(c.isalpha() for c in folded)


def buy_control_present(raw):
    """Is there an active buy control, in this arm's own language?

    Presence of SOME label is not enough. The Danish "Tilfoj til indkobskurv"
    observed on amazon.de is a perfectly valid buy control on a page that is not
    in the DE arm's market, and counting it would redden a row whose geography
    is wrong. Checking the wording against the arm's own languages turns that
    from a lucky catch into a control.
    """
    arm, label = pick(raw, "arm"), pick(raw, "buy_label")
    if not present(label):
        return False
    if pick(raw, "in_stock") is False:
        # A disabled control still renders. Greyed out is not a way to buy.
        return False
    wanted = BUY_LABELS.get(arm, ())
    if not wanted:
        return False
    return any(w in str(label).strip().lower() for w in wanted)


def language_ok(raw):
    """Does the page's own locale match the market this arm claims to measure?

    MISSING when the collector did not emit `page_language`, which is not a
    contradiction and must not be treated as one: plenty of pages omit the
    attribute and an absent attestation is unproven rather than disproven.
    """
    arm, lang = pick(raw, "arm"), pick(raw, "page_language")
    if not present(arm) or not present(lang):
        return MISSING
    prefixes = LANGUAGE_FOR_ARM.get(arm, ())
    return any(str(lang).strip().lower().startswith(p) for p in prefixes)


def matching_forms(needle):
    """The renderings of `needle` that count as the same identifier.

    A GTIN contributes its whole legal family, because a leading zero is a format
    and not a different product. Anything else contributes only itself: a model
    number has no equivalent renderings, and inventing some would widen the match
    in the one direction this project must never widen.
    """
    forms = gtin_forms(needle)
    return forms if forms else [str(needle)]


def reassert(page_text, needle):
    """Did the identifier actually reappear on the page we fetched?

    This is the load-bearing check in the whole project. Amazon substitutes
    ASINs on stale URLs, so a live buy control on the WRONG product would score
    as a hazard still on sale. The identifier must be present in the fetched
    page's own text, not merely in the URL we asked for, and it must appear as
    a whole token rather than as a fragment of a longer one.

    A GTIN is matched across its legal forms, for the reason in gtin_forms().
    Everything else is matched exactly, boundary-anchored.
    """
    if not present(page_text) or not present(needle):
        return False
    text = str(page_text)
    for form in matching_forms(needle):
        pat = needle_pattern(form)
        if pat and pat.search(text):
            return True
    return False


def context_around(page_text, needle, width=90):
    """A short excerpt containing the needle, for the two-receipt card."""
    if not present(page_text) or not present(needle):
        return MISSING
    m = None
    for form in matching_forms(needle):
        pat = needle_pattern(form)
        m = pat.search(str(page_text)) if pat else None
        if m:
            break
    if not m:
        return MISSING
    start = max(0, m.start() - width)
    end = min(len(str(page_text)), m.end() + width)
    return ("..." if start else "") + str(page_text)[start:end] + ("..." if end < len(str(page_text)) else "")


# A listing that names the recalled product because it FITS it is not the
# recalled product. These are the phrases marketplaces use to say so.
#
# Matched against the text immediately around the identifier, not the whole
# page, because a page can legitimately mention compatibility further down while
# still selling the product itself.
_ACCESSORY_MARKERS = (
    # Only phrases that describe THE ITEM BEING SOLD as a part, a case or a
    # substitute. Anything that merely describes a product's purpose was removed
    # after it fired on a genuine Siemens listing whose own copy reads "an
    # integrated energy management solution DESIGNED FOR industrial and
    # commercial applications". "designed for", "suitable for", "for use with",
    # "works with" and a bare "accessory" all describe real products constantly,
    # and discarding on them suppresses findings rather than false ones.
    "compatible with", "compatible for", "fits ", "fit for", "fits for",
    "replacement for", "replacement part", "replacement parts", "spare part",
    "spares for", "carry case", "carrying case", "travel case", "travel box",
    "hard case", "cover for", "case for", "screen protector", "adapter for",
    "charger for", "battery for", "strap for", "mount for", "stand for",
    "bag for", "accessories for", "oem replacement",
)

# The strongest signal of all, and the one a marker list keeps missing.
#
# "MaxLLTo Replacement E165000291 Blower Tube FOR Echo PB-5810H" survived every
# phrase above. The pattern is positional rather than lexical: the identifier is
# preceded by "for", because the listing is naming what the item FITS rather than
# what it IS.
#
# Note that a brand check cannot rescue this. That listing legitimately says
# "Echo", so the brand agrees; it is the framing that disagrees. Which is why the
# accessory test runs before the brand test and not instead of it.
_FITS_PREPOSITION = re.compile(r"\b(for|fits|fit)\s+[\w&.\-]*\s*$", re.I)

# Storefront chrome that says "for <product>" without meaning "fits <product>".
#
# The positional check above fired on a GENUINE Siemens listing because Shopify
# labels its quantity stepper "Decrease quantity for MC2442S1200SC". That is a
# false DISCARD, which is the dangerous direction: it suppresses a real finding
# rather than publishing a false one. A guard against false positives that
# creates false negatives has moved the error, not removed it.
_ACCESSORY_NOUN = re.compile(
    r"\b(case|cover|charger|adapter|adaptor|batter|strap|mount|stand|bag|"
    r"holder|hoist|protector|sleeve|pouch|cord|cable|hose|filter|lid)", re.I)

_UI_CHROME = (
    "quantity for", "decrease quantity", "increase quantity", "search for",
    "results for", "reviews for", "review for", "question for", "notify me",
    "price for", "shipping for", "checkout for", "add to cart for",
    "wishlist for", "compare for", "available for", "in stock for",
)


def accessory_context(page_text, needle, width=120, expected_name=None):
    """Is the identifier on this page because the listing FITS the product?

    WHY THIS EXISTS
    ---------------
    Fixing brand_conflict removed a check that had been suppressing RED on all
    103 CPSC notices. What surfaced was not four findings. It was four listings
    that name a recalled product without being it:

        BenQ Hard Carry Case GV31 Portable Projector Travel Box
        Caltric Starter Motor Compatible with Yamaha Golf Cart Drive2
        BLOWER TUBE FITS PB-5810T, PB-5810H ... Replacement for ECHO OEM
        10 Cup Programmable Coffee Maker      (against a recall for bowls)

    reassert() answers "does the identifier appear on this page". It cannot
    answer "is this page selling that product", and for accessories those two
    questions have opposite answers. brand_conflict was accidentally covering
    the gap, badly and only for notices whose brand string happened not to
    match, and the moment it was corrected the gap was visible.

    Publishing any of those four as RED would be a hazard claim against a seller
    who did nothing wrong, which is the single worst thing this project could do.
    """
    if not present(page_text) or not present(needle):
        return None
    text = str(page_text)
    pat = needle_pattern(needle)
    if pat is None:
        return None
    low = text.lower()

    # WHEN THE RECALLED PRODUCT IS ITSELF AN ACCESSORY, THESE MARKERS ARE NOT
    # EVIDENCE OF ANYTHING.
    #
    # This corpus recalls Flaunt MagSafe Battery Chargers, Broqixin Pool Drain
    # Covers, EEMB Lithium Battery Packs and Ceiling Hoists with Straps. The
    # genuine listing for a recalled drain cover says "cover for", and for a
    # recalled charger says "charger for". Discarding on that would hide exactly
    # the products we are looking for, which is the quiet failure direction: a
    # false RED gets argued about, a false DISCARD is never seen.
    #
    # So a marker is disregarded when the recalled product's own name contains
    # the same noun.
    live = _ACCESSORY_MARKERS
    if expected_name:
        name = str(expected_name).lower()
        live = tuple(mk for mk in _ACCESSORY_MARKERS
                     if not any(w in name for w in mk.split() if len(w) > 3))

    for m in pat.finditer(text):
        lo = max(0, m.start() - width)
        window = low[lo:m.end() + width]
        for marker in live:
            if marker in window:
                return marker.strip()
        # "... Blower Tube for Echo PB-5810H": the words immediately before the
        # identifier say the listing fits it. Checked on the raw slice so the
        # brand between "for" and the identifier is allowed for.
        before = text[lo:m.start()]
        # The positional check is suppressed entirely when the recalled product
        # IS an accessory-type item. "Flaunt MagSafe Battery Charger for iPhone"
        # is that charger's own listing, and "for" is how such a product is
        # always described. Losing the positional guard on those notices is the
        # right trade: a false RED is loud and gets hand-verified, a false
        # DISCARD is silent and hides the thing we are looking for.
        if _ACCESSORY_NOUN.search(str(expected_name or "")):
            continue
        if _FITS_PREPOSITION.search(before):
            tail = before.lower()[-60:]
            if not any(ui in tail for ui in _UI_CHROME):
                return "for"
    return None


# Corporate suffixes and the address clause a regulator appends to a company
# name. Trimmed only from the END of the name, never from the middle, so
# "Inc Industries" stays intact if a brand really is called that.
_CORP_SUFFIX = (
    "incorporated", "inc", "llc", "l l c", "ltd", "limited", "co", "corp",
    "corporation", "company", "gmbh", "bv", "b v", "sa", "s a", "srl", "s r l",
    "ag", "nv", "n v", "plc", "pty", "pte", "kg", "oy", "ab", "as", "aps",
    "sarl", "spa", "s p a", "group", "holdings", "international", "usa",
    "america", "americas", "north america",
)


def brand_core(brand):
    """The distinctive part of a manufacturer name.

    WHY THIS EXISTS, AND IT IS THE WORST BUG THIS PROJECT HAS SHIPPED
    -----------------------------------------------------------------
    brand_conflict() asked whether the WHOLE expected brand string appeared in
    the page text. CPSC does not publish a brand. It publishes the recalling
    firm's full legal identity plus its address:

        "ECHO Inc., of Lake Zurich, Illinois"
        "Zhejiang Changying Car Industry Co. LTD, of China"

    A marketplace page selling that product says "ECHO". It will never contain
    the regulator's address clause, so norm_needle(expected) was never a
    substring of norm_needle(page), so brand_conflict returned True for every
    CPSC notice. brand_conflict is checked at normalize.py:424 on any needle that
    is not a valid GTIN, and all 103 CPSC seeds carry gtin: null.

    So RED was structurally unreachable for 103 of the 207 notices. Half the
    corpus could not have produced a finding whatever was on the page, and the
    published zero was, for that half, a fact about this function.

    The fix trims the address clause and trailing corporate suffixes and compares
    what is left. That WIDENS the matcher, which is the direction this project is
    normally most careful about, so it is bounded: a core shorter than four
    characters is treated as unknown rather than as agreement, and unknown has
    never been a conflict here.
    """
    if not brand:
        return ""
    b = str(brand)
    # CPSC's address clause. "ECHO Inc., of Lake Zurich, Illinois" -> "ECHO Inc."
    for sep in (", of ", " of "):
        if sep in b:
            head = b.split(sep)[0]
            if len(norm_needle(head)) >= 3:
                b = head
                break
    # dba names: the trading name is what a marketplace shows.
    for marker in (" dba ", " d/b/a ", ", dba ", ", d/b/a "):
        if marker in b.lower():
            tail = re.split(marker, b, flags=re.I)[-1]
            if len(norm_needle(tail)) >= 3:
                b = tail
                break
    words = [w for w in re.split(r"[\s,]+", b) if w]
    while words and norm_needle(words[-1]) in _CORP_SUFFIX:
        words.pop()
    return " ".join(words) if words else b


def brand_conflict(page_text, expected_brand):
    """Does the page name a DIFFERENT manufacturer than the notice does?

    Identity re-assertion checks that the identifier appears on the fetched page.
    It says nothing about whose product it is. Model strings are not globally
    unique: PB-5810H can belong to two manufacturers, and a page carrying that
    string for the wrong brand re-asserts perfectly while publishing a hazard
    claim against a company that never made the recalled product.

    The adversarial precision set caught exactly this leak, which is the second
    real false-positive it has found.

    Absent brand on either side is NOT a conflict. Unknown is not disagreement,
    and treating it as one would silently discard correct findings.
    """
    if not present(page_text) or not expected_brand:
        return False
    # The DISTINCTIVE part, not the regulator's legal identity. See brand_core.
    want = norm_needle(brand_core(expected_brand))
    if len(want) < 4:
        # Too short to be evidence either way. Unknown is not disagreement, and
        # treating it as one is what made this check discard the world.
        return False
    return want not in norm_needle(page_text)


def classify(raw, expected_brand=None, expected_name=None):
    """RED, AMBER or DISCARDED, with the reason recorded either way."""
    err = pick(raw, "error")
    if present(err):
        code = str(err) if str(err) in FATAL_ERRORS else "crawl_error"
        return "DISCARDED", [{"code": code, "reason": f"collector reported {err}"}]

    status = pick(raw, "http_status")
    if present(status) and int(status) in DEAD_STATUSES:
        return "DISCARDED", [{"code": "dead_page",
                              "reason": f"HTTP {status} at capture: the listing is gone"}]
    if present(status) and int(status) in BLOCK_STATUSES:
        return "DISCARDED", [{"code": "blocked",
                              "reason": f"HTTP {status} from the fetch layer"}]

    needle = pick(raw, "needle")
    if not present(needle):
        return "DISCARDED", [{"code": "no_join_key",
                              "reason": "no machine-matchable identifier to search for"}]

    # A doubled value is a collector artifact, not the identifier. Repair it
    # before deciding whether it can be asserted at all.
    needle = collapse_repeat(needle)
    is_gtin = gtin_check_digit_ok(needle)
    if not needle_is_assertable(needle, is_gtin):
        return "DISCARDED", [{"code": "no_join_key",
                              "reason": "identifier is not distinctive enough to assert "
                                        "identity from page text"}]

    # Geography before hazard. An arm that cannot prove which market answered it
    # has not found a foreign listing, and saying otherwise is the failure the
    # three-arm design exists to avoid.
    if language_ok(raw) is False:
        return "DISCARDED", [{"code": "blocked",
                              "reason": f"page language {pick(raw, 'page_language')!r} does not "
                                        f"match arm {pick(raw, 'arm')}: exit market unproven"}]
    if currency_ok(raw) is False:
        return "DISCARDED", [{"code": "blocked",
                              "reason": f"storefront quoted {pick(raw, 'currency')}, arm "
                                        f"{pick(raw, 'arm')} expects "
                                        f"{CURRENCY_FOR_ARM.get(pick(raw, 'arm'))}"}]

    matched = reassert(pick(raw, "page_text"), needle)
    buy = buy_control_present(raw)

    # Identity is not identity of MAKER, but only when the identifier is weak.
    #
    # A GTIN is globally unique by construction, so it settles identity on its
    # own and the brand on the page is irrelevant: a live kaufland.de row for
    # EAN 8721003407246 carried the reseller's name and a part number in the
    # brand slot, and refusing it would have discarded a correct finding.
    #
    # A model number is NOT globally unique. Two manufacturers can ship the same
    # string, so there the page must also name the maker or the claim could land
    # on a company that never built the recalled product.
    # An accessory that names the product is not the product. Checked before the
    # brand rule, because these listings often carry the RIGHT brand: a BenQ
    # carry case really is made by BenQ.
    if matched:
        marker = accessory_context(pick(raw, "page_text"), needle,
                                   expected_name=expected_name)
        if marker:
            return "DISCARDED", [{"code": "accessory_or_compatible",
                                  "reason": "the identifier appears next to "
                                            "\"%s\": this listing names the "
                                            "recalled product because it fits "
                                            "it, and is not it" % marker}]

    if matched and not is_gtin and brand_conflict(pick(raw, "page_text"), expected_brand):
        return "AMBER", [{"code": "brand_conflict",
                          "reason": "identifier re-asserted but the page does not name the "
                                    "manufacturer on the notice. Model strings are not "
                                    "globally unique, so this may be another maker's product."}]

    if matched and buy:
        return "RED", []
    if matched and not buy:
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
    tier, discarded = classify(raw, seed.get("brand"), seed.get("name"))
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
