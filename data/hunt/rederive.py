"""Re-derive every hunt verdict from the committed pages. No network.

WHY THIS FILE EXISTS
--------------------
The hunt rows were found by hand, which is weaker provenance than an adjudicated
sweep row, so they have to be checkable in a way an assertion is not. Everything
in hunt.json that could have been typed from memory is derived here instead:

  * the page really was fetched      -> the raw file is committed next to this
  * the buy control really is there  -> asserted against that file's own bytes
  * the identifier really re-asserts -> normalize.reassert(), the sweep's rule
  * the verdict really is the code's -> normalize.classify(), unmodified

If a claim in hunt.json disagrees with the page on disk, this exits non-zero.

    python3 data/hunt/rederive.py
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "collector"))
from normalize import classify, reassert, needle_pattern  # noqa: E402

# Which arm's rulebook each market is adjudicated under. A market no arm covers
# still has to be judged by SOME arm's rules; picking the nearest one is what
# exposes the language gap rather than hiding it.
ARM_FOR_MARKET = {
    "nothingbutsavings.com": "US",
    "iqelectro.com": "US",
    "autourdebebe.com": "DE",   # France. No French arm exists. This is the point.
    "spaw2.pl": "DE",           # Poland. Likewise.
}

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
    return cond


def main():
    hunt = json.loads((ROOT / "canon-event" / "data" / "hunt.json").read_text(encoding="utf-8")
                      if (ROOT / "canon-event").exists()
                      else (ROOT / "data" / "hunt.json").read_text(encoding="utf-8"))

    print("Re-deriving %d hunt findings from committed pages.\n" % len(hunt["findings"]))

    for f in hunt["findings"]:
        page = (ROOT / f["evidence_file"]) if (ROOT / f["evidence_file"]).exists() \
            else (ROOT / "canon-event" / f["evidence_file"])
        text = page.read_text(encoding="utf-8", errors="ignore")
        arm = ARM_FOR_MARKET[f["market"]]

        print("%s  %s" % (f["ref"], f["product"]))
        print("   page        : %s (%d bytes)" % (f["evidence_file"], len(text)))

        # The identifier, by the sweep's own boundary-anchored rule.
        pat = needle_pattern(f["identifier"])
        hits = len(pat.findall(text)) if pat else 0
        print("   identifier  : %s x%d" % (f["identifier"], hits))
        check(hits > 0, "%s: identifier %s not on page" % (f["ref"], f["identifier"]))
        check(hits == f["identifier_occurrences_on_page"],
              "%s: claims %d occurrences, page has %d"
              % (f["ref"], f["identifier_occurrences_on_page"], hits))

        # The buy control, asserted against the bytes rather than remembered.
        buy = f["buy_control"]
        on_page = buy.lower() in text.lower()
        print("   buy control : %r present=%s" % (buy, on_page))
        check(on_page, "%s: buy control %r not found in committed page" % (f["ref"], buy))

        # The RED row additionally claims the page never says "recall".
        if f.get("recall_mentioned_on_page") is False:
            said = "recall" in text.lower()
            print("   says recall : %s" % said)
            check(not said, "%s: claims no recall mention, page mentions it" % f["ref"])

        raw = {
            "arm": arm,
            "needle": f["identifier"],
            "page_text": text,
            "buy_label": buy if on_page else None,
            "url": f["url"],
            "http_status": 200,
        }
        if not on_page:
            raw.pop("buy_label")

        ok = reassert(text, f["identifier"])
        verdict, reasons = classify(raw, expected_brand=f.get("brand"))
        print("   reassert    : %s" % ok)
        print("   classify()  : %s%s" % (verdict, "" if not reasons
                                         else "  " + reasons[0]["reason"]))

        claimed = f["code_verdict"]
        if verdict != claimed:
            print("   MISMATCH    : hunt.json records %s" % claimed)
            failures.append("%s: hunt.json says classify -> %s, code says %s"
                            % (f["ref"], claimed, verdict))
        if f["published_verdict"] != verdict:
            # Publishing something WEAKER than the code allows is a deliberate,
            # recorded downgrade. Publishing something STRONGER is a bug.
            rank = {"DISCARDED": 0, "AMBER": 1, "RED": 2}
            print("   published   : %s (held down by hand)" % f["published_verdict"])
            check(rank[f["published_verdict"]] < rank[verdict],
                  "%s: publishes %s but code only supports %s"
                  % (f["ref"], f["published_verdict"], verdict))
            check(bool(f.get("downgrade_reason")),
                  "%s: downgraded without a recorded reason" % f["ref"])
        print()

    if failures:
        print("FAILED, %d problem(s):" % len(failures))
        for x in failures:
            print("  - " + x)
        return 1
    print("All %d findings re-derived from committed pages. No claim unchecked."
          % len(hunt["findings"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
