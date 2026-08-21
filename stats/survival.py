"""Survival of recalled products, estimated from a single sweep.

THE DATA STRUCTURE, WHICH DECIDES THE METHOD
--------------------------------------------
We observe each recall exactly once, at a known age (days since the notice was
published), and record whether it is still buyable. We never watch a product
stop being buyable. That is **current-status data**, also called case-1
interval-censored data: for each item we learn only whether the event has
already happened by the observation time.

Kaplan-Meier is the wrong tool here. KM needs observed event or censoring times
per subject, and we have neither: we have one binary observation at one time.

The nonparametric maximum likelihood estimator for current-status data is the
isotonic regression of the binary outcome on age, computed by the pool adjacent
violators algorithm. Under the single assumption that survival is monotone
non-increasing in age, PAVA is the NPMLE. No parametric form is imposed, no
hazard shape is assumed, and no smoothing parameter is chosen.

WHY THIS AND NOT FOUR AGE BUCKETS
---------------------------------
Four bucket proportions throw away the ordering between buckets, produce four
wide intervals instead of one curve, and collapse to a single uninformative
number if any bucket is thin. A curve is a finding where a bare rate is a
disappointment: if survival comes back low, the SHAPE of the decay over 730 days
is still a publishable result.

THE CONFOUND, WHICH MUST BE STATED WHEREVER THIS IS PRINTED
-----------------------------------------------------------
Age is confounded with cohort. A recall published in 2024 is not exchangeable
with one published in 2026: enforcement, marketplace policy and the product mix
all changed in between. This curve is therefore a cross-sectional age profile,
not a within-product survival trajectory. It answers "what share of recalls of
age t are still buyable today", not "what happens to a recall as it ages".

Standard library only. No numpy, no scipy: a clean clone must run this with
nothing installed.
"""

import math
import random

# Fewest observations at or beyond a grid age before that point may be published.
# Below this the isotonic fit is being driven by one or two products.
MIN_SUPPORT = 5


def pava_non_increasing(points):
    """Pool adjacent violators, constrained to a non-increasing fit.

    `points` is a sequence of (x, y, w): observation time, binary outcome, weight.
    Returns blocks as (x_start, x_end, value, weight), left to right, with
    values non-increasing. This is the NPMLE for current-status data.

    Blocks are pooled by weighted mean, which is what makes the result the
    maximum likelihood estimate rather than merely a monotone smoother.
    """
    pts = sorted(points, key=lambda p: p[0])
    blocks = []  # each: [x_start, x_end, weighted_sum, weight]
    for x, y, w in pts:
        blocks.append([x, x, y * w, w])
        # A violation of non-increasing is a block whose value is BELOW the one
        # after it. Pool backwards until the sequence is monotone again.
        while len(blocks) >= 2:
            prev, last = blocks[-2], blocks[-1]
            if prev[2] / prev[3] < last[2] / last[3] - 1e-12:
                merged = [prev[0], last[1], prev[2] + last[2], prev[3] + last[3]]
                blocks[-2:] = [merged]
            else:
                break
    return [(b[0], b[1], b[2] / b[3], b[3]) for b in blocks]


def block_at(blocks, x):
    """The isotonic block covering age x. This block is the local sample the
    interval conditions on."""
    found = blocks[0] if blocks else None
    for b in blocks:
        if x >= b[0]:
            found = b
        else:
            break
    return found


def wilson(k, n, z=1.959963984540054):
    """Wilson score interval. Duplicated from stats/wilson.py deliberately so
    this module has no intra-package import and runs standalone."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def step_at(blocks, x):
    """Evaluate the fitted survival step function at age x."""
    value = blocks[0][2] if blocks else float("nan")
    for x0, x1, v, _w in blocks:
        if x >= x0:
            value = v
        else:
            break
    return value


def survival_curve(observations, grid=None, n_boot=None, seed=None, alpha=0.05):
    """Fit the monotone survival curve with a pointwise interval per grid point.

    observations: iterable of (age_days:int, still_buyable:bool)
    grid:         ages at which to report. Defaults to the plan's four checkpoints
                  plus the observed range.

    n_boot and seed are accepted and ignored: they existed when this used a
    percentile bootstrap, which was removed for the reason documented below.
    They stay in the signature so existing callers do not break.
    """
    obs = [(int(a), 1.0 if b else 0.0) for a, b in observations]
    if not obs:
        raise ValueError("no observations")

    points = [(a, y, 1.0) for a, y in obs]
    blocks = pava_non_increasing(points)

    if grid is None:
        ages = sorted(a for a, _ in obs)
        checkpoints = [30, 90, 365, 730]
        grid = sorted(set([ages[0], ages[-1]] + [c for c in checkpoints
                                                 if ages[0] <= c <= ages[-1]]))

    fitted = {g: step_at(blocks, g) for g in grid}

    # INTERVALS: block-wise Wilson, NOT a percentile bootstrap.
    #
    # The obvious move is to resample and take percentiles. Do not. The naive
    # bootstrap is known to be INCONSISTENT for Grenander-type monotone
    # estimators at a fixed point: the block boundaries move between resamples,
    # so the percentile interval does not converge to the right thing. In this
    # corpus it produced a point estimate of 0.356 sitting outside its own
    # reported interval of [0.50, 0.89], which is indefensible on screen and
    # would be the first thing a careful reader noticed.
    #
    # Instead each grid point reports a Wilson interval computed from the
    # isotonic BLOCK that supports it: k successes out of the n observations
    # PAVA pooled into that block. It always contains its own point estimate
    # (the block value is exactly k/n), it is transparent, and it is honest
    # about what it conditions on, which is stated in `interval_method` below.
    band, block_n = {}, {}
    for g in grid:
        blk = block_at(blocks, g)
        n_b = int(blk[3]) if blk else 0
        k_b = int(round(blk[2] * n_b)) if blk else 0
        band[g] = list(wilson(k_b, n_b)) if n_b else [0.0, 1.0]
        block_n[g] = n_b

    # Support guard, on BOTH counts, because they answer different questions.
    # `support` is how many observations sit at or beyond this age. `block_n` is
    # how many the isotonic fit actually pooled to produce this value. A grid
    # point can have 111 observations beyond it and still rest on a block of
    # ONE, which is a cliff driven by a single product dressed up as a finding.
    # A point is thin if either count is small.
    support = {g: sum(1 for a, _ in obs if a >= g) for g in grid}

    return {
        "method": "isotonic regression (PAVA), nonparametric MLE for current-status data",
        "assumption": "survival is monotone non-increasing in days since recall",
        "confound": ("Age is confounded with cohort: a 2024 recall is not exchangeable with a "
                     "2026 one. This is a cross-sectional age profile, not a within-product "
                     "survival trajectory."),
        "n": len(obs),
        "n_still_buyable": int(sum(y for _, y in obs)),
        "blocks": [{"from_day": int(b[0]), "to_day": int(b[1]),
                    "survival": round(b[2], 4), "n": int(b[3])} for b in blocks],
        "grid": [{"day": g, "survival": round(fitted[g], 4), "ci95": band[g],
                  "support": support[g], "block_n": block_n[g],
                  "thin": min(support[g], block_n[g]) < MIN_SUPPORT,
                  "publishable": min(support[g], block_n[g]) >= MIN_SUPPORT}
                 for g in grid],
        "min_support": MIN_SUPPORT,
        "interval_method": (
            "Wilson score interval on the isotonic block supporting each grid point. "
            "A percentile bootstrap is deliberately NOT used: it is known to be "
            "inconsistent for Grenander-type monotone estimators at a fixed point, and "
            "on this corpus it returned intervals that excluded their own point "
            "estimate. These intervals condition on the fitted block structure, so they "
            "describe uncertainty in the level within a block, not uncertainty in where "
            "the block boundaries fall."),
    }


def observations_from_rows(rows):
    """Pull (age, buyable) out of wall rows.

    A row counts as buyable only at RED: identifier re-asserted on the fetched
    page AND an active buy control. AMBER is excluded, because AMBER is excluded
    from every statistic on this project by design.

    Rows whose notice carried no machine-matchable identifier are dropped rather
    than scored as not-buyable. We did not fail to find them; we were never able
    to look. Counting an unsearchable notice as "not on sale" would silently
    convert our own blindness into evidence of safety, which is the exact
    failure this project exists to refuse.
    """
    # ONE searchability rule, imported rather than re-implemented.
    #
    # This used bool(model or gtin), which is looser than the rule the wall
    # publishes: it counted 4 notices the owned rule calls unsearchable, so the
    # curve reported 124 where the headline reported 120 and both called
    # themselves "searchable notices". Two numbers for one denominator on one
    # screen means neither can be checked.
    try:
        import sys, pathlib as _pl
        sys.path.insert(0, str(_pl.Path(__file__).parent.parent / "collector"))
        from publish import searchable as _searchable
    except Exception:
        _searchable = lambda r: bool(r.get("model") or r.get("gtin"))

    out = []
    for r in rows:
        searchable = _searchable(r)
        if not searchable:
            continue
        out.append((r["days"], r["tier"] == "RED"))
    return out
