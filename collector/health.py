"""The detectors, and the arm state they force.

WHY THIS FILE EXISTS
--------------------
`contract/states.json` ends with a structural rule that this module is the
implementation of:

    "No detector is allowed to be invisible. Every one writes its verdict into
     health.json."

That rule exists because of the failure this whole project is built around. A
scraper that breaks does not raise; it returns zero rows. Zero rows render as an
empty hazard wall, and an empty hazard wall reads as SAFE. The bug becomes a
clean bill of health for a product that is still hurting people, and every
row-count check in the pipeline passes it happily.

So the detectors here are all written the same way round: they look for reasons
to DISBELIEVE our own output. A detector that concludes nothing was wrong still
writes that conclusion to the health file, because "this check did not fire" and
"this check never ran" are indistinguishable from an empty file, and only one of
them is reassuring.

WHY ZERO IS A FAULT UNTIL PROVEN OTHERWISE
------------------------------------------
The single most dangerous output this system can produce is an arm that returns
nothing. It is indistinguishable, downstream, from an arm that looked hard and
found nothing — and those two mean opposite things.

The resolution is that a negative has to be AFFIRMATIVE to be publishable. An
arm claiming zero must show an archived empty-result page: the marketplace's own
"no results" response, captured. With that, zero is a finding. Without it, zero
is our own silence and the arm is WITHHELD.

WHY THE THRESHOLDS ARE CONSTANTS AND NOT ARGUMENTS
--------------------------------------------------
Every threshold below is a named module constant with its reasoning attached. A
tunable threshold is a threshold that gets tuned after seeing the data, and a
detector tuned until it stops firing is worse than no detector: it launders a
judgement call into the appearance of a measurement. These numbers are frozen
before the first live sweep and any change to one is a visible diff.

Standard library only, no network. Feed it a sweep and it decides.
"""

import datetime

# Arm states, as frozen in contract/states.json.
MEASURED = "MEASURED"
DEGRADED = "DEGRADED"
WITHHELD = "WITHHELD"
STALE = "STALE"

# An arm must join its identifier to a listing on at least this share of inputs.
# Tracked SEPARATELY from row count, because the failure it catches is an arm
# returning thousands of clean, well-formed rows that match nothing we asked
# about. Row count is blind to that; coverage is not.
JOIN_KEY_COVERAGE_BOUND = 0.80

# Share of inputs that may fail outright before the arm is only partly credible.
FAIL_RATE_BOUND = 0.20

# A sweep-over-sweep collapse in RED rows beyond this fraction blacks the whole
# board. Set at 0.4 because the world does not improve by 40% in a day: a drop
# that large is our own measurement breaking, and the honest response is to stop
# publishing rather than to report the good news.
IMPLAUSIBLE_CLEANLINESS_DROP = 0.40

# How old a sweep may be before its rows are historical rather than current.
# Four hours: long enough to survive a slow full sweep, short enough that
# "buyable right now" stays a defensible phrase.
FRESHNESS_BOUND_S = 14400

# The currency each arm's storefront must quote. A DE arm returning USD did not
# reach the German market, whatever our configuration believes.
ARM_CURRENCY = {"US": "USD", "DE": "EUR", "IN": "INR"}


def _detector(fired, scope, note, **extra):
    """Every detector reports the same shape, firing or not.

    The `fired: false` case is deliberately as verbose as the firing case. A
    health file where quiet checks are omitted cannot be distinguished from one
    where they never ran.
    """
    out = {"fired": bool(fired), "scope": scope, "note": note}
    out.update(extra)
    return out


def identity_reassertion(rows):
    """Did every published RED row re-assert its identifier on the fetched page?

    This should never fire: the gate in adjudicate.py cannot emit a RED row
    without an assertion. It is checked anyway, downstream and independently,
    because the one bug that must never ship silently is a RED row that reached
    the wall without evidence. A guard that duplicates an invariant is cheap; the
    accusation it prevents is not.
    """
    reds = [r for r in rows if r.get("tier") == "RED"]
    missing = [r.get("source", {}).get("ref") for r in reds
               if not (r.get("evidence") or {}).get("assertion")]
    return _detector(
        bool(missing), "per row",
        ("Every RED row re-asserted its identifier on the fetched page."
         if not missing else
         "%d RED row(s) reached the wall with no assertion. These are not "
         "publishable." % len(missing)),
        checked=len(reds),
        offending=missing or None,
    )


def zero_is_a_fault(arm, listings_returned, empty_page_archived):
    """An arm claiming zero must corroborate it, or be withheld.

    `listings_returned` is EVERY listing the arm brought back, not the number that
    reddened. Those are opposite facts and passing the wrong one inverts this
    detector completely.

    It happened. The detector was handed the RED count, so an arm that returned
    1,066 listings and matched none of them reported "returned zero rows with no
    archived empty-result page", and the survival figure was withheld on the
    grounds that we had learned nothing. We had learned something: we looked at
    1,066 listings and none of them was the recalled product. That is a finding,
    and withholding it was the same error as publishing an empty page — a
    measurement misreported as silence.

    `empty_page_archived` is the marketplace's own no-results page, captured. It
    is the difference between "we looked and it is gone" and "we returned
    nothing", which are opposite claims that look identical in a row count.
    """
    fired = listings_returned == 0 and not empty_page_archived
    return _detector(
        fired, "per claim",
        ("%s returned zero listings with no archived empty-result page to "
         "corroborate it. Zero is not published as a finding without an "
         "affirmative negative." % arm) if fired else
        ("%s returned %d listings and adjudicated every one."
         % (arm, listings_returned) if listings_returned else
         "%s returned zero rows, corroborated by an archived empty-result "
         "page. The negative is affirmative and publishable." % arm),
        arm=arm,
    )


def join_key_coverage(arm, joined, inputs):
    """Did the arm actually match what we asked about?

    Deliberately separate from the row count. An arm can be busy and useless at
    the same time, and only this ratio can tell.
    """
    coverage = (joined / inputs) if inputs else 0.0
    fired = inputs > 0 and coverage < JOIN_KEY_COVERAGE_BOUND
    return _detector(
        fired, "per arm",
        "Tracked separately from row count. An arm can return thousands of "
        "clean rows that match nothing, and a row-count check passes it "
        "happily.",
        arm=arm, coverage=round(coverage, 4), bound=JOIN_KEY_COVERAGE_BOUND,
    )


def currency_fingerprint(rows):
    """Every row must carry its arm's currency, or the geography is unproven.

    Scraper Studio has no exit-country flag: the country lives in the collector's
    own input, which is our configuration and therefore not evidence. The
    storefront's currency symbol is the cheapest proof that comes from inside the
    fetched page. This detector is what makes the three-arm comparison mean
    anything at all — without it, a silent country drift produces rows that are
    individually well-formed and collectively meaningless.
    """
    offending = []
    for row in rows:
        got = (row.get("evidence") or {}).get("currency")
        for arm, verdict in (row.get("arms") or {}).items():
            if verdict == "RED" and got and got != ARM_CURRENCY.get(arm):
                offending.append({"ref": row.get("source", {}).get("ref"),
                                  "arm": arm, "got": got,
                                  "want": ARM_CURRENCY.get(arm)})
    return _detector(
        bool(offending), "per row",
        "Every DE row must carry EUR, every IN row INR, every US row USD. "
        "Kills a country-drift failure class that cross-arm comparison is "
        "blind to.",
        offending=offending or None,
    )


def sibling_differential(arm_rows, previous=None):
    """One arm collapsing while its siblings hold is a collector fault, not news.

    Requires persistence across two sweeps before firing. A single-sweep dip is
    ordinary marketplace noise, and a detector that fires on noise is one that
    gets ignored, which is the same as not having it.
    """
    live = {a: n for a, n in arm_rows.items() if n > 0}
    dead = sorted(a for a, n in arm_rows.items() if n == 0)
    persisted = bool(previous) and all(previous.get(a, 0) == 0 for a in dead)
    fired = bool(dead) and bool(live) and persisted
    return _detector(
        fired, "across arms",
        ("%s collapsed while %s held, across two consecutive sweeps."
         % (", ".join(dead), ", ".join(sorted(live)))) if fired else
        "No arm has collapsed against its siblings across two sweeps.",
        collapsed=dead or None, holding=sorted(live) or None,
        requires="persistence across two sweeps",
    )


def implausible_cleanliness(red_now, red_before):
    """Did the world get suspiciously better?

    The asymmetry is deliberate: a large RISE in hazards is publishable, a large
    FALL is suspicious. Recalled products do not leave three marketplaces
    overnight, so a collapse is far more likely to be our matcher breaking than
    the world improving. Reporting that as good news is the exact inversion this
    project exists to refuse, so it blacks the whole board instead.
    """
    if not red_before:
        return _detector(False, "whole board",
                         "No prior sweep to compare against.",
                         threshold=IMPLAUSIBLE_CLEANLINESS_DROP)
    drop = (red_before - red_now) / red_before
    return _detector(
        drop > IMPLAUSIBLE_CLEANLINESS_DROP, "whole board",
        "Did the world get suspiciously better? A drop beyond the threshold "
        "blacks the entire board.",
        threshold=IMPLAUSIBLE_CLEANLINESS_DROP, drop=round(drop, 4),
        red_now=red_now, red_before=red_before,
    )


def schema_drift(reports):
    """Did the collector start returning fields we do not recognise?

    Sourced from the normaliser's `unmapped` counts. Drift is the quiet failure
    mode of an AI-generated schema: the job still succeeds, the rows still
    validate, and a column silently stops being populated. Naming the strangers
    turns that into a visible event on the day it happens.
    """
    drifted = {r["arm"]: r["unmapped_fields"] for r in reports
               if r.get("unmapped_fields")}
    return _detector(
        bool(drifted), "per arm",
        ("Collector returned fields the contract does not map: %s. The rows "
         "still validate, which is exactly why this needs saying."
         % "; ".join("%s: %s" % (a, ", ".join(f)) for a, f in drifted.items()))
        if drifted else
        "Every field the collectors returned is mapped by the contract.",
        drifted=drifted or None,
    )


def freshness(swept_at, now, bound_s=FRESHNESS_BOUND_S):
    """Is this sweep still current enough to speak in the present tense?

    "Buyable right now" is a claim about the present. Past the bound the rows are
    historical, the DAY counters freeze, and the wall says so rather than quietly
    continuing to count.
    """
    age = int((now - swept_at).total_seconds())
    return _detector(
        age > bound_s, "whole board",
        "Rows older than the freshness bound are historical. DAY counters "
        "freeze at last capture rather than continuing to count.",
        age_s=age, bound_s=bound_s,
    )


def arm_state(arm, listings_returned, inputs, fails, joined,
              empty_page_archived=False, heal_status="none", stale=False):
    """The single state this arm renders in, and the reason for it.

    Order matters and is not arbitrary: it runs from least to most credible. A
    withheld arm cannot be talked up into DEGRADED by a good coverage number,
    because the reasons for withholding are reasons to distrust the numbers
    themselves.
    """
    if heal_status in ("in_flight", "awaiting_approval"):
        return {"state": WITHHELD, "reason": "heal_%s" % heal_status}
    # An arm that brought back nothing at all is silent. An arm that brought back
    # listings and matched none of them has measured, and its zero is publishable.
    if listings_returned == 0 and not empty_page_archived:
        return {"state": WITHHELD, "reason": "zero_listings_uncorroborated"}
    if inputs and fails / inputs > FAIL_RATE_BOUND:
        return {"state": DEGRADED, "reason": "fail_rate_above_bound"}
    if inputs and (joined / inputs) < JOIN_KEY_COVERAGE_BOUND:
        return {"state": DEGRADED, "reason": "join_key_coverage_below_bound"}
    if stale:
        return {"state": STALE, "reason": "exceeds_freshness_bound"}
    return {"state": MEASURED, "reason": None}


def verdict_line(arms):
    """The sentence the wall prints, derived from the arm states, never typed.

    Deriving it means the prose cannot drift out of agreement with the data. A
    hand-written verdict is a second source of truth, and the second one is
    always the one that goes stale.
    """
    withheld = sorted(a for a, s in arms.items() if s["state"] == WITHHELD)
    degraded = sorted(a for a, s in arms.items() if s["state"] == DEGRADED)
    if not withheld and not degraded:
        return ("All arms measured. Figures are live. The absence of a red row "
                "is still not evidence of safety.")
    parts = []
    if withheld:
        parts.append("WITHHELD for %s. Figures depending on %s are struck."
                     % (", ".join(withheld), " and ".join(withheld)))
    if degraded:
        parts.append("Partial for %s." % ", ".join(degraded))
    parts.append("Figures computed from the seed corpus are unaffected and "
                 "remain live.")
    return " ".join(parts)


def build(sweep_id, swept_at, arms, rows, reports, previous=None, now=None):
    """Assemble the health file. Every detector appears, firing or not.

    `previous` is the prior sweep's summary, used by the two detectors that need
    history. Absent on a first sweep, and both degrade to not-fired with the
    reason stated rather than silently passing.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    prev_arm_rows = (previous or {}).get("arm_rows") or {}
    prev_red = (previous or {}).get("red_count")

    fresh = freshness(swept_at, now)
    arm_rows = {a: v.get("rows", 0) for a, v in arms.items()}
    red_count = sum(1 for r in rows if r.get("tier") == "RED")

    detectors = {
        "identity_reassertion": identity_reassertion(rows),
        # listings, not rows. See zero_is_a_fault's docstring: passing the RED
        # count here inverts the detector.
        "zero_is_a_fault": _first_firing(
            [zero_is_a_fault(a, v.get("listings", v.get("rows", 0)),
                             v.get("empty_page_archived", False))
             for a, v in arms.items()]),
        "join_key_coverage": _first_firing(
            [join_key_coverage(a, v.get("joined", 0), v.get("inputs", 0))
             for a, v in arms.items()]),
        "sibling_differential": sibling_differential(arm_rows, prev_arm_rows),
        "implausible_cleanliness": implausible_cleanliness(red_count, prev_red),
        "currency_fingerprint": currency_fingerprint(rows),
        "schema_drift": schema_drift(reports),
        "freshness": fresh,
    }

    return {
        "sweep_id": sweep_id,
        "swept_at": swept_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "arms": arms,
        "detectors": detectors,
        # The per-arm normaliser reports, carried rather than consumed. They are
        # the raw material behind the discard rate and the credit arithmetic, and
        # a health file that computed a detector from them and then dropped them
        # would leave every downstream figure unre-derivable.
        "reports": reports,
        "verdict": verdict_line(arms),
        "blackout": detectors["implausible_cleanliness"]["fired"],
    }


def _first_firing(results):
    """Report the firing instance if there is one, else the first quiet one.

    The health file carries one entry per detector, not one per arm. When
    several arms trip the same detector the firing one is what needs saying;
    when none do, the quiet verdict still has to appear so the check is visibly
    present rather than absent.
    """
    for r in results:
        if r["fired"]:
            return r
    return results[0] if results else _detector(False, "per arm", "No arms to check.")
