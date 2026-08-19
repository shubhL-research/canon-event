# CANON EVENT

*A recall is supposed to be a canon event. It is supposed to happen in every universe. It doesn't.*

Governments recall products for burning, choking and killing people. Nobody measures whether those
products actually leave the shelves. CANON EVENT checks whether recalled products are still buyable
right now, from three countries' residential exit IPs, and refuses to show a clean screen when its
own scraper is broken.

---

## The seed layer never touches Bright Data, and that is deliberate

CPSC and the EU Safety Gate publish free official APIs. Pointing a commercial scraping platform at
a government API to inflate a usage claim would be dishonest, and Bright Data's own acceptable use
policy excludes government sites anyway. Every recall notice in this repository was pulled from
`saferproducts.gov/RestWebServices/Recall` at zero credits.

Bright Data is used for the one thing no endpoint on earth answers:

> **Is this exact model number buyable right now, from a German residential exit IP?**

Amazon's Product Advertising API requires affiliate approval and will not answer it. eBay retired
the open Finding API. Bright Data's prebuilt library scrapers are disqualified by the hackathon
rules, so the collectors here are custom Scraper Studio collectors. **Geo is the product, not a
proxy detail.** That is the part a curl loop cannot reproduce at any price.

---

## Status, stated plainly

**This is a build in progress. Day 3 of 7.**

| Component | State |
|---|---|
| Contract, schema, design system | Complete |
| Interface, all states | Complete |
| Statistics and identifier extraction | Complete, tested |
| Structured output and validation | Complete |
| **Live collectors** | **Not built yet** |
| **Real measurements** | **Not taken yet** |
| Self-healing loop | Not built yet |

**Every number currently shown on the wall is fixture data and is stamped as such on screen.** The
recall notices, hazard sentences, model numbers, GTINs and publication dates inside those fixtures
are real and quoted verbatim from CPSC. The marketplace verdicts attached to them are not yet
measured. Nothing in this repository should be read as a finding about any product or seller until
the first live sweep replaces the fixture.

---

## Weaknesses, before anything else

A limitation named first cannot be used against you. A limitation a judge finds first is the whole
review.

**Recall is not directly measured.** We can hand-verify precision. We cannot know how many live
listings we walked straight past. Capture-recapture across our two query strategies puts a floor
under it, but the two strategies share the model token and are positively correlated, which biases
the estimate downward. **The miss count is a lower bound on our blindness, not an estimate of it.**

**Precision will not be 1.0, and false positives name real listings.** At a measured precision of
p over n published rows, roughly `(1-p)·n` rows are expected to be wrong. That is a public claim
against an identifiable listing, so the figure is printed on the wall next to the number it
qualifies, never in a footnote, and every row carries the evidence needed to contest it.

**Survival is confounded with cohort.** A recall published in 2024 is not exchangeable with one
published in 2026: enforcement, marketplace policy and product mix all changed. The survival curve
is a cross-sectional age profile, not a within-product trajectory. It answers "what share of
recalls of age *t* are still buyable today", not "what happens to a recall as it ages".

**The identifier rule was wrong, and the correction argued against us.** The original rule accepted
8 of 12 real CPSC values that are useless to search: batch codes, serial ranges, clothing sizes,
model years, package dimensions. That inflated the searchable population and so **deflated** the
unsearchable rate, against our own headline. Fixed in `extract/identifier.py`, with those 12 real
values as a regression suite.

**Border escape has no input data yet.** It compares EU-recalled products against a non-EU
marketplace, and the corpus is currently CPSC-only. The measure renders as `PENDING` with the
reason stated rather than as a number.

**eBay was cut before day one**, for time and credits. Three arms, not four.

**Coverage is 1280px and up.** Below that, columns are dropped rather than reflowed, because a
hazard ledger that reflows stops being a ledger.

---

## The correct output of a broken scraper is not an empty page

This is the whole thesis, so it is worth stating precisely.

Our output is a claim about **absence**: this product is *not* gone. When an extractor breaks and
returns zero rows, nothing throws. The wall goes empty. **An empty hazard wall does not read as
"broken", it reads as "safe".** A software bug silently becomes a clean bill of health for a
product that is still hurting people, and a row-count health check passes it happily.

So the arm never goes green and never goes empty. It goes black:

> **VERDICT WITHHELD.**
> DE collector unhealed since 14:02 UTC. We do not know, so we will not say.

Figures that the failure contaminates are struck through. Figures it does not touch stay live.
**There is no green anywhere in the interface, and the legend says so:**

> There is no green in this interface. The absence of a red row is not evidence of safety.

---

## How a claim is made, and how you check it

Each row is a government recall notice matched to a live marketplace listing. A row reaches **RED**
only when both hold at capture time:

1. The exact model number or GTIN is **re-asserted from the fetched product page itself**, not from
   the URL and not from the search result.
2. An active buy control is present on that same page.

Identity re-assertion exists because Amazon substitutes ASINs on stale URLs. Without it, a live buy
button on the *wrong* product scores as a hazard still on sale, which is the worst mistake this
system could make.

Anything matching on brand and category but lacking an exact identifier is **AMBER**: shown,
labelled unconfirmed, and excluded from every statistic. Everything else is **DISCARDED**, counted,
and reported by reason code.

**The acceptance test for a row, runnable by you with no code:** read one row aloud. If it is not a
true, sourced, dated, falsifiable claim, the row is not finished.

---

## Run it

No dependencies. No build step. Python 3 and Node, both standard library only.

```bash
git clone https://github.com/shubhL-research/canon-event
cd canon-event
./verify.sh          # regenerates fixtures, validates output, runs all four test suites
```

Then open `wall.html` directly in a browser. It reads a static JSON payload and never calls a
backend, so swap day is `cp`, not an integration.

**Every state is reachable from the address bar**, which is how the failure states get filmed:

| URL | State |
|---|---|
| `wall.html` | Base sweep. DE withheld, with a rejected heal. |
| `wall.html?state=healing` | Heal in flight, IN stale |
| `wall.html?state=gate` | Proposed template awaiting approval |
| `wall.html?state=blackout` | Implausible cleanliness fired, whole board black |
| `wall.html?state=loading` | First paint, correct geometry, no data |

---

## Example structured output

In `examples/`, generated by `examples/make_examples.py` so it can never drift from the contract:

| File | What it is |
|---|---|
| `row.json` | One finding, fully annotated, evidence chain intact |
| `MISSING.json` | A row where declared keys are **absent**, because absence is part of the contract |
| `sweep.jsonl` | The row stream, one object per line |
| `health.json` | Every detector's verdict, including the ones that concluded nothing was wrong |
| `stats.json` | Every published figure with its interval and its method |

**On MISSING.** Bright Data omits absent keys rather than nulling them. Most consumers treat that
as a parser annoyance. Here it is rendered deliberately, as a struck-through field name and the
word `MISSING`, because rendering absence as `0` converts a gap in our own measurement into a claim
about the world.

---

## The numbers, and how they are computed

Every proportion carries a **Wilson score interval**, not just the one that qualifies the others.
Wilson rather than the normal approximation because the normal interval is badly wrong exactly
where this project operates, at small *n* and proportions near 0 or 1, where it can produce a lower
bound below zero.

**Survival** is fitted as a monotone curve by isotonic regression (pool adjacent violators), with a
seeded bootstrap band. Kaplan-Meier is the wrong tool here and it is worth saying why: KM needs an
observed event or censoring time per subject. We observe each recall exactly once, at a known age,
with a binary answer. That is current-status data, and PAVA is its nonparametric MLE. No hazard
shape is assumed and no smoothing parameter is chosen. Curve points resting on fewer than five
observations are flagged `thin` and are not publishable.

**Recall floor** uses Chapman's bias-corrected capture-recapture over the two query strategies.

**Unsearchable rate** is computed entirely from the free seed layer. No scraper can contaminate it,
and it survives every collector failing.

Tests: `python3 stats/test_stats.py` and `python3 extract/test_identifier.py`. They check against
values derivable by hand, not against the code's own output.

---

## Verification

`./verify.sh` runs four suites:

- **Structured output** validated against `contract/row.schema.json` by a dependency-free checker,
  itself tested against 8 deliberate corruptions.
- **Statistics**, 26 tests. Wilson checked against published reference values, the isotonic fit
  property-tested for monotonicity across 200 random datasets.
- **Identifier extraction**, 40 tests, built as a regression suite from real CPSC values.
- **Renderer**, headless, across all five states, checking that no `undefined`, `NaN` or
  `[object Object]` reaches the page.

---

## Disclosure

**AI assistance.** This project was built with AI coding assistance (Claude). It is disclosed here
because the rules require it. The architecture, the thesis, the statistical choices and every
judgement call about what may and may not be claimed are the author's, and the code is understood
and defensible line by line. Where a model is used *inside* the product it is confined to
measurement and can never change a published number: `extract/identifier.py` runs a model as a
second opinion whose only power is to flag a case for human adjudication. The deterministic rule
always decides. Introducing a model into the RED path would destroy the falsifiability the entire
project rests on.

**Pre-hackathon work.** Planning, architecture, interface specification and corpus research were
prepared before the hackathon began, which the rules permit. All code in this repository was
written after the hackathon opened on 17 August 2026. The commit history is the evidence.

**Independence.** Not affiliated with, endorsed by, or operated by CPSC, the EU Safety Gate, Bright
Data, or any marketplace named in this repository. The interface is set in Public Sans, the US Web
Design System typeface, as a visual citation of the regulator being audited, not as a claim of
official status.

---

## Layout

```
contract/     the frozen contract: schema, states, tokens, declared keys
data/         fixture generator and the fixtures it produces
stats/        wilson · isotonic survival · capture-recapture, with tests
extract/      identifier searchability, rule primary, model second opinion
examples/     required structured output, generated
wall.html     the interface. open it directly, no server needed
validate.py   dependency-free contract checker
verify.sh     runs everything
```
