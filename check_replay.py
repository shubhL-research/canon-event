"""Bind the published wall to the raw archive it claims to come from.

WHY THIS EXISTS
---------------
verify.sh republishes data/live.js from data/live-<sweep>.json, which is itself a
derived payload. Nothing checked that either one still agreed with the 17MB of
unmodified Bright Data rows in data/sweeps/raw/. If the archive and the wall ever
disagreed, every suite would still have passed, and the strongest claim this
project makes is that its headline can be re-derived from committed platform
output without issuing a single request.

A claim nobody runs is a claim nobody can rely on. This runs it.

It re-adjudicates the raw archive with the CURRENT matcher, in memory, writing
nothing, and compares the result against what the wall publishes. It is the same
path as `collector/sweep.py --from-raw`, which is the command in the README.

    python3 check_replay.py
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "collector"))


def published():
    src = (ROOT / "data" / "live.js").read_text(encoding="utf-8")
    return json.loads(src[src.index("{"):src.rindex(";")])


def main():
    raw_dir = ROOT / "data" / "sweeps" / "raw"
    if not raw_dir.exists() or not any(raw_dir.glob("*.jsonl")):
        print("  no raw archive committed, skipping")
        return 0

    from sweep import adjudicate_from_raw
    seeds = json.loads((ROOT / "data" / "seeds.json").read_text(encoding="utf-8"))["seeds"]

    arms = sorted(p.stem for p in raw_dir.glob("*.jsonl"))
    rows, _doc = adjudicate_from_raw(seeds, arms=arms)

    wall = published()
    problems = []

    def cmp(label, got, want):
        if got != want:
            problems.append("%s: replaying the raw archive gives %s, the wall "
                            "publishes %s" % (label, got, want))

    cmp("rows", len(rows), len(wall["rows"]))
    cmp("RED rows",
        sum(1 for r in rows if r.get("tier") == "RED"),
        sum(1 for r in wall["rows"] if r.get("tier") == "RED"))

    # The headline itself. This is the number the whole page is judged on, and
    # it is the one a drifted archive would move first.
    from publish import searchable
    replay_sear = sum(1 for r in rows if searchable(r))
    cmp("searchable notices", replay_sear, wall["stats"]["survival"]["d"])

    print("  replayed %d notices from %d committed raw arms, no network"
          % (len(rows), len(arms)))
    print("  RED %d, searchable %d, matching the published wall"
          % (sum(1 for r in rows if r.get("tier") == "RED"), replay_sear))

    if problems:
        print("\n  THE WALL AND THE ARCHIVE DISAGREE:\n")
        for p in problems:
            print("    " + p)
        print("\n  One of them is wrong and the archive is the record.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
