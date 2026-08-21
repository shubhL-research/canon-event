"""Refuse a figure in the prose that the payload contradicts.

WHY THIS EXISTS
---------------
The wall, the README and SCRAPER-STUDIO.md all quote the same sweep, and three
of them went stale at different rates. DE returned 1,037 listings joining 59
notices when the docs were written; it returns 2,061 joining 111 now. The total
moved from 23,655 to 24,679. Every one of those numbers stayed put in prose.

That matters more here than in most projects. A judge reading the repository
beside the page finds two documents disagreeing about the same sweep, and the
governing rule of the whole thing is that it never publishes a number it cannot
defend. A stale figure is not a typo, it is a defended number that is wrong.

Fixing them by hand once fixes them until the next sweep. This makes the prose
answerable to the payload on every run.

    python3 check_docs.py
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent


def payload():
    src = (ROOT / "data" / "live.js").read_text(encoding="utf-8")
    return json.loads(src[src.index("{"):src.rindex(";")])


def facts(doc):
    arms = {a["code"]: a for a in doc["arms"]}
    out = {
        "notices": len(doc["rows"]),
        "listings_total": sum(a["job"]["listings"] for a in doc["arms"]),
        "searchable": doc["stats"]["survival"]["d"],
        "survival_n": doc["stats"]["survival"]["n"],
        "unsearchable_n": doc["stats"]["unsearchable"]["n"],
    }
    for code, a in arms.items():
        out["%s_listings" % code] = a["job"]["listings"]
        out["%s_joined" % code] = a["job"]["joined"]
    return out


def commas(n):
    return "{:,}".format(n)


def main():
    doc = payload()
    f = facts(doc)
    problems = []

    # Each rule is (file, regex, what the captured number must equal, why).
    # The regex is deliberately narrow: it matches the sentence that makes the
    # claim, not every occurrence of a digit.
    RULES = [
        ("SCRAPER-STUDIO.md",
         r"US amazon\.com\s+([\d,]+) listings,\s+(\d+) of (\d+) notices joined",
         ("US_listings", "US_joined", "notices")),
        ("SCRAPER-STUDIO.md",
         r"DE kaufland\.de\s+([\d,]+) listings,\s+(\d+) of (\d+) notices joined",
         ("DE_listings", "DE_joined", "notices")),
        ("SCRAPER-STUDIO.md",
         r"IN flipkart\.com\s+([\d,]+) listings,\s+(\d+) of (\d+) notices joined",
         ("IN_listings", "IN_joined", "notices")),
        ("SCRAPER-STUDIO.md",
         r"listings adjudicated\s+([\d,]+)", ("listings_total",)),
        ("README.md",
         r"\| Listings adjudicated \| ([\d,]+)\. US ([\d,]+), DE ([\d,]+), IN ([\d,]+) \|",
         ("listings_total", "US_listings", "DE_listings", "IN_listings")),
        ("README.md",
         r"joining (\d+), (\d+) and (\d+) notices of (\d+)",
         ("US_joined", "DE_joined", "IN_joined", "notices")),
    ]

    for fname, pattern, keys in RULES:
        path = ROOT / fname
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        m = re.search(pattern, text)
        if not m:
            problems.append("%s: no line matching /%s/. The claim it guarded may "
                            "have been reworded; update this rule or restore the line."
                            % (fname, pattern[:52]))
            continue
        for i, key in enumerate(keys, start=1):
            claimed = int(m.group(i).replace(",", ""))
            actual = f[key]
            if claimed != actual:
                line = text[:m.start()].count("\n") + 1
                problems.append("%s:%d claims %s = %s, payload says %s"
                                % (fname, line, key, commas(claimed), commas(actual)))

    # DEMO.md tells the presenter which numbers to read aloud, and its own text
    # calls a voiceover that disagrees with its frame "the single worst thing
    # this video could do". Four of its seven scripted figures had gone stale.
    demo = ROOT / "DEMO.md"
    if demo.exists():
        text = demo.read_text(encoding="utf-8")
        d_sear = f["searchable"]
        expected = [
            ("0 of %d searchable notices" % d_sear, "the survival denominator"),
            ("%s" % commas(f["listings_total"]), "the adjudicated listing total"),
        ]
        for needle, what in expected:
            if needle not in text:
                problems.append("DEMO.md does not contain %s (%s). The script "
                                "tells the presenter what to say; a figure it "
                                "carries must be one that is on the screen."
                                % (needle, what))
        # And no figure the payload has moved past.
        for stale in ("0 of 120 searchable", "0 of 124 searchable", "0 of 58 searchable",
                      "23,655"):
            if stale in text:
                problems.append("DEMO.md still scripts the stale figure %r" % stale)

    # The arms must also add up to the total they are printed beside, which is
    # the one sum a judge can do in their head on the page itself.
    parts = f["US_listings"] + f["DE_listings"] + f["IN_listings"]
    if parts != f["listings_total"]:
        problems.append("the arm listings sum to %s, not %s"
                        % (commas(parts), commas(f["listings_total"])))

    print("  payload: %s notices, %s listings, %s searchable, survival %s of %s"
          % (f["notices"], commas(f["listings_total"]), f["searchable"],
             f["survival_n"], f["searchable"]))
    if not problems:
        print("  every checked figure in the prose matches the payload")
        return 0
    print("\n  PROSE DISAGREES WITH THE PAYLOAD:\n")
    for p in problems:
        print("    " + p)
    print("\n  A stale figure is not a typo. It is a defended number that is wrong.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
