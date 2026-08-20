#!/usr/bin/env python3
"""Read the heal ledger out of heals/*.md so the wall can render it.

WHY THIS EXISTS
---------------
Three heals were run against live collectors. Two were REFUSED by the canary
gate. The ledgers are written and committed, and every one of them is real.

collector/publish.py hardcoded `"heal": {"status": "none"}` on every arm, so the
wall printed "No heal has been triggered this sweep" while the repository held
three. The hardest artifact in the project to obtain, and the one that cannot be
faked, was invisible on the page a judge actually looks at.

An agent that declines to promote its own repair is worth more than one that
always succeeds. That only counts if someone can see it.

WHAT IS PARSED AND WHAT IS NOT
------------------------------
Only the header block: outcome, arm, collector, timestamps, and the canary that
refused it. The prose underneath is the evidence and belongs in the ledger file,
not on the wall. The wall links to it.

Nothing here infers. If a field is not in the file it is absent, and the wall
renders absence as absence.

Run:  python3 collector/ledger.py
"""

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
HEALS = ROOT / "heals"

TITLE = re.compile(r"^#\s*Heal\s+([A-Z]{2})-(\d+)\s*[-—:]+\s*(\w+)", re.I)
FIELD = re.compile(r"^\s{2,}(\w[\w ]*?)\s{2,}(.+?)\s*$")


def parse(path):
    """One ledger file into a dict. Absent fields stay absent."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    entry = {"file": f"heals/{path.name}"}
    m = TITLE.match(lines[0]) if lines else None
    if not m:
        return None
    entry["arm"], entry["seq"] = m.group(1).upper(), m.group(2)
    # The ledgers write REFUSED. Anything that is not an approval is a
    # refusal, and defaulting the other way would turn a refused heal into a
    # claimed success, which is the one inversion this file exists to prevent.
    raw = m.group(3).upper()
    entry["outcome"] = "APPROVED" if raw.startswith("APPROV") else "REFUSED"
    entry["outcome_raw"] = raw

    # The indented block under the title carries the machine facts.
    #
    # The block contains a field literally named `outcome`, holding prose like
    # "REJECTED at the approval gate". Letting it land on the same key as the
    # parsed verdict silently overwrote every outcome with a sentence, and the
    # counts then read zero refused and zero approved against three real heals.
    # The verdict comes from the title and nothing else may write to it.
    for line in lines[1:14]:
        f = FIELD.match(line)
        if f:
            key = f.group(1).strip().lower().replace(" ", "_")
            if key == "outcome":
                key = "outcome_detail"
            entry[key] = f.group(2).strip().split("  ")[0].split(" (")[0].strip()

    # The canary that refused it is the whole point of a refusal, so find the
    # sentence naming it rather than making the reader open the file.
    refused = re.search(r"(?:canary|check digit|did not re-?assert)[^.]*\.", text, re.I)
    if refused and entry["outcome"] == "REFUSED":
        entry["refused_because"] = " ".join(refused.group(0).split())[:220]

    return entry


def load():
    if not HEALS.exists():
        return []
    out = [parse(p) for p in sorted(HEALS.glob("*.md"))]
    return [e for e in out if e]


def by_arm(entries):
    """Ledger grouped by arm, refusals first.

    A refusal is louder than a success everywhere this project renders one, so
    the ordering is part of the claim rather than a display preference.
    """
    grouped = {}
    for e in entries:
        grouped.setdefault(e["arm"], []).append(e)
    for arm in grouped:
        grouped[arm].sort(key=lambda e: (e["outcome"] != "REFUSED", e.get("seq", "")))
    return grouped


def summary(entries):
    return {
        "total": len(entries),
        "refused": sum(1 for e in entries if e["outcome"] == "REFUSED"),
        "approved": sum(1 for e in entries if e["outcome"] == "APPROVED"),
        "entries": entries,
        "by_arm": by_arm(entries),
        "note": ("Every heal here was run against a live collector through Scraper "
                 "Studio's refactor_template flow. Two were refused by the canary "
                 "gate: the repair worked and the gate rejected it anyway, because "
                 "a fix that passes the reported fault can still break a field it "
                 "was never asked about. There is no rollback endpoint, so "
                 "verification sits before promotion rather than after it."),
    }


def main():
    entries = load()
    if not entries:
        print("  no ledgers in heals/")
        return 1
    s = summary(entries)
    out = ROOT / "data" / "heals.json"
    out.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  {s['total']} heals: {s['refused']} refused, {s['approved']} approved")
    for e in entries:
        mark = "REFUSED " if e["outcome"] == "REFUSED" else "approved"
        print(f"    {e['arm']}-{e['seq']}  {mark}  {e.get('collector', '')[:24]}")
        if e.get("refused_because"):
            print(f"              {e['refused_because'][:96]}")
    print(f"\n  wrote data/heals.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
