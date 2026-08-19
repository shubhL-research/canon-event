#!/usr/bin/env python3
"""Build the hand-verification worksheet.

WHAT THIS IS FOR
----------------
Precision is the only number on the wall that a machine cannot produce. It is
the share of published RED rows that are actually correct, and the only way to
know is for a human to look. Everything else on the wall is qualified by it.

TWO PASSES, SAME METHOD
-----------------------
Pass 1, 15 items   the reality check. Answers "are recalled products findable
                   at all, and do the three marketplaces differ". Do this first.
                   If it comes back empty the headline changes, and the fallback
                   is already written.

Pass 2, 50 items   the golden set. Produces the precision figure and its Wilson
                   interval. Includes the 15 from pass 1.

BLIND, AND THAT IS NOT OPTIONAL
-------------------------------
Fill this in WITHOUT looking at what the collector decided. If you check a row
after seeing the machine's answer, you are not measuring the machine, you are
agreeing with it. Anchoring is not a small effect here: the whole value of the
golden set is that it was produced independently.

`grade.py` does the comparison afterwards.

Run:  python3 golden/make_worksheet.py
"""

import csv
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent


def pick_sample(seeds, n=50):
    """Stratify by identifier strength and by age.

    Not a random sample, and the README says so. A random draw from this corpus
    would be dominated by EU alerts with GTINs, which are the easy case, and the
    resulting precision figure would flatter the matcher. The strata are chosen
    so the hard cases are represented: US notices with a prose-mined model, and
    notices with no identifier at all, which must never reach RED.
    """
    eu_gtin = [s for s in seeds if s["authority"] == "SAFETY_GATE" and s.get("gtin")]
    us_model = [s for s in seeds if s["authority"] == "CPSC" and s.get("model")]
    us_none = [s for s in seeds if s["authority"] == "CPSC" and not s.get("model")]
    eu_model = [s for s in seeds if s["authority"] == "SAFETY_GATE"
                and s.get("model") and not s.get("gtin")]

    def spread(pool, k):
        """Take k items spread across the age range rather than clustered."""
        if not pool or k <= 0:
            return []
        pool = sorted(pool, key=lambda s: s["days"])
        if len(pool) <= k:
            return pool
        step = len(pool) / k
        return [pool[int(i * step)] for i in range(k)]

    quota = [(eu_gtin, 20), (us_model, 7), (eu_model, 8), (us_none, 15)]
    out = []
    for pool, k in quota:
        out.extend(spread(pool, k))

    # Top up from whatever is left if a stratum was short.
    if len(out) < n:
        taken = {s["ref"] for s in out}
        rest = [s for s in seeds if s["ref"] not in taken]
        out.extend(spread(rest, n - len(out)))
    return out[:n]


def main():
    seeds = json.loads((ROOT / "data" / "seeds.json").read_text(encoding="utf-8"))["seeds"]
    sample = pick_sample(seeds, 50)

    rows = []
    for i, s in enumerate(sample, start=1):
        ident = s.get("gtin") or s.get("model") or ""
        kind = ("gtin" if s.get("gtin") else "model" if s.get("model") else "none")
        rows.append({
            "n": i,
            "phase": "reality-check" if i <= 15 else "golden-set",
            "ref": s["ref"],
            "authority": s["authority"],
            "days": s["days"],
            "id_kind": kind,
            "identifier": ident,
            "brand": s.get("brand") or "",
            "product": s["name"][:70],
            "search_this": (ident or f'{s.get("brand") or ""} {s["name"][:40]}').strip(),
            "IN": "", "COM": "", "DE": "",
            "query_that_worked": "",
            "notes": "",
        })

    out = HERE / "worksheet.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by_kind = {}
    for r in rows:
        by_kind[r["id_kind"]] = by_kind.get(r["id_kind"], 0) + 1
    print(f"  wrote golden/worksheet.csv  ({len(rows)} rows)")
    print(f"  first 15 are the reality check, all 50 are the golden set")
    print(f"  identifier mix: {by_kind}")
    print(f"  age span: {min(r['days'] for r in rows)} to {max(r['days'] for r in rows)} days")
    print()
    print("  Fill IN / COM / DE with:  RED  AMBER  NOT_FOUND")
    print("  Then: python3 golden/grade.py")


if __name__ == "__main__":
    main()
