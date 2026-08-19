"""Scraper Studio's output shape -> the flat rows COLLECTOR.md specifies.

WHY THIS FILE EXISTS
--------------------
`COLLECTOR.md` says: emit RAW_FIELDS and stop. That is the right contract, and
`normalize.py` is written against it. But nobody hand-writes the collector — the
Scraper Studio AI Agent generates it, and it names its own fields. Three arms
asked the same question returned `add_to_cart`, `add_to_cart_text` and
`add_to_cart_button_text`, and the EAN arrived under `ean` on one arm and inside
a nested `price` object on another.

So this is the adapter between a schema we do not control and a contract we do.
It is the ONLY module allowed to know Bright Data's field names. `normalize.py`
never sees them, which is what keeps the RED decision testable against a fixed
vocabulary while the collectors underneath keep changing.

WHAT IT REFUSES TO DO
---------------------
It does not decide anything. No tier, no re-assertion, no statistic. If a field
is absent it stays absent, because `normalize.py` renders absence as MISSING all
the way to the screen and a default here would silently become a claim there.

Unrecognised fields are counted rather than dropped. An AI-generated schema
drifts quietly: the job still succeeds, the rows still validate, and a column
stops being populated three days before anyone notices the number moved.

Standard library only.
"""

import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from normalize import collapse_repeat  # noqa: E402

# Candidate names per contract field, best first. Every spelling here was
# observed in a real collector payload, not guessed.
ALIASES = {
    "title": ("title", "product_title", "name", "product_name"),
    "brand": ("brand", "brand_name", "manufacturer"),
    "model": ("manufacturer_part_number", "model_number", "part_number", "mpn",
              "item_model_number", "model", "model_no"),
    "gtin": ("ean", "gtin", "upc", "barcode", "gtin13", "ean13"),
    "url": ("product_page_url", "product_url", "url", "link", "page_url"),
    "buy_label": ("add_to_cart_button_text", "add_to_cart_text", "add_to_cart",
                  "buy_button_text", "buy_button", "cart_button", "buy_now"),
    "availability": ("availability_text", "availability", "in_stock_text",
                     "stock_status", "stock"),
    "seller": ("seller_name", "seller", "sold_by", "merchant"),
    "ships_from": ("ships_from", "shipped_by", "fulfilled_by", "dispatched_from"),
    "currency": ("currency_symbol", "currency", "currency_code"),
    "page_language": ("page_language", "html_lang", "lang", "locale"),
    "http_status": ("http_status", "status_code", "http"),
    "error": ("error",),
    "error_code": ("error_code",),
    "warning": ("warning",),
}

# Keys the CLI wraps around a collector's own output. Not product fields, and
# their presence is not drift.
ENVELOPE = ("input", "timestamp", "job_id", "trace", "sha256")

# Fields we see and deliberately refuse to carry. `price` is read only far
# enough to recover its currency symbol; the value never crosses this boundary.
# Listing it here keeps it out of the drift report, because "we chose not to map
# this" and "we do not recognise this" are different facts and only the second
# one needs anybody's attention.
IGNORED = ("price", "rating", "reviews_count", "image", "images", "thumbnail")

# Currency signs to ISO code. An unrecognised symbol stays unrecognised: coercing
# it into one of ours would fabricate the geography evidence the gate checks for.
SIGNS = (("EUR", ("€", "eur")), ("USD", ("$", "usd")), ("INR", ("₹", "inr", "rs.")))

# Wording that means the product cannot be bought right now, per market. Matched
# against availability text only, never against the button: a disabled control
# frequently still reads "Add to Cart".
OUT_OF_STOCK = ("currently unavailable", "out of stock", "unavailable",
                "derzeit nicht verfügbar", "nicht auf lager", "nicht verfügbar",
                "temporarily out of stock", "sold out")
IN_STOCK = ("in stock", "auf lager", "available", "på lager")

_WS = re.compile(r"\s+")


def pick(row, field):
    """First aliased key present with a usable value, else None.

    A key that exists but holds None or an empty string counts as absent. Both
    mean "the extractor found nothing", and both must produce an omitted field
    rather than an empty one.
    """
    for key in ALIASES.get(field, ()):
        if key not in row:
            continue
        val = row[key]
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        return val
    return None


def known_keys():
    return ({k for names in ALIASES.values() for k in names}
            | set(ENVELOPE) | set(IGNORED))


def currency_of(*values):
    """ISO code for the first recognisable currency sign, else None.

    Reads the symbol out of a price string without ever keeping the number.
    The project makes no claim about what anything costs; the symbol is only
    ever a fingerprint for which storefront answered.
    """
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            # Some collectors nest: {"value": 69.99, "currency": "EUR"}.
            value = value.get("currency") or value.get("symbol") or ""
        low = str(value).lower()
        for code, signs in SIGNS:
            if any(s in low for s in signs):
                return code
    return None


def stock_of(availability):
    """True, False or None from the marketplace's own wording.

    None when absent or unrecognised. kaufland.de puts a delivery date range in
    this field rather than a stock phrase, and inventing a boolean from
    "Do. 20. - Fr. 21. August" would be a guess. Unknown stays unknown and the
    buy control carries the verdict.
    """
    if not availability:
        return None
    low = _WS.sub(" ", str(availability)).strip().lower()
    # Out-of-stock is tested first: several in-stock phrases appear inside
    # longer unavailability sentences.
    if any(p in low for p in OUT_OF_STOCK):
        return False
    if any(p in low for p in IN_STOCK):
        return True
    return None


def page_text_of(row):
    """The fields identity may be re-asserted against, joined for the matcher.

    `normalize.reassert()` takes a single string, and its pattern is
    boundary-anchored, so a separator between fields cannot fuse two values into
    an identifier present in neither. That anchoring is what makes joining safe
    here; without it this would have to stay a list.
    """
    parts = []
    for field in ("title", "brand", "model", "gtin"):
        val = pick(row, field)
        if val:
            parts.append(collapse_repeat(val))
    return " | ".join(str(p) for p in parts)


def to_raw(row, seed_ref, arm, query_kind, needle, captured_at, job_id=None):
    """One Scraper Studio row -> one flat row in COLLECTOR.md's vocabulary.

    `seed_ref`, `arm`, `query_kind` and `needle` come from the sweep rather than
    from the page: they are what we asked, not what we were told, and the
    distinction is the whole evidence chain.
    """
    out = {
        "seed_ref": seed_ref,
        "arm": arm,
        "query_kind": query_kind,
        "needle": needle,
        "captured_at": captured_at,
    }

    err = pick(row, "error")
    if err:
        out["error"] = str(pick(row, "error_code") or err)
        return out

    for field, key in (("url", "url"), ("buy_label", "buy_label"),
                       ("ships_from", "ships_from"), ("seller", "ships_from")):
        val = pick(row, field)
        if val and key not in out:
            out[key] = _WS.sub(" ", str(val)).strip()

    text = page_text_of(row)
    if text:
        out["page_text"] = text

    stock = stock_of(pick(row, "availability"))
    if stock is not None:
        out["in_stock"] = stock

    currency = currency_of(pick(row, "currency"), row.get("price"))
    if currency:
        out["currency"] = currency

    language = pick(row, "page_language")
    if language:
        out["page_language"] = str(language).strip().lower()[:5]

    status = pick(row, "http_status")
    if status is not None:
        try:
            out["http_status"] = int(status)
        except (TypeError, ValueError):
            pass

    for key in ("sha256", "trace"):
        if row.get(key):
            out[key] = str(row[key])
    if job_id:
        out["job_id"] = str(job_id)

    warning = pick(row, "warning")
    if warning:
        out["warning"] = str(warning)
    return out


def convert(payload, seed_ref, arm, query_kind, needle, captured_at, job_id=None):
    """A whole `bdata scraper run` payload -> (flat rows, drift report).

    The report is what makes an AI-generated schema safe to depend on: it names
    every field the collector returned that this adapter does not understand, so
    drift is an event on the health file rather than a number that quietly stops
    moving.
    """
    rows = _rows_of(payload)
    flat = [to_raw(r, seed_ref, arm, query_kind, needle, captured_at, job_id)
            for r in rows if isinstance(r, dict)]

    known = known_keys()
    unmapped = sorted({k for r in rows if isinstance(r, dict)
                       for k in r if k not in known})
    report = {
        "arm": arm,
        "rows_in": len(rows),
        "rows_out": len(flat),
        "with_currency": sum(1 for r in flat if r.get("currency")),
        "with_language": sum(1 for r in flat if r.get("page_language")),
        "with_buy_label": sum(1 for r in flat if r.get("buy_label")),
        "errors": sum(1 for r in flat if r.get("error")),
        "unmapped_fields": unmapped,
    }
    return flat, report


def _rows_of(payload):
    """Find the row list inside whichever envelope the CLI used."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "rows", "items", "output"):
            if isinstance(payload.get(key), list):
                return payload[key]
        if any(k in payload for k in known_keys()):
            return [payload]
    return []
