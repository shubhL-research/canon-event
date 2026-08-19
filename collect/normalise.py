"""Turn whatever Scraper Studio returns into the shape the gate expects.

WHY THIS FILE EXISTS
--------------------
The collector's output schema is written by Bright Data's AI, not by us. Ask
three arms for "the add-to-cart button text" and you can get `add_to_cart`,
`addToCartText`, `buy_button`, or a field the generator invented. That is fine —
it is the platform doing its job — but it means the boundary between the
platform and our contract needs an explicit, auditable translation layer rather
than a pile of `row.get("price")` calls scattered through the sweep.

Everything downstream of this file speaks the frozen contract. Everything
upstream speaks whatever the AI generated. This is the only place that knows
both, which is what makes the collector replaceable without touching the gate.

THE TWO RULES THIS FILE OBEYS
-----------------------------
1. ABSENCE IS PRESERVED. Bright Data omits keys it could not fill rather than
   nulling them. A missing `price` means the extractor found no price, which is
   a fact about our measurement. Defaulting it to 0, "" or False would convert
   that gap into a claim about the world, and the whole project rests on
   refusing to do exactly that. A key we did not observe does not appear.

2. NOTHING UNMAPPED IS DROPPED SILENTLY. Any field the collector returned that
   this file does not recognise is recorded in `unmapped`. A silently discarded
   field is how a schema drift becomes a wrong number three days later: the
   sweep keeps running, the rows keep validating, and a column quietly stops
   being populated. Counting the strangers makes drift visible on the health
   file instead of invisible in the output.

WHY CURRENCY IS PARSED FROM THE SYMBOL
--------------------------------------
Scraper Studio has no country flag. Geo comes from the Search scraper's country
input, which means the country we asked for lives in OUR configuration — and a
config file is not evidence. The storefront's own currency symbol is the
cheapest proof that lives INSIDE the fetched page: a page quoting € answered
from the euro market, whatever we believe we requested.

So the symbol is extracted here and handed to the gate, which refuses to redden
a row whose currency contradicts its arm. Price VALUE is deliberately discarded
at this boundary and never reaches the contract. The project makes no claim
about what anything costs, and carrying the figure would invite one.

Standard library only, no network. Feed it a saved job payload and it runs.
"""

import re

# Candidate field names, best first. The AI generator is consistent within a
# collector but not across them, so each contract field lists the spellings seen
# in practice plus the obvious near-misses. Order matters: the first key present
# in the row wins.
FIELD_ALIASES = {
    "title": ("title", "product_title", "name", "product_name"),
    "brand": ("brand", "manufacturer", "brand_name"),
    "model": ("model", "model_number", "part_number", "manufacturer_part_number",
              "mpn", "item_model_number", "model_no"),
    "gtin": ("gtin", "ean", "upc", "barcode", "gtin13", "ean13"),
    "asin": ("asin", "product_id", "item_id", "sku"),
    "price_raw": ("price", "current_price", "price_text", "final_price", "amount"),
    "currency_raw": ("currency", "currency_symbol", "currency_code"),
    "buy_label": ("add_to_cart", "add_to_cart_text", "add_to_cart_button_text",
                  "buy_button", "buy_button_text", "cart_button", "buy_now",
                  "add_to_cart_button", "buy_label"),
    "availability": ("availability", "availability_text", "in_stock_text",
                     "stock_status", "stock"),
    "seller": ("seller", "seller_name", "sold_by", "merchant"),
    "ships_from": ("ships_from", "shipped_by", "fulfilled_by", "dispatched_from"),
    "url": ("url", "product_url", "product_page_url", "link", "page_url"),
    "page_language": ("page_language", "lang", "html_lang", "locale"),
    "page_text": ("page_text", "html_text", "body_text", "description", "full_text"),
}

# Keys the CLI adds around the collector's own output. They are not product
# fields and their presence is not schema drift, so they are recognised here in
# order to be ignored rather than reported as strangers.
ENVELOPE_KEYS = ("input", "error", "error_code", "warning", "timestamp")

# Symbol and code to ISO code. Only the three markets this project measures: an
# unrecognised symbol must stay unrecognised so the gate can withhold on it,
# rather than being coerced into whichever currency we were hoping for.
CURRENCY_SIGNS = (
    ("EUR", ("€", "eur")),
    ("USD", ("$", "usd", "us$")),
    ("INR", ("₹", "inr", "rs.", "rs ")),
)

# The language each arm's storefront must answer in.
#
# THIS IS THE GEO ATTESTATION, AND IT OUTRANKS CURRENCY. Learned from a real
# heal preview on 2026-08-19: amazon.de returned a fully Danish page — "På
# lager", "Tilføj til indkøbskurv" — quoting EUR. The currency was correct and
# the market was not. amazon.de quotes EUR to every visitor from every exit, so
# a currency check cannot distinguish a German exit from a Danish one, and the
# whole three-arm comparison rests on that distinction.
#
# The page's own `lang` attribute can. It is written by the storefront, in
# response to the session that reached it, and it is inside the fetched
# document rather than in our configuration. See heals/2026-08-19-de-001.md.
ARM_LANGUAGE = {"US": ("en",), "DE": ("de",), "IN": ("en", "hi")}

# Wording that means "you cannot buy this right now", in each market's language.
# Matched against the availability text, never against the button, because a
# disabled button often still reads "Add to Cart".
OUT_OF_STOCK = (
    "currently unavailable", "out of stock", "unavailable",
    "derzeit nicht verfügbar", "nicht auf lager", "nicht verfügbar",
    "temporarily out of stock",
)
IN_STOCK = ("in stock", "auf lager", "in den einkaufswagen", "available")

_WS = re.compile(r"\s+")


def collapse_repeat(value):
    """Collapse "X X" to "X" when both halves are byte-identical.

    Observed on 25 of 28 real kaufland.de rows and again in an amazon.de heal
    preview: the generated extractor matches both a label node and its value
    node, or the same node twice, and concatenates. `ean` arrives as
    "8721003407246 8721003407246", which is 26 digits and therefore not a GTIN
    at all — the check-digit guard rejects it and a real, usable identifier is
    lost.

    The repair is restricted to EXACT repetition of the whole string, because
    that is the only case where nothing can be lost: "X X" carries no
    information that "X" does not. A value that merely looks repetitive, like a
    genuine multi-value model field "A, B, A", is left alone.

    Returns (value, repaired) so the caller can count repairs. A silent repair
    would hide a live collector defect behind clean-looking output, and the
    defect is the thing that needs fixing at source.
    """
    if value is None:
        return None, False
    text = _WS.sub(" ", str(value)).strip()
    if not text:
        return text, False
    for halves in (2, 3):
        parts = text.split(" ")
        if len(parts) % halves:
            continue
        size = len(parts) // halves
        chunks = [" ".join(parts[i * size:(i + 1) * size]) for i in range(halves)]
        if len(set(chunks)) == 1 and chunks[0]:
            return chunks[0], True
    return text, False


def pick(row, field):
    """First aliased key actually present, or None.

    Presence is judged on the key existing with a non-empty value. Bright Data
    omits absent keys, so a key that is present but empty is a different fact
    from a key that never appeared — both mean "not observed" to us, and both
    yield None here so the caller omits the field entirely.
    """
    for key in FIELD_ALIASES.get(field, ()):
        if key in row:
            val = row[key]
            if val is None:
                continue
            if isinstance(val, str) and not val.strip():
                continue
            return val
    return None


def mapped_keys():
    """Every key name this module knows how to read."""
    return {k for aliases in FIELD_ALIASES.values() for k in aliases}


def currency_of(*texts):
    """ISO code for the first recognisable currency sign in any of `texts`.

    Returns None when nothing recognisable is present. None is not a failure: it
    means the page offered no proof of which market answered, and the gate
    decides what to do about that. Guessing here would fabricate the very
    evidence the gate is checking for.
    """
    for text in texts:
        if not text:
            continue
        low = str(text).lower()
        for code, signs in CURRENCY_SIGNS:
            if any(s in low for s in signs):
                return code
    return None


def stock_of(availability):
    """True, False, or None from the marketplace's own availability wording.

    None when the text is absent or says nothing we recognise. Returning False
    for unrecognised wording would silently suppress real rows; returning True
    would fabricate them. Unknown has to stay unknown.
    """
    if not availability:
        return None
    low = _WS.sub(" ", str(availability)).strip().lower()
    # Out-of-stock is checked first: "currently unavailable" contains no
    # in-stock phrase, but several in-stock phrases appear inside longer
    # unavailability sentences.
    if any(p in low for p in OUT_OF_STOCK):
        return False
    if any(p in low for p in IN_STOCK):
        return True
    return None


def searchable_text(row, *extra):
    """The fields the gate asserts identity against, as a LIST, never joined.

    Returning a list rather than one blob is a correctness requirement, not a
    style choice. The gate folds away punctuation before matching, so joining a
    title ending "BR-C708" to a brand beginning "S-Line" would create the match
    "BRC708S" out of thin air — an identifier present in neither field, and a
    false accusation against a real listing. Keeping the fields separate makes
    that class of match impossible rather than merely unlikely.
    """
    parts = []
    for field in ("title", "brand", "model", "gtin", "asin", "page_text"):
        val = pick(row, field)
        if val:
            # Doubled values are collapsed before matching, or a real GTIN
            # arrives as 26 digits and fails its own check digit.
            parts.append(collapse_repeat(val)[0])
    parts.extend(str(e) for e in extra if e)
    return parts


def normalise(row, arm, http=None, job_id=None, trace=None):
    """One raw collector row to one listing the gate can adjudicate.

    Absent inputs produce absent keys, never defaults. The returned dict is
    deliberately flat and boring: the gate should not have to know anything
    about Bright Data, and this is the file that guarantees it does not.
    """
    listing = {}

    title = pick(row, "title")
    if title:
        listing["title"] = _WS.sub(" ", str(title)).strip()

    url = pick(row, "url")
    if url:
        listing["url"] = str(url)

    availability = pick(row, "availability")
    if availability:
        listing["availability"] = _WS.sub(" ", str(availability)).strip()

    buy_label = pick(row, "buy_label")
    if buy_label:
        listing["buy_label"] = _WS.sub(" ", str(buy_label)).strip()

    stock = stock_of(availability)
    if stock is not None:
        listing["in_stock"] = stock

    # Price value is read only to find the symbol, then discarded. The symbol is
    # the geo attestation; the number is a claim we do not make.
    currency = currency_of(pick(row, "currency_raw"), pick(row, "price_raw"))
    if currency:
        listing["currency"] = currency

    for field, key in (("seller", "seller"), ("ships_from", "ships_from")):
        val = pick(row, field)
        if val:
            listing[key] = _WS.sub(" ", str(val)).strip()
    # A marketplace that names a seller but not a fulfiller still tells us who
    # is shipping it, which is what the row displays.
    if "ships_from" not in listing and listing.get("seller"):
        listing["ships_from"] = listing["seller"]

    # The page's own locale, which is what actually attests the exit market.
    language = pick(row, "page_language")
    if language:
        listing["page_language"] = str(language).strip().lower()[:5]

    listing["page_text"] = searchable_text(row)

    repaired = [f for f in ("model", "gtin", "title")
                if pick(row, f) and collapse_repeat(pick(row, f))[1]]
    if repaired:
        listing["repaired_doubles"] = repaired

    if http is not None:
        listing["http"] = int(http)
    if job_id:
        listing["job_id"] = str(job_id)
    if trace:
        listing["trace"] = str(trace)

    # Strangers are carried, not dropped. This is what makes schema drift show
    # up on the health file the day it happens.
    known = mapped_keys() | set(ENVELOPE_KEYS)
    unmapped = sorted(k for k in row if k not in known)
    if unmapped:
        listing["unmapped"] = unmapped

    listing["arm"] = arm
    return listing


def normalise_job(payload, arm, job_id=None):
    """Normalise a whole `bdata scraper run` payload.

    Accepts the shapes the CLI emits: a bare list of rows, or an envelope with
    the rows under a data-ish key. Returns (listings, report) where the report
    carries the counts the health file needs — including how many rows arrived
    with keys we did not recognise, which is the drift signal.
    """
    rows = _rows_of(payload)
    listings = [normalise(r, arm, job_id=job_id) for r in rows if isinstance(r, dict)]

    drifted = sorted({k for l in listings for k in l.get("unmapped", ())})
    wrong_language = sorted({l["page_language"] for l in listings
                             if l.get("page_language")
                             and not any(l["page_language"].startswith(p)
                                         for p in ARM_LANGUAGE.get(arm, ()))})
    report = {
        "arm": arm,
        "rows_in": len(rows),
        "rows_normalised": len(listings),
        "with_currency": sum(1 for l in listings if l.get("currency")),
        "with_buy_label": sum(1 for l in listings if l.get("buy_label")),
        "with_language": sum(1 for l in listings if l.get("page_language")),
        "wrong_language": wrong_language,
        "repaired_doubles": sum(1 for l in listings if l.get("repaired_doubles")),
        "unmapped_fields": drifted,
    }
    if job_id:
        report["job_id"] = str(job_id)
    return listings, report


def _rows_of(payload):
    """Find the row list inside whatever envelope the CLI used."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "rows", "items", "output"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
        # A single row returned bare, rather than wrapped in a list.
        if any(k in payload for k in mapped_keys()):
            return [payload]
    return []
