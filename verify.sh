#!/usr/bin/env bash
# Everything a clean clone must pass. No dependencies: python3 and node only.
# This is the D6 clean-clone check, runnable by a judge in about five seconds.
set -e
cd "$(dirname "$0")"
echo "== regenerating fixtures from real CPSC notices =="
python3 data/make_fixture.py
echo
echo "== structured output against the frozen contract =="
python3 validate.py
echo
echo "== statistics =="
python3 stats/test_stats.py
echo
echo "== example structured output =="
python3 examples/make_examples.py
echo
echo "== identifier extractor =="
python3 extract/test_identifier.py
echo
echo "== collector normalizer =="
python3 collector/test_normalize.py
echo
echo "== adversarial precision set =="
python3 collector/adversarial.py
echo
echo "== sweep: adapter, arm combination, detectors, all offline =="
python3 collector/test_sweep.py
echo
echo "== hand-verification worksheet =="
python3 golden/grade.py
echo
echo "== wall renderer, headless =="
node test_render.js
echo
echo "ALL CHECKS PASSED"
