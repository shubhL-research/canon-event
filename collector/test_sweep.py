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


# ------------------------------------------------------------------ batching
print("\nBatching, without which the sweep is 124 hours long")

plan = S.plan_arm("DE", [SEED])
check(len(plan) == 2, "one notice plans exactly two loads, one per strategy")
check({p[2] for p in plan} == {S.BRAND_MODEL, S.MODEL_ONLY},
      "both strategies are planned, never one")
check(all(p[0].startswith("https://www.kaufland.de/") for p in plan),
      "the DE plan targets the DE storefront")
check(len({p[0] for p in plan}) == 2,
      "the two strategies produce two DISTINCT urls, or one would shadow the other")
check(S.plan_arm("DE", [{"ref": "x", "name": "", "model": "", "gtin": ""}]) == [],
      "a notice with no identifier plans no loads rather than an empty search")

grouped = S.group_by_input([
    {"title": "a", "input": {"url": "u1"}},
    {"title": "b", "input": {"url": "u1"}},
    {"title": "c", "input": {"url": "u2"}},
    {"title": "d"},
])
check(len(grouped["u1"]) == 2 and len(grouped["u2"]) == 1,
      "rows are split back to the url that produced them")
check(None in grouped,
      "a row with no input echo is kept under None, not dropped")

check(S.cli_batch("c_x", [])[0] == [],
      "an empty batch is a no-op, not a job")


# A whole batch failing must not look like an absence of hazard. This is the
# batching-specific version of the project's central refusal: one failed job now
# covers 40 urls instead of one, so getting it wrong is 40 times as wrong.
def failing_runner(collector_id, urls, timeout_s=None):
    return None, "cli timeout after 3600s on a batch of %d" % len(urls)


rows_f, report_f = S.sweep_arm("DE", "c_de", [SEED], runner=failing_runner)
check(len(report_f["fetch_errors"]) == 2,
      "a failed batch records an error for every url it covered")
check(rows_f and rows_f[0]["tier"] == "DISCARDED",
      "and every covered notice becomes a counted discard, not a silent absence")
check(S.arm_verdict(rows_f[0]) == "WITHHELD",
      "which surfaces as WITHHELD, never as NOT_FOUND")
check(report_f["planned_loads"] == 2 and report_f["batches"] == 1,
      "the report states what was planned, so a short sweep is visible")


# --------------------------------------------------------- the whole pipeline
print("\nEnd to end, offline, from a saved payload")


def fake_runner(payloads):
    """A batch runner that replays canned rows per arm.

    Mirrors the real cli_batch contract: given many urls, return a flat list of
    rows each carrying the `input.url` that produced it. That echo is what makes
    batching safe, so the fake has to reproduce it or the test would pass against
    a mapping that does not work in production.
    """
    def run(collector_id, urls, timeout_s=None):
        rows, error = [], None
        for arm, marker in (("DE", "kaufland.de"), ("US", "amazon.com"),
                            ("IN", "flipkart.com")):
            if not any(marker in u for u in urls):
                continue
            canned, error = payloads.get(arm, ([], None))
            if error:
                return None, error
            for url in urls:
                for row in canned or []:
                    rows.append({**row, "input": {"url": url}})
        return rows, error
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

# ----------------------------------------------------------------- publishing
print("\nThe payload the wall reads")

import publish as P                                                # noqa: E402

PUB_SEEDS = [
    dict(SEED),
    {**SEED, "ref": "A12/00002/24", "gtin": None, "model": "KX-77B"},
    # No identifier at all: this notice is unsearchable, and that is the figure
    # no collector can contaminate.
    {**SEED, "ref": "A12/00003/24", "gtin": None, "model": None,
     "hazard": "Button cell batteries pose an ingestion hazard to children."},
    # A gtin field holding a value that fails its own check digit. Six real
    # Safety Gate notices look like this, and they are not searchable.
    {**SEED, "ref": "A12/00004/24", "gtin": "3973500298", "model": None},
]

check(P.searchable({"gtin": "8721003407246"}), "a valid GTIN is searchable")
check(P.searchable({"model": "KX-77B"}), "a model number is searchable")
check(not P.searchable({"gtin": "3973500298"}),
      "a gtin that fails its own check digit is NOT searchable")
check(not P.searchable({"gtin": None, "model": "  "}),
      "whitespace is not an identifier")

uns = P.unsearchable(PUB_SEEDS)
check(uns["n"] == 2 and uns["d"] == 4,
      "the unsearchable count includes the bad-check-digit notice")
check(uns["contaminated"] is False,
      "unsearchable is uncontaminated: it survives every arm being withheld")
check(uns["ci95"][0] > 0 and uns["ci95"][1] < 1,
      "and it carries a Wilson interval, not a bare proportion")

pub_rows, pub_health = S.run(
    PUB_SEEDS, {"DE": "c_de"},
    runner=fake_runner({"DE": ([LIVE_ROW], None)}))
payload = P.build(pub_rows, pub_health, PUB_SEEDS,
                  reports=pub_health.get("reports") or [])

check(set(payload) == {"sweep_id", "swept_at", "variant", "freshness_bound_s",
                       "arms", "rows", "stats", "provenance"},
      "the payload carries exactly the eight keys wall.html reads")
check(payload["provenance"]["fixture"] is False,
      "a live payload is not stamped as a fixture")
check(payload["stats"]["survival"]["contaminated"] is True,
      "a figure that depends on a collector is stamped contaminated")
check(payload["stats"]["unsearchable"]["contaminated"] is False,
      "a figure computed from the free corpus is not")
check(payload["stats"]["survival"]["d"] == 2,
      "the buyable denominator counts only SEARCHABLE notices, never the corpus")
check(payload["stats"]["precision"]["v"] is None
      and "hand adjudication" in payload["stats"]["precision"]["pending"],
      "precision is PENDING with the count needed, never invented from the sweep")
check("recall" in payload["stats"]["precision"],
      "the capture-recapture floor rides with it, because recall is bounded not measured")
check(payload["stats"]["arms_measured"]["d"] == 1,
      "arms_measured reports against the arms actually swept")
check(all("hazard_class" in r for r in payload["rows"] if r.get("hazard")),
      "every row carries the transparent hazard classification the hero uses")
check(payload["stats"]["arithmetic"]["search_page_loads"] > 0,
      "the credit arithmetic is derived from the plan, so a reader can re-add it")

graded = P.precision(pub_rows, {"filled": 50, "precision": 0.94,
                                "ci95": [0.83, 0.98], "v": 0.94})
check(graded.get("v") == 0.94,
      "once enough listings are hand-verified, the real figure is published")

print("\n" + ("%d FAILURES" % len(FAILURES) if FAILURES else "all sweep tests passed"))
sys.exit(1 if FAILURES else 0)
