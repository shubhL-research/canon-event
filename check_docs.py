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

    # THE HERO AND THE REGULATOR BLOCK MUST RECONCILE.
    #
    # The hero says every EU alert carries a barcode and N of them pass their own
    # check digit. The regulator block, three screens down, says M EU notices are
    # unsearchable. Those are the same notices seen from two directions. If they
    # ever stop agreeing, one of the two is wrong and a reader can see it without
    # leaving the page.
    hero = doc["stats"].get("hero") or {}
    eu = (doc["stats"].get("unsearchable_by_authority") or {}).get("SAFETY_GATE")
    if eu and hero.get("eu_barcode_total"):
        invalid = hero["eu_barcode_total"] - hero["eu_barcode_valid"]
        if invalid != eu["n"]:
            problems.append(
                "the hero implies %d EU barcodes are unusable (%d of %d fail their "
                "check digit) while the regulator block reports %d EU notices "
                "unsearchable. Same notices, two directions, two answers."
                % (invalid, invalid, hero["eu_barcode_total"], eu["n"]))
        if str(hero["eu_barcode_valid"]) not in hero.get("sentence", ""):
            problems.append("the hero sentence does not state the %d it validated"
                            % hero["eu_barcode_valid"])

    # THE PRIMARY-EVIDENCE POINTER MUST NAME THE PUBLISHED SWEEP.
    #
    # README's "The primary evidence" table offered sweep-2026-08-20.csv as "the
    # full three-arm sweep". It is a 60-notice trial whose summary still carries
    # the retracted 46.4% unsearchable rate. A judge following the project's own
    # pointer found it committing the error the README apologises for.
    #
    # It must name data/sweeps/published.jsonl, which publish.py rewrites on
    # every publish. A timestamped name goes stale the moment a sweep is
    # re-scored, which is how the pointer drifted onto a superseded file.
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stable = ROOT / "data" / "sweeps" / "published.jsonl"
    if "published.jsonl" not in readme:
        problems.append("README's primary-evidence table must name "
                        "data/sweeps/published.jsonl, the stable pointer to the "
                        "sweep on screen, not a timestamped file that goes stale")
    if not stable.exists():
        problems.append("data/sweeps/published.jsonl is missing: nothing points "
                        "a reader at the sweep the wall publishes")
    elif len([l for l in stable.read_text(encoding="utf-8").splitlines() if l.strip()]) != len(doc["rows"]):
        problems.append("data/sweeps/published.jsonl holds a different number of "
                        "rows than the payload publishes")

    # NO SURFACE MAY CALL A PLAN AN ISSUED COUNT.
    #
    # planned_loads on the replay path is len(plan_arm(...)) recomputed at replay
    # time, so the same committed archive was credited with 232, 348 and 1,107
    # "issued" loads on three different days as the corpus and the searchability
    # rule moved. The README says of this publish: "No new fetch and no new
    # credits." A replay issues nothing.
    #
    # publish.py was corrected and republish.py carried a second, unfixed copy of
    # the same sentence, which is the copy the wall renders, so the fix never
    # reached the page. This checks the rendered value, not the source.
    working = (doc["stats"].get("arithmetic") or {}).get("working", "")
    for banned in ("loads issued", "planned and issued", "actually issued"):
        if banned in working:
            problems.append("stats.arithmetic.working says %r for a payload whose "
                            "sweep id is %s. A replay issues nothing."
                            % (banned, doc.get("sweep_id")))
    if "-" in working.split("because")[0] and "extra -" in working:
        problems.append("stats.arithmetic.working prints a negative count as an "
                        "'extra': %r" % working[:90])

    # And the archive claim, which the archive itself can settle.
    raw_dir = ROOT / "data" / "sweeps" / "raw"
    if raw_dir.exists():
        import json as _j
        counts = {}
        # Named `arm_file`, not `f`: `f` is the facts dict in this scope and
        # shadowing it made every figure comparison below read a Path.
        for arm_file in sorted(raw_dir.glob("*.jsonl")):
            urls = set()
            for line in arm_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    u = (_j.loads(line).get("input") or {}).get("url")
                except Exception:
                    continue
                if u:
                    urls.add(u)
            counts[arm_file.stem] = len(urls)
        doc_text = (ROOT / "SCRAPER-STUDIO.md").read_text(encoding="utf-8")
        for arm, n in counts.items():
            if str(n) not in doc_text:
                problems.append("SCRAPER-STUDIO.md does not state the %d distinct "
                                "search URLs the committed archive holds for %s"
                                % (n, arm))

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
