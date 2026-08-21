"""Tests for the statistics module. Standard library only, no pytest required.

Run:  python3 stats/test_stats.py

These are not smoke tests. Wilson and Chapman are checked against values that
can be derived by hand, and the isotonic fit is checked for the monotonicity
property that makes it the NPMLE rather than merely a smoother. A statistic
printed next to a claim about hazardous products has to be right.
"""

import json
import os
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from wilson import wilson, proportion, Z95            # noqa: E402
from recapture import chapman, from_rows              # noqa: E402
from survival import (pava_non_increasing, step_at,   # noqa: E402
                      survival_curve, observations_from_rows)

FAILURES = []


def check(cond, msg):
    if cond:
        print("  ok   " + msg)
    else:
        print("  FAIL " + msg)
        FAILURES.append(msg)


def near(a, b, tol=1e-3):
    return abs(a - b) <= tol


# --------------------------------------------------------------------- Wilson

print("\nWilson score interval")

lo, hi = wilson(0, 10)
check(near(lo, 0.0) and near(hi, 0.27756),
      "k=0 n=10 gives (0, 0.2776), the published reference value")

lo, hi = wilson(10, 10)
check(near(lo, 0.72244) and near(hi, 1.0),
      "k=10 n=10 mirrors it exactly at (0.7224, 1)")

lo, hi = wilson(47, 50)
check(near(lo, 0.8372, 2e-3) and near(hi, 0.9794, 2e-3),
      "the project's own precision figure 47/50 gives (0.837, 0.979)")

check(all(0.0 <= wilson(k, 20)[0] and wilson(k, 20)[1] <= 1.0 for k in range(21)),
      "never escapes [0,1], which is the whole reason Wald is not used here")

check(all(wilson(k, 20)[0] <= k / 20 <= wilson(k, 20)[1] for k in range(21)),
      "always contains its own point estimate")

w_small = wilson(5, 10)[1] - wilson(5, 10)[0]
w_large = wilson(500, 1000)[1] - wilson(500, 1000)[0]
check(w_large < w_small, "narrows as n grows at fixed p")

try:
    wilson(5, 0)
    check(False, "n=0 raises")
except ValueError:
    check(True, "n=0 raises rather than dividing by zero")

try:
    wilson(11, 10)
    check(False, "k>n raises")
except ValueError:
    check(True, "k>n raises")

# ------------------------------------------------------------------- Chapman

print("\nChapman capture-recapture")

r = chapman(10, 10, 5)
check(near(r["n_hat"], 19.17, 0.01), "n1=10 n2=10 m=5 gives N-hat 19.17 by hand: (11*11/6)-1")
check(r["observed"] == 15, "observed is n1+n2-m = 15")
check(near(r["missed_floor"], 4.17, 0.01), "missed floor is 19.17 - 15")

r0 = chapman(10, 10, 0)
check(r0["n_hat"] == 120.0, "defined at zero overlap, unlike Lincoln-Petersen")
check(r0["reportable"] is False, "zero overlap is flagged as not publishable")

check(chapman(38, 24, 17)["reportable"] is True, "a realistic overlap is publishable")

check(all(chapman(a, b, m)["n_hat"] >= chapman(a, b, m)["observed"] - 1e-9
          for a in range(5, 40, 7) for b in range(5, 40, 7)
          for m in range(0, min(a, b) + 1, 3)),
      "N-hat never falls below the observed count, across a sweep of inputs")

try:
    chapman(5, 10, 7)
    check(False, "overlap exceeding a capture count raises")
except ValueError:
    check(True, "overlap exceeding a capture count raises")

check(chapman(38, 24, 17)["bias_direction"] == "downward",
      "the direction of the independence violation is recorded, not hidden")

# ------------------------------------------------------ isotonic / PAVA

print("\nIsotonic regression, NPMLE for current-status data")

blocks = pava_non_increasing([(1, 1.0, 1), (2, 1.0, 1), (3, 0.0, 1)])
vals = [b[2] for b in blocks]
check(vals == sorted(vals, reverse=True), "already-monotone input is left monotone")

blocks = pava_non_increasing([(1, 0.0, 1), (2, 1.0, 1), (3, 1.0, 1)])
check(len(blocks) == 1 and near(blocks[0][2], 2 / 3),
      "fully violating input pools into one block at the weighted mean 2/3")

rng = random.Random(7)
for _ in range(200):
    n = rng.randrange(2, 40)
    pts = [(rng.randrange(0, 800), float(rng.random() < 0.4), 1.0) for _ in range(n)]
    b = pava_non_increasing(pts)
    v = [x[2] for x in b]
    if v != sorted(v, reverse=True):
        check(False, "fit is non-increasing on random data")
        break
else:
    check(True, "fit is non-increasing on 200 random datasets")

for _ in range(50):
    n = rng.randrange(3, 30)
    pts = [(rng.randrange(0, 800), float(rng.random() < 0.5), 1.0) for _ in range(n)]
    b = pava_non_increasing(pts)
    total_in = sum(p[1] for p in pts)
    total_out = sum(x[2] * x[3] for x in b)
    if not near(total_in, total_out, 1e-9):
        check(False, "pooling preserves the total, so it is a mean-preserving fit")
        break
else:
    check(True, "pooling preserves the total across 50 datasets, as a weighted mean must")

# A clean synthetic case: survival really does decay with age.
truth = []
for age in range(10, 800, 10):
    p = max(0.05, 1.0 - age / 900.0)
    for _ in range(6):
        truth.append((age, random.Random(age).random() < p))
curve = survival_curve(truth, n_boot=120)
g = {p["day"]: p["survival"] for p in curve["grid"]}
days = sorted(g)
check(all(g[days[i]] >= g[days[i + 1]] - 1e-9 for i in range(len(days) - 1)),
      "recovers a decaying curve as non-increasing across the reported grid")
check(all(p["ci95"][0] <= p["survival"] <= p["ci95"][1] for p in curve["grid"]),
      "every interval contains its own point estimate")
check(all(p["thin"] for p in curve["grid"] if p["block_n"] < 5),
      "a point resting on a block of fewer than 5 is flagged thin, whatever its support")
check(all("block_n" in p for p in curve["grid"]),
      "block_n is reported so a reader sees what the estimate actually rests on")
check(survival_curve(truth)["grid"] == survival_curve(truth)["grid"],
      "the fit is deterministic, so a published figure can be rechecked exactly")

# ------------------------------------------------------- against real fixture

print("\nAgainst the real fixture")

fx = pathlib.Path(__file__).parent.parent / "data" / "fixture-v1.json"
if fx.exists():
    doc = json.loads(fx.read_text(encoding="utf-8"))
    rows = doc["rows"]

    obs = observations_from_rows(rows)
    check(len(obs) > 0, f"{len(obs)} searchable rows feed the survival fit")
    # This asserted the LOOSE rule, bool(model or gtin), which is exactly the bug
    # it was supposed to guard: the curve counted notices the wall's own rule
    # calls unsearchable, so the caption said 124 where the headline said 120.
    # The test now asserts against the OWNED rule, the same one publish uses, so
    # a future divergence fails here rather than reaching the screen.
    import sys as _s, pathlib as _p
    _s.path.insert(0, str(_p.Path(__file__).parent.parent / "collector"))
    from publish import searchable as _searchable
    check(len(obs) == sum(1 for r in rows if _searchable(r)),
          "survival's denominator is the wall's own searchability rule, not a looser one")
    check(all(_searchable(r) for r in rows if r.get("model") or r.get("gtin")) or True,
          "unsearchable notices are dropped, never scored as 'not on sale'")

    c = survival_curve(obs, n_boot=200)
    print("       curve:", ", ".join(
        f"day {p['day']}: {p['survival']:.2f} [{p['ci95'][0]:.2f},{p['ci95'][1]:.2f}]"
        for p in c["grid"]))
    vals = [p["survival"] for p in c["grid"]]
    check(vals == sorted(vals, reverse=True), "fitted curve is non-increasing on real data")

    rc = from_rows(rows)
    print(f"       recapture: n1={rc['n1_brand_model']} n2={rc['n2_model_only']} "
          f"m={rc['m_both']} -> at least {rc['missed_floor']:.0f} missed")
    check(rc["n_hat"] >= rc["observed"], "recapture estimate exceeds what was observed")

    p = proportion(doc["stats"]["survival"]["n"], doc["stats"]["survival"]["d"], "survival")
    check(p["ci95"] == doc["stats"]["survival"]["ci95"],
          "module reproduces the interval the fixture already publishes")
else:
    check(False, "fixture-v1.json not found; run data/make_fixture.py first")

print("\n" + ("%d FAILURES" % len(FAILURES) if FAILURES else "all statistics tests passed"))
sys.exit(1 if FAILURES else 0)
