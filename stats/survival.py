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


def step_at(blocks, x):
    """Evaluate the fitted survival step function at age x."""
    value = blocks[0][2] if blocks else float("nan")
    for x0, x1, v, _w in blocks:
        if x >= x0:
            value = v
        else:
            break
    return value


def survival_curve(observations, grid=None, n_boot=400, seed=20260821, alpha=0.05):
    """Fit the monotone survival curve with a pointwise bootstrap band.

    observations: iterable of (age_days:int, still_buyable:bool)
    grid:         ages at which to report. Defaults to the plan's four checkpoints
                  plus the observed range.

    The bootstrap is a plain nonparametric resample of items. It is seeded, so
    the published figure is reproducible from the committed data. Do not remove
    the seed: an unreproducible confidence band is not evidence.
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

    rng = random.Random(seed)
    draws = {g: [] for g in grid}
    n = len(obs)
    for _ in range(n_boot):
        sample = [obs[rng.randrange(n)] for _ in range(n)]
        b = pava_non_increasing([(a, y, 1.0) for a, y in sample])
        for g in grid:
            draws[g].append(step_at(b, g))

    band = {}
    lo_i = int(math.floor((alpha / 2) * n_boot))
    hi_i = min(n_boot - 1, int(math.ceil((1 - alpha / 2) * n_boot)) - 1)
    for g in grid:
        d = sorted(draws[g])
        band[g] = [round(d[lo_i], 4), round(d[hi_i], 4)]

    # Support guard. An isotonic fit is at its least stable at the boundaries,
    # where a single observation can drag the last block to 0 or 1 and render a
    # cliff that looks like a finding. Count how many observations actually sit
    # at or beyond each grid age, and flag the thin ones so the wall can grey
    # them out instead of publishing a cliff driven by one product.
    support = {g: sum(1 for a, _ in obs if a >= g) for g in grid}

    return {
        "method": "isotonic regression (PAVA), nonparametric MLE for current-status data",
        "assumption": "survival is monotone non-increasing in days since recall",
        "confound": ("Age is confounded with cohort: a 2024 recall is not exchangeable with a "
                     "2026 one. This is a cross-sectional age profile, not a within-product "
                     "survival trajectory."),
        "n": n,
        "n_still_buyable": int(sum(y for _, y in obs)),
        "blocks": [{"from_day": int(b[0]), "to_day": int(b[1]),
                    "survival": round(b[2], 4), "n": int(b[3])} for b in blocks],
        "grid": [{"day": g, "survival": round(fitted[g], 4), "ci95": band[g],
                  "support": support[g], "thin": support[g] < MIN_SUPPORT,
                  "publishable": support[g] >= MIN_SUPPORT} for g in grid],
        "min_support": MIN_SUPPORT,
        "bootstrap": {"draws": n_boot, "seed": seed, "resample": "nonparametric, by item"},
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
    out = []
    for r in rows:
        searchable = bool(r.get("model") or r.get("gtin"))
        if not searchable:
            continue
        out.append((r["days"], r["tier"] == "RED"))
    return out
