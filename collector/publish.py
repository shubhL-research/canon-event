"""Sweep output -> the payload the wall reads.

WHY THIS FILE EXISTS
--------------------
The README promises that swap day is `cp` rather than an integration, and that
promise was not true yet. `sweep.py` writes rows and a health file;
`wall.html` reads one object carrying eight keys, of which the largest is
`stats`. Nothing computed the statistics from real rows. This is the last mile,
and until it existed the wall could only ever show fixture data.

Every figure here is computed from the sweep, never carried over from the
fixture. A payload that silently inherits a fixture number is worse than one
that shows nothing: it looks measured.

CONTAMINATION IS A PROPERTY OF EACH FIGURE, NOT OF THE PAGE
----------------------------------------------------------
Each statistic is stamped `contaminated: true` when it depends on a collector
and `false` when it does not. That flag is what lets the wall strike exactly the
figures a broken arm invalidates while leaving the rest live.

`unsearchable` is the one that matters. It is computed entirely from the free
government corpus, so no scraper can contaminate it and it survives every arm
failing at once. When the whole board goes black it is still publishable, which
is the reason the project has something to say on its worst day.

WHAT IS DELIBERATELY LEFT PENDING
---------------------------------
`precision` cannot be computed from the sweep. It requires a human to open
listings and adjudicate them, which is what `golden/` is for. Rather than
inventing a number or quietly omitting it, the field renders as PENDING with the
count still needed. A precision figure is the number that qualifies every other
number on the wall, and asserting it without the worksheet would be the single
most dishonest thing this project could do.

Standard library only.
"""

import datetime
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "stats"))
sys.path.insert(0, str(ROOT / "data"))

from wilson import proportion, wilson                        # noqa: E402
from recapture import from_rows as recapture_from_rows       # noqa: E402
from survival import survival_curve, observations_from_rows  # noqa: E402
from make_fixture import hazard_class                        # noqa: E402
from normalize import gtin_check_digit_ok                    # noqa: E402
from extract.identifier import UNSEARCHABLE, classify        # noqa: E402

# How long a sweep may speak in the present tense. Mirrors health.FRESHNESS_BOUND_S.
FRESHNESS_BOUND_S = 14400

# Rows the wall renders before the fold. The rest ship in the structured output,
# and the footer says so rather than letting the reader assume they saw everything.
ROWS_SHOWN = 40

# Which storefront each arm actually measured. The wall names it on screen, so it
# has to come from the payload rather than be assumed by the renderer.
ARM_HOST = {"US": "amazon.com", "DE": "kaufland.de", "IN": "flipkart.com"}

# Hand-adjudicated listings required before a precision figure may be published.
# Below this the interval is too wide to qualify anything, and a precision claim
# that cannot qualify the numbers underneath it is decoration.
PRECISION_MINIMUM = 50

# The code normalize.py files BOTH of its AMBER outcomes under.
#
# "identifier re-asserted but no active buy control" and "identifier not
# re-asserted on the fetched page" are opposite facts about the same page: the
# first says we found the product and could not buy it, the second says we never
# found the product. Counting them in one bucket says neither. The row-level
# reason separates them, so the reason is what gets counted.
AMBER_CODE = "AMBER"


def _identifier(seed_or_row):
    """The owned searchability verdict for one notice.

    ONE RULE, AND IT LIVES IN extract/identifier.py
    -----------------------------------------------
    This file used to carry a second copy of the rule, and the two disagreed. The
    copy here accepted any non-empty model string, so "Year 2026 Teryx4 H2" and
    "Year 2019-2025 UMAX Bistro" counted as searchable identifiers. Over the full
    207-notice corpus that copy called 19 unsearchable where the owned rule calls
    21. Two rules is two numbers, and the wall was printing the wrong one.

    The check digit is not a third rule. classify() tests the SHAPE of a barcode;
    whether those digits are a real GTIN is modulo-10 arithmetic owned by
    collector/normalize.py. Six Safety Gate notices hold a value in the gtin field
    that fails its own check digit, at lengths 9, 10, 12 and 14, because the
    notifying country types into a free-text box. The field does not contain a
    GTIN, so it is not handed to classify() as one. See README, "Six of the Safety
    Gate GTINs are not GTINs".
    """
    gtin = seed_or_row.get("gtin")
    if not (gtin and gtin_check_digit_ok(gtin)):
        gtin = None
    return classify(seed_or_row.get("model"), gtin, seed_or_row.get("name") or "")


def searchable(seed_or_row):
    """Did this notice carry anything a matcher could search for?

    The denominator of the unsearchable rate, and the reason it can be computed
    without a scraper.
    """
    return _identifier(seed_or_row)["verdict"] != UNSEARCHABLE


def unsearchable(seeds):
    """Share of the corpus that cannot be searched at all.

    Computed entirely from the free government corpus. No collector touches it,
    so it is the one headline that survives every arm being withheld.
    """
    d = len(seeds)
    n = sum(1 for s in seeds if not searchable(s))
    stat = proportion(n, d, "unsearchable")
    stat["contaminated"] = False
    stat["note"] = ("Pooled across regulators. CPSC and Safety Gate do not fail the "
                    "same way and a single rate averaging them describes neither, so "
                    "the split in stats.unsearchable_by_authority is published beside "
                    "this figure and never instead of it.")
    return stat


def unsearchable_by_authority(seeds):
    """The unsearchable rate split by regulator, with an interval on each.

    This is the most defensible fact the project holds and the pooled rate hides
    it. CPSC publishes a Products[].Model field that is empty on 183 of 183
    product records across four date windows; every one of the 104 Safety Gate
    alerts carries a typed barcode. Those are two different failures, and anyone
    can confirm both with curl.

    `by_kind` names the mechanism behind each unsearchable notice, straight from
    the owned rule, so a reader can see whether a regulator named nothing at all
    or named something too generic to search.
    """
    groups = {}
    for seed in seeds:
        authority = seed.get("authority") or "UNKNOWN"
        group = groups.setdefault(authority, {"n": 0, "d": 0, "by_kind": {}})
        group["d"] += 1
        verdict = _identifier(seed)
        if verdict["verdict"] == UNSEARCHABLE:
            group["n"] += 1
            kind = verdict["kind"]
            group["by_kind"][kind] = group["by_kind"].get(kind, 0) + 1

    out = {}
    for authority, group in sorted(groups.items()):
        stat = proportion(group["n"], group["d"], "unsearchable, %s" % authority)
        stat["by_kind"] = group["by_kind"]
        stat["contaminated"] = False
        out[authority] = stat
    return out


def still_buyable(rows, arms=None):
    """Share of SEARCHABLE notices found still on sale.

    The denominator excludes notices we could never look for. Scoring an
    unsearchable notice as not-buyable would convert our own blindness into
    evidence of safety, which is the failure this project exists to refuse.

    Contamination is decided by whether a collector was WITHHELD, not by whether
    a collector was involved. Marking it contaminated unconditionally redacted a
    figure we had genuinely measured, 0 of 58 from 5,812 adjudicated listings, and
    a redaction over a real measurement is the same lie as a number over a
    broken one, pointed the other way. A DEGRADED arm makes the figure partial
    rather than unpublishable, which is what the contract's partial stamp is for.
    """
    scored = [r for r in rows if searchable(r)]
    n = sum(1 for r in scored if r["tier"] == "RED")
    states = [a.get("state") for a in (arms or {}).values()]
    withheld = "WITHHELD" in states
    partial = "DEGRADED" in states or "STALE" in states

    if not scored:
        return {"v": None, "n": 0, "d": 0, "ci95": None, "contaminated": True,
                "pending": "No searchable notice reached a verdict."}
    stat = proportion(n, len(scored), "still buyable")
    stat["contaminated"] = withheld
    if partial and not withheld:
        stat["partial"] = ("One collector is degraded, so this is a floor: a "
                           "listing it failed to match could still exist.")
    return stat


# Measured directly against saferproducts.gov on 2026-08-20, across the four date
# windows the corpus is drawn from. Reproduce it with:
#
#   curl -s "https://www.saferproducts.gov/RestWebServices/Recall?format=json#   &RecallDateStart=2026-07-20&RecallDateEnd=2026-08-13" #     | python3 -c "import json,sys; d=json.load(sys.stdin); #       print(sum(1 for r in d for p in r['Products'] if not (p.get('Model') or '').strip()), #             'of', sum(len(r['Products']) for r in d))"
#
# These are counts of a field in a public feed, not estimates, so they carry no
# interval. If CPSC adds the field, this headline stops being true and should be
# retired rather than quietly softened.
CPSC_MODEL_FIELD_EMPTY = {
    "empty": 183,
    "checked": 183,
    "eu_with_barcode": 104,
    "measured_on": "2026-08-20",
    "source": "saferproducts.gov/RestWebServices/Recall",
    "note": ("CPSC serves Products[].Model empty on every product record checked, "
             "and writes the model number into the Description prose instead. EU "
             "Safety Gate carries a typed barcode on every alert. Both feeds are "
             "free and public, so this figure is reproducible without any scraper."),
}


def hero(rows, seeds):
    """The headline sentence, and it is allowed to be a different sentence.

    THE HEADLINE IS NOT GUARANTEED TO EXIST
    ---------------------------------------
    The fixture's headline is "N products recalled for burning or choking children
    are in a cart right now". That sentence requires at least one RED row whose
    hazard names a burn or choking mechanism and names children. The first real
    sweeps produced no RED rows at all: 4,209 listings scraped across two
    countries, sixty recall notices, zero identifiers re-asserted on a live page
    with an active buy control.

    So the sentence has to be able to change, and it must not be the fixture's
    sentence rendered over a zero. A headline that survives its own evidence
    disappearing is not a headline, it is a slogan.

    The fallback is the unsearchable rate, and it is a better finding rather than
    a consolation. It is computed entirely from the free government corpus, so no
    collector failure can touch it, and it indicts the regulator rather than a
    seller: a notice naming no searchable identifier cannot be checked by anyone,
    ever, including the authority that published it.

    The classification behind the primary sentence stays a transparent keyword
    rule recorded on every row, so a reader can audit which words triggered it.
    """
    qualifying = [r for r in rows
                  if r["tier"] == "RED" and r.get("hazard_class", {}).get("qualifies")]
    out = {"n": len(qualifying), "oldest_days": 0, "oldest": None}

    if qualifying:
        oldest = max(qualifying, key=lambda r: r.get("days") or 0)
        out["oldest_days"] = oldest.get("days") or 0
        out["oldest"] = {
            "name": oldest["name"],
            "ref": oldest["source"]["ref"],
            "authority": oldest["source"]["authority"],
            "hazard": oldest["hazard"],
        }
        out["sentence"] = ("%d products recalled for burning or choking children "
                           "are in a cart right now. The oldest has been buyable "
                           "for %d days." % (len(qualifying), out["oldest_days"]))
        out["basis"] = "measured"
        return out

    # No confirmed listing. Lead with the figure no scraper can contaminate.
    #
    # The headline is the ASYMMETRY, not the pooled rate. Two regulators publish
    # the same kind of notice into the same kind of feed, and one of them fills
    # the identifier field while the other leaves it empty every single time.
    # That is a fact about machine-readability, which is the subject of this
    # hackathon, and any reader can reproduce it with one curl command.
    #
    # The pooled rate was the old headline and it was a worse claim twice over:
    # it averaged two populations that behave nothing alike, and it was attached
    # to the sentence "Nobody can check whether those products ever left the
    # shelves", which our own AMBER tier refutes by forming queries for exactly
    # those notices. A sentence the codebase disproves cannot lead the page.
    uns = unsearchable(seeds)
    empty = CPSC_MODEL_FIELD_EMPTY
    out["sentence"] = ("The US recall feed has a model-number field. It is empty on "
                       "%d of %d product records. Every one of %d EU alerts carries "
                       "a barcode." % (empty["empty"], empty["checked"], empty["eu_with_barcode"]))
    out["basis"] = "unsearchable_fallback"
    out["fallback_reason"] = (
        "No listing reached RED in this sweep: no recalled identifier was "
        "re-asserted on a fetched page carrying an active buy control. The "
        "headline is therefore the figure computed from the regulators' own "
        "corpus, which no collector failure can affect.")
    return out


def precision(rows, graded=None):
    """Precision, or an explicit PENDING with the count still needed.

    Cannot be derived from the sweep. It needs a human opening listings, which is
    what golden/ exists for. Inventing it, or omitting it and letting the other
    figures stand unqualified, are both worse than saying it is not ready.
    """
    if graded and graded.get("filled", 0) >= PRECISION_MINIMUM:
        return dict(graded, contaminated=False)
    filled = (graded or {}).get("filled", 0)
    return {
        "v": None, "n": filled, "d": PRECISION_MINIMUM, "ci95": None,
        "contaminated": False,
        "pending": ("Requires hand adjudication. %d of %d listings verified; %d "
                    "to go before precision can be published. See golden/HOW-TO.md."
                    % (filled, PRECISION_MINIMUM, PRECISION_MINIMUM - filled)),
        "recall": recapture_from_rows(rows),
    }


def border_escape(rows, seeds, arms=None):
    """EU-recalled products found on a non-EU marketplace.

    The numerator needs the IN arm to have measured. This used to emit v=0.0
    unconditionally, without ever reading arm state, against the promise in this
    file's own docstring. A zero read as "nothing escaped" while the arm that
    would have found an escape had not looked.

    THE DENOMINATOR IS WHAT WAS SWEPT, NOT WHAT EXISTS
    --------------------------------------------------
    It also scored against the full 104-notice EU corpus while a trial slice had
    queried 60 of them. That counts 44 notices nobody opened as non-escapes, and
    an unlooked-at notice is not evidence of anything. The effect is not cosmetic:
    it narrows the interval from [0, 6.2] to [0, 3.6], so the sweep is credited
    with a precision it did not buy.

    So `seeds` here is the slice actually swept. `unsearchable` is the one figure
    that belongs to the whole corpus, because it needs no sweep at all.
    """
    eu = [s for s in seeds if s["authority"] == "SAFETY_GATE"]
    eu_searchable = [s for s in eu if searchable(s)]
    out = {"eu_seeds": len(eu), "eu_searchable": len(eu_searchable),
           "contaminated": True}

    state = (arms or {}).get("IN", {}).get("state")
    if state != "MEASURED":
        out.update(v=None, n=0, d=len(eu_searchable), ci95=None,
                   pending=("The India arm is %s, so no EU-recalled product was "
                            "looked for outside the EU. A zero here would report "
                            "that nothing escaped, which is a finding we have not "
                            "made." % (state or "not in this sweep")))
        return out
    if not eu_searchable:
        out.update(v=None, n=0, d=0, ci95=None,
                   pending="No EU notice carries a searchable identifier.")
        return out

    refs = {s["ref"] for s in eu_searchable}
    escaped = [r for r in rows
               if r["source"]["ref"] in refs and r.get("arms", {}).get("IN") == "RED"]
    out.update(proportion(len(escaped), len(eu_searchable), "border escape"))
    return out


def discard_code(entry):
    """One discard reason, mapped to the code it is counted under.

    normalize.py files both AMBER outcomes under the code "AMBER", so the code on
    its own puts every adjudication in one bucket. A single bucket at 100% is the
    opaque count this panel exists to refuse: it looks exactly like a matcher that
    stopped working. The reason text is already specific, so it decides the code.

    A reason that matches nothing recognised gets its own bucket rather than
    joining one of these. If normalize.py grows a third AMBER outcome it surfaces
    on the wall as an unrecognised code instead of silently inflating a neighbour.
    """
    code = entry.get("code") or "unspecified"
    if code != AMBER_CODE:
        return code
    reason = (entry.get("reason") or "").lower()
    if "not re-asserted" in reason:
        return "identifier_not_reasserted"
    if "no active buy control" in reason:
        return "reasserted_no_buy_control"
    return "amber_reason_unrecognised"


def discarded(rows, reports):
    """Discard rate and the reason codes behind it.

    Reported by cause rather than as a single number, because an opaque discard
    count is indistinguishable from a broken matcher.

    The denominator is the number of ADJUDICATION DECISIONS, not the number of
    search loads. One load returns thirty to four hundred listings and every one
    of them is decided, so dividing discards by loads produced a ratio above 1 and
    a Wilson call that raised, caught on the first live payload. A rate has to be
    discards over things decided or it is not a rate.

    THE RATE AND THE BREAKDOWN COUNT DIFFERENT THINGS, AND BOTH ARE NAMED
    ---------------------------------------------------------------------
    The rate is per listing adjudicated. The breakdown cannot be, because the
    per-arm normaliser report counts codes and throws the reason away, and the
    reason is the only thing that separates the two AMBER outcomes. So the
    breakdown counts the discard entries carried on the published rows, one per
    notice per arm. Adding `by_code` up will not reach `n`, and `by_code_scope`
    says why rather than leaving a reader to discover it.

    Apportioning the listing-scale total across the row-scale reasons would close
    that gap and would be invented. A row keeps only its strongest verdict, so its
    reason is not a sample of the reasons the listings under it were given.
    """
    total, decided = 0, 0
    for report in reports:
        for count in (report.get("by_code") or {}).values():
            total += count
        decided += report.get("out", 0)

    by_code = {}
    for row in rows:
        for entry in row.get("discarded") or []:
            code = discard_code(entry)
            by_code[code] = by_code.get(code, 0) + 1

    out = {"n": total, "d": decided, "by_code": by_code,
           "by_code_n": sum(by_code.values()),
           "by_code_scope": ("Counted per published row per arm, because that is "
                             "where the reason survives. The rate above is counted "
                             "per listing adjudicated, so these do not sum to it."),
           "contaminated": True}
    # A listing may carry more than one discard reason, so the count can exceed
    # the number decided. Report the counts and withhold the ratio rather than
    # inventing a denominator that makes the arithmetic work.
    if decided and total <= decided:
        out["v"] = round(total / decided, 4)
        out["ci95"] = [round(x, 4) for x in wilson(total, decided)]
    else:
        out["v"] = None
        out["ci95"] = None
        out["note"] = ("Reported as counts by cause. A row can carry more than one "
                       "discard reason, so a single ratio would misstate it.")
    return out


def arithmetic(seeds, reports):
    """The credit sum, shown as working rather than as a total.

    A cost figure nobody can re-derive is a cost figure nobody can check.
    """
    planned = sum(r.get("planned_loads", 0) for r in reports)
    arms = len({r["arm"] for r in reports})
    searchable_seeds = sum(1 for s in seeds if searchable(s))
    return {
        "corpus_seeds": len(seeds),
        "searchable_seeds": searchable_seeds,
        "queries_per_seed_per_arm": 2,
        "arms": arms,
        "search_page_loads": planned,
        "batches": sum(r.get("batches", 0) for r in reports),
        "total_page_loads": planned,
        # The batch count comes from the normaliser reports, which are absent on a
        # replay. Printing "submitted as 0 batch jobs" beside a real load count
        # reads as a collector that ran nothing, so the clause is omitted rather
        # than printed as a zero we do not actually know.
        # STATE THE DERIVATION THAT HOLDS, not one that reads well.
        #
        # This asserted "180 searchable x 2 queries x 3 arms = 1107". That product
        # is 1080. The right-hand side was never computed from the left: `planned`
        # is summed from the per-arm plans, which issue 369 unique URLs each. The
        # 27 gap happens to equal the unsearchable count, so a reader who
        # multiplied concluded we had queried the notices we say we never
        # submitted. A cost figure nobody can re-derive is the thing this block
        # exists to prevent.
        "working": (("%d unique URLs planned per arm x %d arms = %d search loads, "
                     "from %d searchable of %d notices"
                     % (planned // arms if arms else planned, arms, planned,
                        searchable_seeds, len(seeds)))
                    + ((", submitted as %d batch jobs."
                        % sum(r.get("batches", 0) for r in reports))
                       if sum(r.get("batches", 0) for r in reports) else ".")),
        # Counted, not typed. This sentence carried a hardcoded 96 from a corpus
        # pull that missed the CPSC Description key, and the seed correction left
        # it stating a number the same block contradicts two lines above.
        "note": ("Only searchable notices are queried. %d of %d notices in this plan "
                 "carry no usable identifier and were never submitted, so they cost "
                 "nothing. Batching is what makes a full sweep possible: one job per "
                 "40 urls rather than one job per url."
                 % (len(seeds) - searchable_seeds, len(seeds))),
    }


def adversarial():
    """The precision probes, if they have been run. Absent rather than faked."""
    path = ROOT / "data" / "adversarial.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {"n": doc["n"], "all_discarded": doc["all_discarded"],
            "by_kind": doc["by_kind"], "note": doc["note"]}


def controls():
    """The positive control set, if it has been run. Absent rather than faked.

    THE PAIR IS THE CLAIM, AND HALF OF IT WAS INVISIBLE
    ---------------------------------------------------
    adversarial.json shows the matcher REFUSES what it should: 21 deliberately
    confusable near-misses, every one discarded. It has always been published.
    control.json shows the matcher ACCEPTS what it should: 13 known-good products
    carrying real recall identifiers, on pages written in each marketplace's own
    vocabulary, every one reaching RED. It was written on every run and read by
    nobody.

    That asymmetry mattered more here than almost anywhere, because this sweep's
    headline is a ZERO. A wall that proves only "we do not over-fire" leaves the
    single question a zero raises unanswered: is the matcher firing at all. Both
    halves are needed before a zero describes the market rather than the code.
    """
    path = ROOT / "data" / "control.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {"n": doc["n"], "all_red": doc["all_red"],
            "by_kind": doc["by_kind"], "note": doc["note"]}


def annotate(rows):
    """Attach the hazard classification the hero sentence is computed from."""
    for row in rows:
        if "hazard_class" not in row and row.get("hazard"):
            row["hazard_class"] = hazard_class(row["hazard"])
    return rows


def build(rows, health_doc, seeds, reports=None, graded=None, variant="live",
          corpus=None):
    """Assemble the wall payload. Every figure computed, none inherited.

    TWO DIFFERENT DENOMINATORS, AND CONFUSING THEM PRODUCES A FALSE HEADLINE
    -----------------------------------------------------------------------
    `seeds` are the notices this sweep actually visited. `corpus` is every notice
    the regulators published. Most figures belong to the first; UNSEARCHABLE
    belongs to the second, and it is the one that matters most.

    Caught on the first live payload: a trial slice selects notices by identifier
    strength, so every notice it visits has a searchable identifier by
    construction. Computing the unsearchable rate over that subset returned 0 of
    60, a headline saying every recall is checkable, produced by the sampling
    rule rather than by the world. The figure over the full corpus is not that,
    and it is computed here rather than quoted, because it has already moved
    twice: once when the seed puller learned to open the CPSC Description key,
    and once when this file stopped carrying its own copy of the rule.

    The unsearchable rate does not depend on sweeping at all. That is the whole
    reason it survives every collector failing, and it has to be computed over
    everything the regulator published or it means nothing.

    `reports` are the per-arm normaliser reports. `graded` is golden/grade.py's
    output once enough listings have been hand-adjudicated.
    """
    reports = reports or []
    corpus = corpus or seeds
    rows = annotate(rows)
    curve = survival_curve(observations_from_rows(rows)) if rows else {"grid": []}

    stats = {
        # Over the whole corpus, always. Never over the swept subset.
        "unsearchable": unsearchable(corpus),
        # Published with the pooled rate every time, never after it.
        "unsearchable_by_authority": unsearchable_by_authority(corpus),
        "survival": still_buyable(rows, health_doc.get("arms")),
        "survival_curve": curve,
        "hero": hero(rows, corpus),
        "precision": precision(rows, graded),
        # Swept seeds, not the corpus: a notice nobody opened is not a non-escape.
        "border_escape": border_escape(rows, seeds, health_doc.get("arms")),
        "discarded": discarded(rows, reports),
        "arithmetic": arithmetic(seeds, reports),
        "findings": {
            "red": sum(1 for r in rows if r["tier"] == "RED"),
            "amber": sum(1 for r in rows if r["tier"] == "AMBER"),
            "total": len(rows),
            "shown": min(ROWS_SHOWN, len(rows)),
            "footer": "%d of %d shown, full set in data/sweeps/"
                      % (min(ROWS_SHOWN, len(rows)), len(rows)),
        },
        # The wall reads stats.credits. Omitting it threw
        # "Cannot read properties of undefined (reading 'used')" and halted boot()
        # after the rows had rendered, so the page looked complete and no animation
        # or count-up ever ran. Derived from the same plan the arithmetic is, so
        # the two cannot disagree.
        "credits": {
            "used": sum(r.get("planned_loads", 0) for r in reports),
            "cap": 5000,
            "code": sum(r.get("planned_loads", 0) for r in reports),
            "browser": 0,
        },
        "arms_measured": {
            "n": sum(1 for a in health_doc["arms"].values()
                     if a["state"] == "MEASURED"),
            "d": len(health_doc["arms"]),
        },
    }
    probes = adversarial()
    if probes:
        stats["adversarial_precision_set"] = probes
    ctrl = controls()
    if ctrl:
        stats["positive_control_set"] = ctrl

    return {
        "sweep_id": health_doc["sweep_id"],
        "swept_at": health_doc["swept_at"],
        "variant": variant,
        "freshness_bound_s": FRESHNESS_BOUND_S,
        "arms": _arms_for_wall(health_doc),
        "rows": rows,
        "stats": stats,
        "provenance": {
            "seed_source": ("CPSC official REST API and EU Safety Gate. "
                            "Zero Bright Data credits: the seed layer never "
                            "touches the platform, deliberately."),
            "seed_note": ("Every hazard sentence is the regulator's verbatim "
                          "text. Never paraphrased."),
            "fixture": False,
            "stamp": ("LIVE MEASUREMENT. %s"
                      % (health_doc.get("_STATUS") or health_doc["verdict"])),
            "collectors": {arm: a.get("collector_id")
                           for arm, a in health_doc["arms"].items()},
        },
    }


def _arms_for_wall(health_doc):
    """The arm blocks the wall renders, carried straight from the health file.

    Deriving them again here would create a second source of truth, and the
    second one always goes stale.
    """
    out = []
    for arm in ("US", "DE", "IN"):
        block = health_doc["arms"].get(arm)
        if not block:
            continue
        out.append({
            "code": arm,
            "host": ARM_HOST.get(arm),
            "state": block["state"],
            "reason": block.get("reason"),
            "collector_id": block.get("collector_id"),
            # data_lines is what the arm RETURNED, not what reddened. Passing the
            # RED count made an arm that brought back 1,066 listings report "0 of
            # 60 inputs returned rows", which is the same inversion the
            # zero_is_a_fault detector suffered.
            # Three different counts, and they are three different units. inputs
            # are notices we asked about; data_lines are listings that came back;
            # joined is how many notices got any candidate at all. Conflating the
            # first two produced "1066 of 60 inputs returned rows" on screen and a
            # coverage bar 11,477% wide.
            # Emitted under BOTH names on purpose. wall.js reads `listings`;
            # the archived payloads carry `data_lines`. Emitting one and reading
            # the other is how 16,025 adjudicated listings disappeared from the
            # page while the README stated them, so the emitter now satisfies
            # both readers rather than the reader guessing.
            "job": {"inputs": block.get("inputs", 0),
                    "listings": block.get("listings", block.get("rows", 0)),
                    "data_lines": block.get("listings", block.get("rows", 0)),
                    "joined": block.get("joined", 0),
                    "red": block.get("rows", 0),
                    "fails": block.get("fails", 0)},
            "heal": {"status": "none", "step": None, "completed_steps": [],
                     "started_at": None, "canary_pass": None, "canary_total": 3,
                     "ledger": None},
        })
    return out


def main(argv):
    """Turn the newest sweep in data/sweeps/ into data/fixtures.js.

    Writing the same file the wall already loads is what makes swap day `cp`
    rather than an integration: no server, no build step, no code change.
    """
    sweeps = ROOT / "data" / "sweeps"
    jsonl = sorted(sweeps.glob("s_*.jsonl"))
    if not jsonl:
        print("no sweep found in data/sweeps/. Run collector/sweep.py first.")
        return 1
    latest = argv[0] if argv else str(jsonl[-1])
    path = pathlib.Path(latest)
    health_path = path.with_name(path.stem + "-health.json")

    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]
    health_doc = json.loads(health_path.read_text(encoding="utf-8"))
    corpus = json.loads((ROOT / "data" / "seeds.json").read_text(encoding="utf-8"))["seeds"]
    seeds = corpus
    # A trial slice is scored against the notices it actually swept, or the
    # denominators describe a sweep that did not happen. The full corpus is kept
    # separately because the unsearchable rate belongs to it, not to the slice.
    if health_doc.get("trial_slice"):
        refs = {r["source"]["ref"] for r in rows}
        seeds = [s for s in corpus if s["ref"] in refs]

    payload = build(rows, health_doc, seeds, corpus=corpus,
                    reports=health_doc.get("reports") or [],
                    variant="trial" if health_doc.get("trial_slice") else "live")

    out = ROOT / "data" / ("live-%s.json" % path.stem)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("wrote %s" % out.relative_to(ROOT))

    # And the file the wall actually loads. This is the "swap day is cp" step,
    # done as a write rather than a copy: the wall reads data/live.js if it
    # exists and falls back to the fixture if it does not, so a clean clone with
    # no sweep still opens and still says which it is showing.
    live = ROOT / "data" / "live.js"
    live.write_text("window.CANON_LIVE = " +
                    json.dumps(payload, ensure_ascii=False) + ";\n",
                    encoding="utf-8")
    print("wrote %s  <- the wall loads this" % live.relative_to(ROOT))

    s = payload["stats"]
    print()
    print("unsearchable   %s of %s  %s" % (s["unsearchable"]["n"],
                                           s["unsearchable"]["d"],
                                           s["unsearchable"]["ci95"]))
    # The pooled rate is never printed on its own. The two regulators fail in
    # different ways and the average describes neither of them.
    for authority, stat in sorted(s["unsearchable_by_authority"].items()):
        print("  %-12s %s of %s  %s" % (authority, stat["n"], stat["d"],
                                        stat["ci95"]))
    print("still buyable  %s of %s  %s" % (s["survival"]["n"], s["survival"]["d"],
                                           s["survival"].get("ci95")))
    print("hero           %d burning-or-choking-children rows" % s["hero"]["n"])
    print("precision      %s" % (s["precision"].get("pending") or s["precision"]["v"]))
    print("arms measured  %d of %d" % (s["arms_measured"]["n"], s["arms_measured"]["d"]))
    print("credits        %s" % s["arithmetic"]["working"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
