#!/usr/bin/env bash
# Everything a clean clone must pass. No dependencies: python3 and node only.
# This is the D6 clean-clone check, runnable by a judge in about five seconds.
set -e
cd "$(dirname "$0")"
echo "== regenerating fixtures from real CPSC notices =="
python data/make_fixture.py
echo
echo "== structured output against the frozen contract =="
python validate.py
echo
echo "== statistics =="
python stats/test_stats.py
echo
echo "== example structured output =="
python examples/make_examples.py
echo
echo "== identifier extractor =="
python extract/test_identifier.py
echo
echo "== wall renderer, headless =="
node test_render.js
echo
echo "ALL CHECKS PASSED"
