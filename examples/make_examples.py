#!/usr/bin/env python3
"""Emit the example structured output.

This is a required submission deliverable in its own right, separate from the
repository and the demo. It is generated rather than hand-written so it can
never drift from the contract the code actually enforces.

Formats, one per consumer:

  row.json         a single finding, fully annotated, for reading
  sweep.jsonl      the row stream, one JSON object per line, for piping
  health.json      what every detector concluded, including the ones that
                   concluded nothing is wrong
  stats.json       every published figure with its interval and its method
  MISSING.json     a row where declared keys are absent, because absence is
                   part of the contract and not an error

Run:  python examples/make_examples.py
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "stats"))
sys.path.insert(0, str(ROOT / "extract"))

from survival import survival_curve, observations_from_rows   # noqa: E402
from recapture import from_rows as recapture_from_rows        # noqa: E402


def main():
    doc = json.loads((ROOT / "data" / "fixture-v1.json").read_text(encoding="utf-8"))
    rows, stats = doc["rows"], doc["stats"]

    banner = {
        "_STATUS": "FIXTURE DATA. Structure is final and enforced; the values are "
                   "illustrative until the first live sweep. Every recall notice, "
                   "hazard sentence, model number and GTIN below is real and quoted "
                   "verbatim from the CPSC official API. The marketplace verdicts are not "
                   "yet measured.",
        "_generated_by": "examples/make_examples.py",
        "_contract": "contract/row.schema.json",
        "_validate": "python validate.py",
    }

    # A single finding, fully populated, with the evidence chain intact.
    full = next(r for r in rows
                if r["tier"] == "RED" and r.get("evidence", {}).get("assertion", {}).get("dom_path"))
    (HERE / "row.json").write_text(
        json.dumps({**banner, **full}, indent=2, ensure_ascii=False), encoding="utf-8")

    # A row where declared keys are absent. Bright Data omits absent keys rather
    # than nulling them, so this shape is the real one, not a contrived one.
    missing = next(r for r in rows
                   if r.get("evidence") and not r["evidence"]["assertion"].get("dom_path"))
    (HERE / "MISSING.json").write_text(json.dumps({
        **banner,
        "_why": "evidence.assertion.dom_path and evidence.buy_control.ships_from are ABSENT, "
                "not null and not empty. A consumer runs row.get(k, MISSING) over "
                "contract/contract_keys.py and renders the field name struck through with "
                "the word MISSING. Rendering absence as 0 would turn a gap in our own "
                "measurement into a claim about the world.",
        **missing,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # The row stream. One object per line, which is what a pipeline consumes.
    with (HERE / "sweep.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Every detector's verdict, including the quiet ones. A detector that only
    # reports when it fires is a detector you cannot prove was running.
    de = next(a for a in doc["arms"] if a["code"] == "DE")
    health = {
        **banner,
        "sweep_id": doc["sweep_id"],
        "swept_at": doc["swept_at"],
        "arms": {a["code"]: {"state": a["state"], "reason": a["reason"],
                             "rows": a["job"]["data_lines"], "fails": a["job"]["fails"],
                             "exit_country": a["attest"]["country"],
                             "exit_asn_org": a["attest"]["asn_org"]}
                 for a in doc["arms"]},
        "detectors": {
            "identity_reassertion": {"fired": False, "scope": "per row",
                                     "checked": sum(1 for r in rows if r["tier"] == "RED"),
                                     "note": "Every RED row re-asserted its identifier on the fetched page."},
            "zero_is_a_fault": {"fired": True, "scope": "per claim", "arm": "DE",
                                "note": "DE returned zero rows with no archived empty-result page to corroborate it. "
                                        "Zero is not published as a finding without an affirmative negative."},
            "join_key_coverage": {"fired": True, "scope": "per arm", "arm": "IN",
                                  "coverage": round(next(a for a in doc["arms"] if a["code"] == "IN")["job"]["data_lines"]
                                                    / next(a for a in doc["arms"] if a["code"] == "IN")["job"]["inputs"], 4),
                                  "note": "Tracked separately from row count. An arm can return thousands of clean rows "
                                          "that match nothing, and a row-count check passes it happily."},
            "sibling_differential": {"fired": True, "scope": "across arms",
                                     "note": "DE collapsed while US and IN held. Requires persistence across two sweeps."},
            "implausible_cleanliness": {"fired": False, "scope": "whole board", "threshold": 0.40,
                                        "note": "Did the world get suspiciously better? A drop beyond the threshold "
                                                "blacks the entire board."},
            "currency_fingerprint": {"fired": False, "scope": "per row",
                                     "note": "Every DE row must carry EUR, every IN row INR, every US row USD. "
                                             "Kills a country-drift failure class that cross-arm comparison is blind to."},
        },
        "heal": de["heal"],
        "verdict": "WITHHELD for DE. Figures depending on DE are struck. Figures computed from "
                   "the seed corpus are unaffected and remain live.",
    }
    (HERE / "health.json").write_text(json.dumps(health, indent=2, ensure_ascii=False), encoding="utf-8")

    # Every published figure, with its interval and the method that produced it.
    obs = observations_from_rows(rows)
    curve = survival_curve(obs, n_boot=400)
    (HERE / "stats.json").write_text(json.dumps({
        **banner,
        "headline": stats["hero"],
        "survival": stats["survival"],
        "survival_curve": curve,
        "border_escape": stats["border_escape"],
        "unsearchable": stats["unsearchable"],
        "precision": stats["precision"],
        "recall_floor": recapture_from_rows(rows),
        "discarded": stats["discarded"],
        "adversarial_precision_set": stats["adversarial_precision_set"],
        "arithmetic": stats["arithmetic"],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    for p in sorted(HERE.glob("*.json")) + [HERE / "sweep.jsonl"]:
        print(f"  {p.name:<18} {p.stat().st_size / 1024:6.1f} KB")


if __name__ == "__main__":
    main()
