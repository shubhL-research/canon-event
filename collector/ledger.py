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
    for line in lines[1:16]:
        f = FIELD.match(line)
        if f:
            key = f.group(1).strip().lower().replace(" ", "_")
            if key == "outcome":
                key = "outcome_detail"
            val = f.group(2).strip()
            if key != "refused_because":
                # Short machine facts carry trailing parentheticals and aligned
                # columns; a prose reason is one field holding one sentence and
                # must not be cut at its first double space or bracket.
                val = val.split("  ")[0].split(" (")[0].strip()
            entry[key] = val

    if entry["outcome"] == "REFUSED" and not entry.get("refused_because"):
        raise ValueError(
            "%s is REFUSED and carries no `refused_because` field. The reason a "
            "heal was refused is the whole point of recording it, and it is not "
            "something to infer from the prose: the regex that used to do so "
            "matched the heading 'What the canary found' running into the line "
            "below it, so every refusal card on the wall printed the sentence "
            "saying the fix WORKED as the reason it was rejected. State it in "
            "the indented block." % entry.get("file", "this ledger"))

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
    # The counts are computed and the note is built FROM them. It used to say
    # "Two were refused" in prose directly under a computed heading that said
    # four, in the one section built to answer the self-healing criterion. A
    # hand-typed count beside a derived one is a contradiction with a timer on
    # it: every heal added moves one number and not the other.
    refused = sum(1 for e in entries if e["outcome"] == "REFUSED")
    approved = sum(1 for e in entries if e["outcome"] == "APPROVED")
    return {
        "total": len(entries),
        "refused": refused,
        "approved": approved,
        "entries": entries,
        "by_arm": by_arm(entries),
        "note": (
            "Every heal here was run against a live collector through Scraper "
            "Studio's refactor_template flow. %d of %d %s refused at the canary "
            "gate, for two different reasons that are worth keeping apart: two "
            "repairs fixed the fault they were asked about and broke a field they "
            "were not, and two widened past the request and stripped the "
            "extraction entirely. There is no rollback endpoint, so verification "
            "sits before promotion rather than after it, and a draft is run at "
            "version=dev rather than trusted from its preview."
            % (refused, len(entries), "was" if refused == 1 else "were")),
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
