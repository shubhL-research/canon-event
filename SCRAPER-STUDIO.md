# How Bright Data Scraper Studio was used

One of the five mandatory submission items, kept as its own file so it does not
have to be hunted for inside a long README.

---

## The one question no endpoint answers

Every recall notice in this project comes from a free government API. CPSC and
the EU Safety Gate both publish openly, and pointing a paid scraping platform at
a government feed to inflate a usage claim would be dishonest. The seed layer
therefore spends zero credits, deliberately, and the README says so first.

Scraper Studio is used for the one thing nothing else can answer:

> **Is this exact identifier buyable right now, from inside this market?**

Amazon's Product Advertising API needs affiliate approval and will not answer it.
eBay retired the open Finding API. And the rules disqualify library scrapers, so
a prebuilt marketplace scraper is not an option even where one exists. What the
project needs is a custom collector per storefront, run from a controlled exit,
repairable when the page changes underneath it.

## Four collectors, all custom, all built by the AI Agent

| Arm | Storefront | Collector |
|---|---|---|
| US | `amazon.com` | `c_mt01usw31e8y5ubqjs` |
| DE | `kaufland.de` | `c_mt00jidz6zhqjbpew` |
| IN | `flipkart.com` | `c_mt03cj5z2fo651wy8q` |
| DE, earlier build | `amazon.de` | `c_mt000dde2qdd6uln7z` |

Each was created with `bdata scraper create` from a natural-language brief and
then run and repaired through the CLI:

```
bdata scraper create <url> <description>
bdata scraper run --input-file <urls>
bdata scraper heal --url <url> <prompt>
bdata scraper approve <collector_id>
```

**The AI Agent named its own fields, and that is the evidence they are custom.**
`data/sweeps/raw-row-kaufland-de.json` is one row exactly as the platform returned
it, carrying `add_to_cart_button_text`, `manufacturer_part_number`,
`availability_text` and `seller_name`. Nobody picks those names by hand. A library
scraper returns a fixed schema you did not choose, which is precisely the
distinction the rules turn on.

The storefronts were chosen because of that rule rather than in spite of it.
Bright Data's own documentation says the AI Agent works best on regional
ecommerce and that the largest marketplaces are covered by prebuilt scrapers the
rules disqualify. `kaufland.de` and `flipkart.com` are the answer to that
constraint, and the confound it creates is stated in the README rather than
hidden: three different marketplaces means country and marketplace are not
separable.

## What the platform actually did

Full corpus, three arms, one sweep. The load count is the plan the collectors
issued, not a multiplication: 180 of the 207 notices carry a searchable
identifier, and planning them produces 369 unique URLs per arm rather than a
clean 360, because a notice can yield more than two distinct queries.

```
369 unique URLs planned per arm x 3 arms  =   1,107 search page loads
US amazon.com    14,632 listings,  95 of 207 notices joined
DE kaufland.de    1,037 listings,  59 of 207 notices joined
IN flipkart.com    7,986 listings,  55 of 207 notices joined
                 ------                                    
listings adjudicated                          23,655
```

Stage one runs on the Code worker over search HTML, which is cheap and returns
tens of records per load. Escalation to the Browser worker happens only on a
block or a missing grid. The collectors are deliberately **not** chained with
`next_stage`: chaining auto-promotes every discovered listing to a product-page
load and multiplies spend by roughly forty. Promotion is decided outside Studio
by the matcher, so only candidates that could reach RED cost a browser load.

## Self-healing, including the three that were refused

Four heals were run against live collectors through `refactor_template` and three
of them were refused. Ledgers are in `heals/`, each with the verbatim prompt, the
canary result and the decision.

**DE-001, REFUSED.** The collector was built from a search URL and waited for
`.s-main-slot`, which does not exist on a product page, so every product page
failed with `wait_element_timeout`. The agent fixed exactly that. The canary gate
rejected it anyway, because the preview row showed `ean` holding
`"4.1 4.1 ud af 5 stjerner"`, a Danish review rating, and `brand` holding
`"Gå til Comfyer butikken"`, the storefront link. The repair passed the fault it
was asked about and broke two fields it was not asked about. Production template
unchanged, arm left withheld.

**US-001, REFUSED.** Same shape, different fields.

**US-002, REFUSED, and this one was verified differently.** The gate did not read
the preview row. It ran the healed template with `version=dev` and adjudicated the
output, then refused it and confirmed production was unchanged afterwards rather
than assuming it. A preview tells you what the agent thinks it produced. Running
the draft tells you what it actually produces.

**DE-002, APPROVED.**

Three refusals against one approval is not a tuning failure. The gate is
two-sided by design: a heal that makes everything match is exactly as broken as
one that matches nothing, so a repair has to satisfy the canaries that must
resolve AND the negatives that must stay dead.

There is no rollback endpoint, so verification sits **before** promotion rather
than after it. That is not a workaround: `version=dev` exists on every trigger
endpoint precisely so a draft can be run against canaries before it is promoted.

## The failure the platform's own behaviour caused, and how it was caught

A rebuilt `amazon.com` collector emitted `add_to_cart_button` where the previous
build had emitted `add_to_cart_button_text`. **The AI names its own fields, and a
rebuild from the same prompt does not have to name them the same way.**

That was not a missing column. `buy_label` was never populated on that arm, and a
row with no buy control cannot reach RED by construction, so the US arm could not
have produced a finding whatever was on the page. The schema-drift detector
counts unmapped fields rather than dropping them, so it fired on the very sweep
that introduced the drift. Mapped, and 1,810 of 2,000 sampled US rows now carry a
buy control.

Without that detector, the headline would have been a zero produced by our own
blindness and indistinguishable from a real one.

## What the platform is not asked to do

**It is never asked to decide anything.** Scraper Studio returns what a page
contains. Whether that page is the recalled product is decided afterwards, by an
exact identifier re-assertion in `collector/normalize.py`, against a matcher
proven in both directions: 13 positive controls that must all reach RED, and 21
adversarial near-misses that must all be discarded.

**It is never pointed at a government site.** Bright Data's acceptable use policy
excludes them, and the seed layer has no need of it.

**Price is never recorded.** Only the currency symbol, as a country-drift check.

## Reproducing this

```
python3 data/pull_seeds.py        # both regulators, zero credits
python3 collector/sweep.py        # the collectors, live
python3 collector/publish.py      # sweep output to the wall payload
./verify.sh                       # 13 suites, no dependencies
```

Raw platform output is committed in `data/sweeps/`, including per-sweep health
files, so the adjudication can be re-derived without re-running a single request.
