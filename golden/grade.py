#!/usr/bin/env python3
"""Score the hand-verified worksheet, and compare it to the collector.

Two jobs:

1. REALITY CHECK (first 15 rows). Are recalled products findable at all, and do
   the three marketplaces differ? This decides whether the headline stands or
   the project pivots to the unsearchable rate. Reports the answer against the
   pre-registered gate rather than leaving it to a judgement call on the day.

2. PRECISION (all 50 rows). Of the rows the collector published as RED, what
   share did a human confirm? With a Wilson interval, because a bare 0.94 over
   50 items is not a number anyone should act on without one.

Run:  python3 golden/grade.py
      python3 golden/grade.py --against data/sweeps/latest.jsonl
"""

import csv
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "stats"))
from wilson import wilson  # noqa: E402

VALID = {"RED", "AMBER", "NOT_FOUND"}
ARMS = ["IN", "COM", "DE"]


def load():
    f = HERE / "worksheet.csv"
    if not f.exists():
        sys.exit("golden/worksheet.csv not found. Run golden/make_worksheet.py first.")
    return list(csv.DictReader(f.open(encoding="utf-8")))


def clean(v):
    return (v or "").strip().upper().replace(" ", "_")


def reality_check(rows):
    """The D2 gate, scored against its pre-registered threshold.

    Pre-registered so the decision is not made by whoever is most tired at the
    time. The gate wants at least 8 RED across at least 2 arms, with at least 2
    on amazon.in, scaled to however many rows are actually filled in.
    """
    filled = [r for r in rows[:15] if any(clean(r[a]) in VALID for a in ARMS)]
    if not filled:
        return None

    red = {a: sum(1 for r in filled if clean(r[a]) == "RED") for a in ARMS}
    amber = {a: sum(1 for r in filled if clean(r[a]) == "AMBER") for a in ARMS}
    nf = {a: sum(1 for r in filled if clean(r[a]) == "NOT_FOUND") for a in ARMS}

    total_red = sum(red.values())
    arms_with_red = sum(1 for a in ARMS if red[a] > 0)
    scale = len(filled) / 15.0
    need_total, need_in = max(1, round(8 * scale * 15 / 60)), max(1, round(2 * scale * 15 / 60))

    if total_red >= need_total and arms_with_red >= 2 and red["IN"] >= need_in:
        verdict, action = "PASS", "Proceed unchanged. The headline stands."
    elif total_red >= need_total and arms_with_red >= 2:
        verdict, action = ("PASS, IN WEAK",
                           "Border escape demotes to a body statistic with its real small n "
                           "printed. Widen the IN query strategy to identifier + brand + "
                           "product noun and re-measure. Survival becomes the hero.")
    elif total_red > 0:
        verdict, action = ("MARGINAL",
                           "The headline survives but the gate is tight. Widen the query "
                           "strategy now rather than on Friday, and print the small n honestly.")
    else:
        verdict, action = ("FAIL",
                           "Pivot to UNSEARCHABLE RATE plus the identifier-present vs "
                           "identifier-absent survival cross. The fallback hero sentence is "
                           "already written in CONTRACT-v0.9.md section 4, so this costs zero "
                           "copy time.")

    return {"filled": len(filled), "red": red, "amber": amber, "not_found": nf,
            "total_red": total_red, "arms_with_red": arms_with_red,
            "verdict": verdict, "action": action}


def identifier_effect(rows):
    """Does carrying a searchable identifier change what you find?

    This is the cross the plan already wanted and never had a way to compute.
    It is also the fallback headline if the reality check fails, so it is worth
    reading off the same worksheet rather than a second exercise.
    """
    out = {}
    for kind in ("gtin", "model", "none"):
        sub = [r for r in rows if r["id_kind"] == kind
               and any(clean(r[a]) in VALID for a in ARMS)]
        if not sub:
            continue
        found = sum(1 for r in sub if any(clean(r[a]) == "RED" for a in ARMS))
        lo, hi = wilson(found, len(sub))
        out[kind] = {"n": len(sub), "found": found,
                     "rate": round(found / len(sub), 4),
                     "ci95": [round(lo, 4), round(hi, 4)]}
    return out


def precision(rows, machine):
    """Human verdict versus collector verdict, per arm.

    Precision counts only rows the COLLECTOR called RED. A row the human found
    and the machine missed is a recall failure, not a precision failure, and the
    two must not be mixed: recall is bounded separately by capture-recapture.
    """
    if not machine:
        return None
    tp = fp = fn = 0
    disagreements = []
    for r in rows:
        for arm in ARMS:
            h = clean(r[arm])
            if h not in VALID:
                continue
            key = (r["ref"], {"COM": "US"}.get(arm, arm))
            m = machine.get(key)
            if m is None:
                continue
            if m == "RED" and h == "RED":
                tp += 1
            elif m == "RED" and h != "RED":
                fp += 1
                disagreements.append((r["ref"], arm, "machine RED, human " + h, r["product"]))
            elif m != "RED" and h == "RED":
                fn += 1
                disagreements.append((r["ref"], arm, "human RED, machine " + m, r["product"]))
    if tp + fp == 0:
        return {"published": 0, "note": "the collector published no RED rows in this sample"}
    lo, hi = wilson(tp, tp + fp)
    return {"published": tp + fp, "confirmed": tp, "false": fp, "missed_by_machine": fn,
            "precision": round(tp / (tp + fp), 4), "ci95": [round(lo, 4), round(hi, 4)],
            "disagreements": disagreements}


def load_machine(path):
    """Collector verdicts as {(ref, arm): tier}."""
    p = pathlib.Path(path)
    if not p.exists():
        return None
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        ref = row.get("source", {}).get("ref")
        for arm, verdict in (row.get("arms") or {}).items():
            out[(ref, arm)] = "RED" if verdict == "RED" else row.get("tier", "AMBER")
    return out


def main():
    rows = load()
    against = None
    if "--against" in sys.argv:
        against = sys.argv[sys.argv.index("--against") + 1]

    bad = [(r["n"], a, r[a]) for r in rows for a in ARMS
           if r[a].strip() and clean(r[a]) not in VALID]
    if bad:
        print("  entries that are not RED / AMBER / NOT_FOUND:")
        for n, a, v in bad[:10]:
            print(f"    row {n} {a}: {v!r}")
        print()

    rc = reality_check(rows)
    if not rc:
        print("  Nothing filled in yet. Open golden/worksheet.csv and start with the")
        print("  first 15 rows. Sixty seconds per cell, and the timeout IS the answer.")
        return 0

    print(f"\n  REALITY CHECK   {rc['filled']} of 15 rows filled")
    for a in ARMS:
        print(f"    amazon.{a.lower():<4}  RED {rc['red'][a]:>2}   "
              f"AMBER {rc['amber'][a]:>2}   NOT_FOUND {rc['not_found'][a]:>2}")
    print(f"\n    VERDICT: {rc['verdict']}")
    print(f"    {rc['action']}")

    eff = identifier_effect(rows)
    if eff:
        print("\n  DOES A SEARCHABLE IDENTIFIER CHANGE WHAT YOU FIND?")
        for kind, d in eff.items():
            print(f"    {kind:<6} {d['found']:>2}/{d['n']:<3} found  {d['rate']:.0%}  "
                  f"CI [{d['ci95'][0]:.0%}, {d['ci95'][1]:.0%}]")
        if "none" in eff and "gtin" in eff:
            print("    If these intervals do not overlap, that gap is a finding in its own")
            print("    right and it is the fallback headline.")

    filled_all = sum(1 for r in rows if any(clean(r[a]) in VALID for a in ARMS))
    print(f"\n  GOLDEN SET      {filled_all} of 50 rows filled")
    if filled_all < 50:
        print(f"    {50 - filled_all} to go before precision can be published.")

    if against:
        prec = precision(rows, load_machine(against))
        if prec and prec.get("published"):
            print(f"\n  PRECISION vs {against}")
            print(f"    collector published {prec['published']} RED, human confirmed {prec['confirmed']}")
            print(f"    precision {prec['precision']:.3f}  "
                  f"CI [{prec['ci95'][0]:.3f}, {prec['ci95'][1]:.3f}]")
            print(f"    machine missed {prec['missed_by_machine']} the human found "
                  f"(recall, not precision: bounded separately by capture-recapture)")
            for ref, arm, what, prod in prec["disagreements"][:8]:
                print(f"      {ref} {arm}: {what}  {prod[:40]}")
        elif prec:
            print(f"\n  {prec['note']}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
