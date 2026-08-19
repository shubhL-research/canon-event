"""Capture-recapture: a floor under what the matcher never saw.

THE PROBLEM THIS SOLVES
-----------------------
Precision is measurable by hand: take 50 RED rows, check them, count how many
are right. Recall is not, because measuring it would require knowing the true
number of live listings for every recalled product, which is the thing we cannot
observe. So the honest position has always been "recall is unmeasured".

That is honest but it is weak, and it is the mirror image of the attack the
project already answers. We disclose that roughly 4 of 61 RED rows are expected
to be false. Nobody has asked the opposite question: how many hazards are on
sale right now that we walked straight past?

THE METHOD
----------
The matcher already runs two independent-ish query strategies against every
recall on every arm: brand+model, then model alone. Treat those as two capture
occasions on the same population.

    n1 = listings found by brand+model
    n2 = listings found by model alone
    m  = listings found by both

Lincoln-Petersen estimates the population as N = n1*n2/m. That estimator is
badly biased when m is small and undefined when m is zero, so we use Chapman's
bias-corrected form, which is defined at m = 0 and has far smaller bias at
realistic overlaps:

    N_hat = ((n1+1)(n2+1) / (m+1)) - 1

THE ASSUMPTION WE VIOLATE, AND WHY THAT IS SAFE HERE
-----------------------------------------------------
Capture-recapture assumes the two occasions are independent. Ours are not: both
queries contain the model token, so a listing that is hard for one to find is
hard for the other. Positive correlation between occasions inflates m relative
to independence, and inflating m DEFLATES N_hat.

The bias therefore runs in a known direction: N_hat is too small, so the implied
miss count is too small. That makes the result a LOWER BOUND on our blindness.
Reporting "we missed at least N" is safe under exactly this violation, and
reporting "we missed N" would not be. Say "at least" everywhere this is printed.

Standard library only.
"""


def chapman(n1, n2, m):
    """Chapman's bias-corrected capture-recapture estimator.

    n1, n2: counts found by each query strategy (each includes the overlap)
    m:      count found by both

    Returns the estimate plus everything needed to print it honestly.
    """
    if m > min(n1, n2):
        raise ValueError("overlap cannot exceed either capture count")
    if n1 < 0 or n2 < 0 or m < 0:
        raise ValueError("counts must be non-negative")

    observed = n1 + n2 - m
    n_hat = ((n1 + 1) * (n2 + 1) / (m + 1)) - 1

    # Seber's variance for the Chapman estimator.
    if m > 0:
        var = ((n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m)) / (((m + 1) ** 2) * (m + 2))
        se = var ** 0.5
    else:
        var, se = float("inf"), float("inf")

    missed = max(0.0, n_hat - observed)
    return {
        "estimator": "Chapman (bias-corrected Lincoln-Petersen)",
        "n1_brand_model": n1,
        "n2_model_only": n2,
        "m_both": m,
        "observed": observed,
        "n_hat": round(n_hat, 2),
        "se": None if se == float("inf") else round(se, 2),
        "missed_floor": round(missed, 2),
        "independence_violated": True,
        "bias_direction": "downward",
        "note": ("The two query strategies share the model token and are positively "
                 "correlated, which inflates the overlap and deflates N-hat. The miss "
                 "count is therefore a LOWER bound on what we failed to see, not an "
                 "estimate of it. Always print it as 'at least'."),
        "reportable": m >= 3,
        "reportable_note": ("With an overlap below 3 the estimator is too unstable to "
                            "publish. Report the raw counts and say recall is unmeasured."),
    }


def from_rows(rows):
    """Compute the counts from wall rows carrying `found_by_query`.

    Only RED rows count: a row that never resolved to a confirmed listing was
    not 'captured' by either strategy in the sense the estimator requires.
    """
    red = [r for r in rows if r.get("tier") == "RED" and r.get("found_by_query")]
    n1 = sum(1 for r in red if r["found_by_query"] in ("brand_model", "both"))
    n2 = sum(1 for r in red if r["found_by_query"] in ("model_only", "both"))
    m = sum(1 for r in red if r["found_by_query"] == "both")
    return chapman(n1, n2, m)
