#!/usr/bin/env python3
"""Pull the seed corpus from both regulators. Zero Bright Data credits.

TWO SOURCES, ONE SHAPE
----------------------
US   CPSC official REST API, saferproducts.gov. Free, no key, no terms issue.
EU   Safety Gate / RAPEX. The official portal at ec.europa.eu is JavaScript
     rendered with no documented public JSON API, so this reads the Opendatasoft
     open-data mirror of the same dataset. Every record carries `rapex_url`,
     which points back at the official EU alert page, so each seed remains
     traceable to the primary source and any single row can be checked by hand.
     That mirror dependency is disclosed in the README rather than hidden.

WHY THE EU HALF MATTERS
-----------------------
BORDER ESCAPE is defined as: of EU-recalled products, what share are still
buyable from an Indian residential IP, in a country with no consumer recall
portal at all. It cannot be computed from CPSC notices. Without this pull the
measure has no input data and renders as PENDING.

AGE BANDS
---------
Survival is read off the notice date, so the corpus must span ages, not just
recent alerts. Seeds are drawn around 30, 90, 365 and 730+ days so the isotonic
fit has support across its whole range instead of one dense cluster.

Run:  python data/pull_seeds.py
Writes data/seeds.json. make_fixture.py picks it up automatically.
"""

import datetime
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).parent
TODAY = datetime.date(2026, 8, 19)
TARGET_PER_BAND = 26          # 4 bands x 26 x 2 regulators, trimmed to ~180
BANDS = [30, 90, 365, 730]

CPSC = "https://www.saferproducts.gov/RestWebServices/Recall"
EU = ("https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
      "healthref-europe-rapex-en/records")

UA = {"User-Agent": "canon-event/0.1 (hackathon research; contact via repo)"}


def get(url, params):
    q = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    req = urllib.request.Request(f"{url}?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def clean(s):
    """Collapse whitespace. Never rewrite the regulator's words beyond that."""
    return re.sub(r"\s+", " ", str(s or "")).strip()


def window(days, span=45):
    """A date window centred on an age band."""
    centre = TODAY - datetime.timedelta(days=days)
    return (centre - datetime.timedelta(days=span // 2),
            centre + datetime.timedelta(days=span // 2))


# ------------------------------------------------------------------ CPSC (US)

# CPSC serves an EMPTY Products[].Model on nearly every record. The model number
# is instead written into the product NAME as free text:
#   "COMMOWNER Electric Pressure Washers, model numbers HD14P-Z and HX18"
#   "CuberShop Magnetic Stickerless Speed Cubes, model YJ MGC 5x5"
# Trusting the structured field yields a 0% identifier rate and would hand us a
# fake UNSEARCHABLE rate near 100%. So the identifier is mined from the prose.
MODEL_IN_NAME = re.compile(
    r"\bmodels?\s*(?:numbers?|nos?\.?|#)?\s*:?\s*(.+)$", re.I)
STOP_AT = re.compile(r"\s+(?:and|or|sold|with|in|for)\b", re.I)


# The identifier is in the feed. We were not opening the key it lives in.
#
# Products[].Model is empty on 0 of 57 records checked live. The top-level
# Description is non-empty on 57 of 57 and names the model in prose:
#   "This recall involves CuberShop's Magnetic Stickerless Speed Cubes,
#    model YJ MGC 5x5."
# Reading only Products[].Model and the product name produced a 96% unsearchable
# rate for CPSC. That is a claim about our own parser, not about the regulator,
# and publishing it would have been false by more than its confidence interval.
CUE = re.compile(
    r"\b(?:model|models|catalog|catalogue|sku|item|style|part|series)\b"
    r"(?:\s*(?:numbers?|nos?\.?|#|code)\b)?\s*:?\s*([^.;)]{2,60})", re.I)


def mine_identifier(*texts):
    """Recover an identifier from regulator prose, conservatively.

    Requires a cue word, then takes the first token carrying BOTH a letter and a
    digit. Anything recovered is then gated through extract.identifier.classify(),
    the same rule the wall publishes, so this can widen coverage but can never
    invent a searchable identifier the project would not otherwise accept.
    """
    for t in texts:
        if not t:
            continue
        for m in CUE.finditer(str(t)):
            for tok in re.split(r"[ ,;/]+", m.group(1).strip(" \"'")):
                tok = tok.strip(" \".,;:()'")
                if (len(tok) >= 4 and any(c.isalpha() for c in tok)
                        and any(c.isdigit() for c in tok)):
                    if _classify(tok)["verdict"] == "searchable":
                        return tok
    return None


def _classify(tok):
    import importlib.util
    global _CLS
    try:
        return _CLS(tok)
    except NameError:
        spec = importlib.util.spec_from_file_location(
            "identifier", pathlib.Path(__file__).parent.parent / "extract" / "identifier.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _CLS = mod.classify
        return _CLS(tok)


def model_from_name(name):
    """Mine a model token out of a CPSC product name.

    Returns None rather than a guess. A wrong identifier is worse than no
    identifier: it sends the matcher looking for a product that does not exist
    and the miss is then silently counted as 'not on sale'.
    """
    m = MODEL_IN_NAME.search(name or "")
    if not m:
        return None
    tail = m.group(1).strip(" ,.;:")
    tail = STOP_AT.split(tail)[0].strip(" ,.;:")
    # "10-Liter and 15-Liter models" leaves a size, not a model. Require a token
    # that carries both a letter and a digit, which is what a real SKU looks like.
    if not tail or len(tail) < 3 or len(tail) > 40:
        return None
    if not (any(c.isalpha() for c in tail) and any(c.isdigit() for c in tail)):
        return None
    return tail


def brand_from_name(name):
    """First word of a CPSC product name is almost always the brand."""
    first = clean(name).split(" ")[0].strip(" ,.")
    return first if len(first) > 2 and first[0].isupper() else ""


def pull_cpsc(days):
    start, end = window(days)
    try:
        rows = get(CPSC, {"format": "json",
                          "RecallDateStart": start.isoformat(),
                          "RecallDateEnd": end.isoformat()})
    except Exception as e:
        print(f"  CPSC {days}d FAILED: {e}", file=sys.stderr)
        return []

    out = []
    for r in rows:
        products = r.get("Products") or []
        hazards = r.get("Hazards") or []
        if not products or not hazards:
            continue
        p, h = products[0], hazards[0]
        hazard = clean(h.get("Name")) or clean(h.get("HazardType"))
        if not hazard:
            continue

        firm = ""
        for key in ("Manufacturers", "Importers", "Distributors", "Retailers"):
            v = r.get(key) or []
            if v:
                firm = clean(v[0].get("Name"))
                break

        date = clean(r.get("RecallDate"))[:10]
        if not date:
            continue

        pname = clean(p.get("Name"))
        out.append({
            "authority": "CPSC",
            "ref": clean(r.get("RecallNumber")),
            "published": date,
            "name": pname,
            "brand": firm or brand_from_name(pname),
            "model": (clean(p.get("Model")) or model_from_name(pname)
                      or mine_identifier(r.get("Description"), r.get("Title"),
                                         p.get("Description"))),
            "gtin": next((u for u in (r.get("ProductUPCs") or [])
                          if str(u).isdigit() and 8 <= len(str(u)) <= 14), None),
            "category": clean(p.get("Type")) or None,
            "hazard": hazard,
            "url": clean(r.get("URL")) or f"https://www.cpsc.gov/Recalls/{r.get('RecallNumber')}",
        })
    return out


# ------------------------------------------------------------- Safety Gate (EU)

GTIN_RE = re.compile(r"\b\d{8,14}\b")


def pull_eu(days):
    start, end = window(days)
    try:
        data = get(EU, {
            "limit": 100,
            "where": (f"alert_date >= '{start.isoformat()}' "
                      f"AND alert_date <= '{end.isoformat()}'"),
            "select": ("alert_number,alert_date,product_name,product_brand,"
                       "product_model_type,product_barcode,product_category,"
                       "alert_description,rapex_url,alert_level,product_type"),
            "order_by": "alert_date desc",
        })
    except Exception as e:
        print(f"  EU {days}d FAILED: {e}", file=sys.stderr)
        return []

    out = []
    for r in data.get("results", []):
        hazard = clean(r.get("alert_description"))
        name = clean(r.get("product_name")) or clean(r.get("product_type"))
        if not hazard or not name:
            continue

        # The model field frequently carries several labelled codes across
        # multiple lines. Keep the first line as the model and mine the whole
        # field for a barcode-shaped run of digits.
        raw_model = clean(r.get("product_model_type"))
        model = raw_model.split(" ")[0] if raw_model else None
        if model and len(model) < 3:
            model = raw_model or None

        gtin = clean(r.get("product_barcode")) or ""
        if not GTIN_RE.fullmatch(gtin):
            m = GTIN_RE.search(gtin) or GTIN_RE.search(raw_model or "")
            gtin = m.group(0) if m else None

        brand = clean(r.get("product_brand"))
        if brand.lower() in ("unknown", "none", ""):
            brand = ""

        out.append({
            "authority": "SAFETY_GATE",
            "ref": clean(r.get("alert_number")),
            "published": clean(r.get("alert_date"))[:10],
            "name": name,
            "brand": brand,
            "model": model,
            "gtin": gtin or None,
            "category": clean(r.get("product_category")) or None,
            "hazard": hazard,
            "url": clean(r.get("rapex_url")) or "https://ec.europa.eu/safety-gate-alerts/",
        })
    return out


# ---------------------------------------------------------------- selection

CONSUMER_HINTS = ("toy", "child", "infant", "baby", "electric", "battery",
                  "charger", "light", "lamp", "cosmetic", "jewel", "cloth",
                  "appliance", "kitchen", "furniture", "sport", "bicycle",
                  "scooter", "power", "fire", "candle", "phone", "audio")


def score(s):
    """Prefer seeds that can actually be tested on a marketplace.

    An identifier is worth far more than anything else, because without one the
    matcher cannot form a query at all. Beyond that, prefer consumer goods
    plausibly sold online over industrial or vehicle recalls.
    """
    v = 0
    if s.get("gtin"):
        v += 6
    if s.get("model"):
        v += 4
    if s.get("brand"):
        v += 2
    blob = f"{s['name']} {s.get('category') or ''}".lower()
    if any(h in blob for h in CONSUMER_HINTS):
        v += 3
    if len(s["hazard"]) > 40:
        v += 1
    return v


def main():
    seeds, seen = [], set()
    print(f"pulling seeds, today = {TODAY.isoformat()}\n")

    for days in BANDS:
        start, end = window(days)
        print(f"age band ~{days}d  ({start} to {end})")
        for label, rows in (("US CPSC   ", pull_cpsc(days)),
                            ("EU SafetyGate", pull_eu(days))):
            rows.sort(key=score, reverse=True)
            kept = 0
            for s in rows:
                key = (s["authority"], s["ref"])
                if key in seen or not s["ref"]:
                    continue
                pub = datetime.date.fromisoformat(s["published"])
                s["days"] = (TODAY - pub).days
                s["band"] = days
                seen.add(key)
                seeds.append(s)
                kept += 1
                if kept >= TARGET_PER_BAND:
                    break
            print(f"  {label}  {len(rows):4d} available, {kept:3d} kept")
        print()

    seeds.sort(key=lambda s: -s["days"])
    out = {
        "_source_us": "CPSC official REST API, saferproducts.gov/RestWebServices/Recall",
        "_source_eu": ("EU Safety Gate / RAPEX via the Opendatasoft open-data mirror. "
                       "The official ec.europa.eu portal is JavaScript rendered with no "
                       "documented public JSON API. Every EU seed carries the official "
                       "alert URL so it remains traceable to the primary source."),
        "_credits_spent": 0,
        "_pulled": TODAY.isoformat(),
        "_note": "Hazard text is the regulator's verbatim wording. Never paraphrased.",
        "seeds": seeds,
    }
    (HERE / "seeds.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                     encoding="utf-8")

    us = sum(1 for s in seeds if s["authority"] == "CPSC")
    eu = len(seeds) - us
    with_id = sum(1 for s in seeds if s.get("model") or s.get("gtin"))
    with_gtin = sum(1 for s in seeds if s.get("gtin"))
    print(f"TOTAL {len(seeds)} seeds   US {us}   EU {eu}")
    print(f"  with an identifier {with_id} ({with_id/len(seeds):.0%})")
    print(f"  with a GTIN        {with_gtin}")
    print(f"  age span           {seeds[-1]['days']} to {seeds[0]['days']} days")
    print(f"\nwrote seeds.json")


if __name__ == "__main__":
    main()
