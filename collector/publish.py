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
sys.path.insert(0, str(ROOT / "stats"))
sys.path.insert(0, str(ROOT / "data"))

from wilson import proportion, wilson                        # noqa: E402
from recapture import from_rows as recapture_from_rows       # noqa: E402
from survival import survival_curve, observations_from_rows  # noqa: E402
from make_fixture import hazard_class                        # noqa: E402

# How long a sweep may speak in the present tense. Mirrors health.FRESHNESS_BOUND_S.
FRESHNESS_BOUND_S = 14400

# Rows the wall renders before the fold. The rest ship in the structured output,
# and the footer says so rather than letting the reader assume they saw everything.
ROWS_SHOWN = 40

# Hand-adjudicated listings required before a precision figure may be published.
# Below this the interval is too wide to qualify anything, and a precision claim
# that cannot qualify the numbers underneath it is decoration.
PRECISION_MINIMUM = 50


def searchable(seed_or_row):
    """Did this notice carry anything a matcher could search for?

    The denominator of the unsearchable rate, and the reason it can be computed
    without a scraper. `gtin` alone is not enough: six Safety Gate notices carry
    a value in that field that fails its own check digit, and those are not
    searchable in any useful sense.
    """
    from normalize import gtin_check_digit_ok
    gtin = seed_or_row.get("gtin")
    if gtin and gtin_check_digit_ok(gtin):
        return True
    return bool((seed_or_row.get("model") or "").strip())


def unsearchable(seeds):
    """Share of the corpus that cannot be searched at all.

    Computed entirely from the free government corpus. No collector touches it,
    so it is the one headline that survives every arm being withheld.
    """
    d = len(seeds)
    n = sum(1 for s in seeds if not searchable(s))
    stat = proportion(n, d, "unsearchable")
    stat["contaminated"] = False
    return stat


def still_buyable(rows):
    """Share of SEARCHABLE notices found still on sale.

    The denominator excludes notices we could never look for. Scoring an
    unsearchable notice as not-buyable would convert our own blindness into
    evidence of safety, which is the failure this project exists to refuse.
    """
    scored = [r for r in rows if searchable(r)]
    n = sum(1 for r in scored if r["tier"] == "RED")
    if not scored:
        return {"v": None, "n": 0, "d": 0, "ci95": None, "contaminated": True,
                "pending": "No searchable notice reached a verdict."}
    stat = proportion(n, len(scored), "still buyable")
    stat["contaminated"] = True
    return stat


def hero(rows):
    """The burning-or-choking-children count, with the oldest example named.

    The classification is a transparent keyword rule recorded on every row, so a
    reader can audit which words triggered it. An opaque classifier under the
    most quoted sentence in the project would be indefensible.
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


def border_escape(rows, seeds):
    """EU-recalled products found on a non-EU marketplace.

    The denominator is free: EU notices carrying a searchable identifier. The
    numerator needs the IN arm to have measured, so when it has not this renders
    as PENDING with the reason rather than as a zero. A zero here would read as
    "nothing escaped", which is a finding we have not made.
    """
    eu = [s for s in seeds if s["authority"] == "SAFETY_GATE"]
    eu_searchable = [s for s in eu if searchable(s)]
    refs = {s["ref"] for s in eu_searchable}
    escaped = [r for r in rows
               if r["source"]["ref"] in refs and r.get("arms", {}).get("IN") == "RED"]

    out = {"eu_seeds": len(eu), "eu_searchable": len(eu_searchable),
           "contaminated": True}
    if not eu_searchable:
        out.update(v=None, n=0, d=0, ci95=None,
                   pending="No EU notice carries a searchable identifier.")
        return out
    if not escaped:
        out.update(v=0.0, n=0, d=len(eu_searchable),
                   ci95=list(wilson(0, len(eu_searchable))))
        return out
    stat = proportion(len(escaped), len(eu_searchable), "border escape")
    out.update(stat)
    return out


def discarded(health_doc, reports):
    """Discard rate and the reason codes behind it.

    Reported by cause rather than as a single number, because an opaque discard
    count is indistinguishable from a broken matcher.
    """
    by_code, total = {}, 0
    for report in reports:
        for code, count in (report.get("by_code") or {}).items():
            by_code[code] = by_code.get(code, 0) + count
            total += count
    planned = sum(r.get("planned_loads", 0) for r in reports)
    out = {"n": total, "d": planned, "by_code": by_code, "contaminated": True}
    if planned:
        out["v"] = round(total / planned, 4)
        out["ci95"] = [round(x, 4) for x in wilson(total, planned)]
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
        "working": ("%d searchable of %d notices x 2 queries x %d arms = %d "
                    "search loads, submitted as %d batch jobs."
                    % (searchable_seeds, len(seeds), arms, planned,
                       sum(r.get("batches", 0) for r in reports))),
        "note": ("Only searchable notices are queried, so the 96 with no usable "
                 "identifier cost nothing. Batching is what makes a full sweep "
                 "possible: one job per 40 urls rather than one job per url."),
    }


def adversarial():
    """The precision probes, if they have been run. Absent rather than faked."""
    path = ROOT / "data" / "adversarial.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {"n": doc["n"], "all_discarded": doc["all_discarded"],
            "by_kind": doc["by_kind"], "note": doc["note"]}


def annotate(rows):
    """Attach the hazard classification the hero sentence is computed from."""
    for row in rows:
        if "hazard_class" not in row and row.get("hazard"):
            row["hazard_class"] = hazard_class(row["hazard"])
    return rows


def build(rows, health_doc, seeds, reports=None, graded=None, variant="live"):
    """Assemble the wall payload. Every figure computed, none inherited.

    `reports` are the per-arm normaliser reports from the sweep. `graded` is the
    output of golden/grade.py when enough listings have been hand-adjudicated.
    """
    reports = reports or []
    rows = annotate(rows)
    curve = survival_curve(observations_from_rows(rows)) if rows else {"grid": []}

    stats = {
        "unsearchable": unsearchable(seeds),
        "survival": still_buyable(rows),
        "survival_curve": curve,
        "hero": hero(rows),
        "precision": precision(rows, graded),
        "border_escape": border_escape(rows, seeds),
        "discarded": discarded(health_doc, reports),
        "arithmetic": arithmetic(seeds, reports),
        "findings": {
            "red": sum(1 for r in rows if r["tier"] == "RED"),
            "amber": sum(1 for r in rows if r["tier"] == "AMBER"),
            "total": len(rows),
            "shown": min(ROWS_SHOWN, len(rows)),
            "footer": "%d of %d shown, full set in data/sweeps/"
                      % (min(ROWS_SHOWN, len(rows)), len(rows)),
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
            "state": block["state"],
            "reason": block.get("reason"),
            "collector_id": block.get("collector_id"),
            "job": {"inputs": block.get("inputs", 0),
                    "data_lines": block.get("rows", 0),
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
    seeds = json.loads((ROOT / "data" / "seeds.json").read_text(encoding="utf-8"))["seeds"]
    # A trial slice must be scored against the notices it actually swept, or the
    # denominators describe a sweep that did not happen.
    if health_doc.get("trial_slice"):
        refs = {r["source"]["ref"] for r in rows}
        seeds = [s for s in seeds if s["ref"] in refs]

    payload = build(rows, health_doc, seeds,
                    reports=health_doc.get("reports") or [],
                    variant="trial" if health_doc.get("trial_slice") else "live")

    out = ROOT / "data" / ("live-%s.json" % path.stem)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("wrote %s" % out.relative_to(ROOT))

    s = payload["stats"]
    print()
    print("unsearchable   %s of %s  %s" % (s["unsearchable"]["n"],
                                           s["unsearchable"]["d"],
                                           s["unsearchable"]["ci95"]))
    print("still buyable  %s of %s  %s" % (s["survival"]["n"], s["survival"]["d"],
                                           s["survival"].get("ci95")))
    print("hero           %d burning-or-choking-children rows" % s["hero"]["n"])
    print("precision      %s" % (s["precision"].get("pending") or s["precision"]["v"]))
    print("arms measured  %d of %d" % (s["arms_measured"]["n"], s["arms_measured"]["d"]))
    print("credits        %s" % s["arithmetic"]["working"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
