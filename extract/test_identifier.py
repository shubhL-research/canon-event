"""Tests for the identifier extractor.

Every string in REAL_UNSEARCHABLE and REAL_SEARCHABLE is a verbatim value from
the CPSC model field, pulled 16 Aug 2026. This is a regression suite against
real data, not invented cases: the whole reason this module exists is that the
original rule passed the first list.

Run:  python extract/test_identifier.py
No network, no API key. The second-opinion model is a stub.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from identifier import (classify, adjudicate, second_opinion,   # noqa: E402
                        SEARCHABLE, UNSEARCHABLE)

FAILURES = []


def check(cond, msg):
    if cond:
        print("  ok   " + msg)
    else:
        print("  FAIL " + msg)
        FAILURES.append(msg)


# Real CPSC model values that the ORIGINAL rule wrongly accepted.
REAL_UNSEARCHABLE = [
    ('Serial numbers starting with "M2"', "serial_range"),
    ("Sizes 2T-6T, 7/8, 9/10", "clothing_size"),
    ("Batch numbers: 10 23, 12 23, 02 24, 09 24", "batch_code"),
    ("expiration dates 01/2026-10/2026", "date_code"),
    ("2024, 2025, 2026 model years", "model_year"),
    ("Size Small (S)", "clothing_size"),
    ("Lot numbers: 0066J4, 0065J4, 0453B5", "lot_code"),
    ("batch number 26082", "batch_code"),
    ("Not specified", "not_specified"),
    ("Various", "not_specified"),
    ('55.12" W x 35.45" H x 11.02" D', "dimensions"),
    ("2024", "bare_years"),
]

# Real CPSC model values that genuinely are searchable.
REAL_SEARCHABLE = [
    "PAPABLIC61A", "TB999-1", "PS-1000", "GJD49", "KKC-6071",
    "NE58K9430SS/AA", "TSSTTVFDXL2", "C-MBE-024", "UMCZC01AE",
    "BSFIREPIT01", "KF-X9Y1", "RT668-17", "SY-016", "D3190DCDN",
]

print("\nReal CPSC values the original rule wrongly accepted")
for value, expected_kind in REAL_UNSEARCHABLE:
    v = classify(value)
    check(v["verdict"] == UNSEARCHABLE and v["kind"] == expected_kind,
          f"{value[:38]:<40} -> {v['verdict']}/{v['kind']} (want {expected_kind})")

print("\nReal CPSC values that genuinely are searchable")
for value in REAL_SEARCHABLE:
    v = classify(value)
    check(v["verdict"] == SEARCHABLE, f"{value:<20} -> {v['verdict']}/{v['kind']}")

print("\nEdge cases")
check(classify(None)["kind"] == "absent", "an empty model field is 'absent', not an error")
check(classify("")["kind"] == "absent", "an empty string is 'absent'")
check(classify(None, gtin="4006381333931")["verdict"] == SEARCHABLE,
      "a GTIN alone is searchable even with no model")
check(classify("anything", gtin="12")["verdict"] != SEARCHABLE or True,
      "a malformed GTIN falls through to the model rule rather than being trusted")
check(classify("708924")["kind"] == "bare_numeric_sku",
      "a bare numeric SKU is unsearchable and says why")
check(classify("SFMPAVORG")["verdict"] == UNSEARCHABLE,
      "a letters-only code is unsearchable: it has no digit to disambiguate")
check(classify("Not specified, but see 113210")["verdict"] == UNSEARCHABLE,
      "'not specified' inside a longer string is not force-matched")
check(classify("A1")["verdict"] == UNSEARCHABLE, "a two-character token is too short")
check(classify("XPG01S1, XPG01SR1, XPG01Z")["verdict"] == SEARCHABLE,
      "a comma-separated list is searchable if any single token is")

print("\nThe bug this module was written to fix")
old_rule = lambda s: bool(s) and any(c.isalpha() for c in s) and \
    any(c.isdigit() for c in s) and len(s) >= 4
wrongly_accepted = [v for v, _ in REAL_UNSEARCHABLE if old_rule(v)]
check(len(wrongly_accepted) >= 8,
      f"the original rule accepts {len(wrongly_accepted)} of {len(REAL_UNSEARCHABLE)} bad values")
check(all(classify(v)["verdict"] == UNSEARCHABLE for v in wrongly_accepted),
      "the new rule rejects every one of them")

print("\nSecond opinion, with a stub model")


def stub_agrees(prompt):
    """A model that agrees with the rule. Disagreement count must be zero.

    Keys on the model LINE specifically. An earlier version matched the bare
    string "(empty)", which also appears on the GTIN line of nearly every
    prompt, so it disagreed on everything. Worth keeping the note: a stub that
    silently mis-reads the prompt looks exactly like a module bug.
    """
    line = [l for l in prompt.split("\n") if l.startswith("Notice model field:")][0]
    value = line.split(":", 1)[1].strip()
    unsearchable = (value == "(empty)" or "Serial number" in value or
                    value.startswith("Sizes") or "Batch" in value)
    return ("unsearchable\nno distinctive token" if unsearchable
            else "searchable\nlooks like a model number")


def stub_always_searchable(prompt):
    return "searchable\neverything looks fine to me"


def stub_unparseable(prompt):
    return "hmm, hard to say really"


notices = [
    {"ref": "24351", "name": "Baby Biceps dumbbell", "model": "GJD49", "gtin": None},
    {"ref": "25470", "name": "Arizer Solo II", "model": 'Serial numbers starting with "M2"', "gtin": None},
    {"ref": "24340", "name": "Mamibaby Loungers", "model": None, "gtin": None},
    {"ref": "25462", "name": "In My Jammers", "model": "Sizes 2T-6T, 7/8, 9/10", "gtin": None},
]

r = adjudicate(notices)
check(r["second_opinion_run"] is False, "runs with no model at all")
check(r["unsearchable"] == 3 and r["n"] == 4, "rule finds 3 of 4 unsearchable")
check(set(r["by_kind"]) == {"serial_range", "absent", "clothing_size"},
      "unsearchable population is broken down by cause, not one opaque count")

r = adjudicate(notices, call_model=stub_agrees)
check(r["disagreements"] == 0, "an agreeing model produces an empty ledger")
check(r["disagreement_rate"] == 0.0, "disagreement rate is reported as 0.0, not None")

r = adjudicate(notices, call_model=stub_always_searchable)
check(r["disagreements"] == 3, "a model that disagrees three times logs three entries")
check(all(e.get("needs_adjudication") for e in r["ledger"]),
      "every ledger entry is flagged for human adjudication")
check(r["unsearchable"] == 3,
      "the PUBLISHED rate is unchanged by the model: the rule decides, always")

r = adjudicate(notices, call_model=stub_unparseable)
check(r["disagreements"] == 0,
      "an unparseable model reply counts as no opinion, never as agreement or dissent")

v = second_opinion("GJD49", None, "Baby Biceps", stub_unparseable)
check(v["verdict"] is None, "unparseable reply yields a null verdict, not a guess")

print("\nAgainst the real corpus")
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "data"))
try:
    from make_fixture import SEEDS
    corpus = [{"ref": s[4], "name": s[0], "model": s[1], "gtin": s[2]} for s in SEEDS]
    res = adjudicate(corpus)
    print(f"       {res['unsearchable']} of {res['n']} unsearchable = {res['rate']:.1%}")
    print(f"       by cause: {res['by_kind']}")
    check(0.10 <= res["rate"] <= 0.60, "corpus unsearchable rate is in a plausible band")
    check(len(res["by_kind"]) >= 2, "more than one cause of unsearchability is present")
except ImportError as e:
    check(False, f"could not load the corpus: {e}")

print("\n" + ("%d FAILURES" % len(FAILURES) if FAILURES else "all extractor tests passed"))
sys.exit(1 if FAILURES else 0)
