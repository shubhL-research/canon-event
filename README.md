# CANON EVENT

*A recall is supposed to be a canon event. It is supposed to happen in every universe. It doesn't.*

Governments recall products for burning, choking and killing people. Nobody measures whether those
products actually leave the shelves. CANON EVENT checks whether recalled products are still buyable
right now, from geo-accurate exit IPs in three markets, and refuses to show a clean screen when its
own scraper is broken. One trial sweep has run, over 60 of 207 notices and two of the three arms.
Nothing here has been swept at full scale, and the numbers say so on their face.

---

## The strongest claim in this repository, and how to check it yourself

**The US recall API has a model-number field. It is empty on every record.**

CPSC publishes `Products[].Model` in its official REST feed. Across the four date windows this
corpus draws from, that field is empty on **213 of 213 product records**. Not sparse. Empty. The
model number is in the same JSON response, written in prose into the top-level `Description`, which
is non-empty on all 213. A structured barcode reaches `ProductUPCs` on 7 of the 213.

Run this and read the two numbers. The first is product records returned, the second is product
records whose `Model` is empty.

```bash
curl -s "https://www.saferproducts.gov/RestWebServices/Recall?format=json&RecallDateStart=2026-06-28&RecallDateEnd=2026-08-11" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); p=[x for e in r for x in e['Products']]; print(len(p), sum(1 for x in p if not x['Model'].strip()))"
```

```
72 72
```

The other three windows are the same command with the dates swapped:

| Window | Recalls | Product records | `Model` empty |
|---|---|---|---|
| 2026-06-28 to 2026-08-11 | 72 | 72 | 72 |
| 2026-04-29 to 2026-06-12 | 81 | 81 | 81 |
| 2025-07-28 to 2025-09-10 | 35 | 35 | 35 |
| 2024-07-28 to 2024-09-10 | 25 | 25 | 25 |
| **Total** | **213** | **213** | **213** |

The EU does the opposite. Every one of the 104 Safety Gate alerts in this corpus carries a typed
barcode in `product_barcode`. Six of those 104 fail their own check digit and are refused, which the
weaknesses section takes up. The field is populated on all 104 EU alerts. The equivalent US field is
populated on none of the 213.

That 104 of 104 is partly our own selection, because the seed puller prefers alerts carrying a
barcode, so here is the unselected figure instead: across the whole EU population in the same four
windows, **1,072 of 1,737 sampled alerts carry a barcode, 61.7%**.

```bash
curl -s "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/healthref-europe-rapex-en/records?limit=100&select=product_barcode&where=alert_date%3E%3D%272026-06-28%27%20AND%20alert_date%3C%3D%272026-08-11%27" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['results']; print(len(r), sum(1 for x in r if (x['product_barcode'] or '').strip()))"
```

```
100 43
```

So a machine-readable model number reaches the US feed 0% of the time, a machine-readable barcode
reaches it on 7 of 213 records, and the EU barcode field is filled about 62% of the time. That is a
claim about record format, not about any seller, and it is the one claim here that needs no scraper,
no sample and no trust. It also survives every collector in this repository failing at once.

**Counts move, the zero does not.** The figure recorded when this corpus was pulled on 19 August was
183 of 183. Re-checked on 20 August it is 213 of 213, because CPSC kept publishing. The denominator
grows with every recall. The number of exceptions has never moved off zero.

---

## What has actually been measured

One trial sweep, 19 August 2026. **60 of 207 notices, two of the three arms.**

| | |
|---|---|
| Notices swept | 60 of 207, all of them Safety Gate. **No CPSC notice has been swept yet** |
| Arms swept | US `amazon.com` DEGRADED, DE `kaufland.de` MEASURED, IN `flipkart.com` MEASURED |
| Listings adjudicated | 16,025. US 6,886, DE 1,066, IN 8,073 |
| Notices that got any candidate at all | US 33, DE 58, IN 56, of 60 queried per arm |
| Listings discarded | 16,025, every one |
| Rows reaching RED | 0, across all 180 notice-arm pairs |
| Still buyable | 0 of 58 searchable notices, Wilson 95% CI [0, 6.2] |
| Precision | not computed, and cannot be. There are no RED rows to hand-verify |
| Border escape | pending. Scored against swept seeds only, and the swept set is entirely EU |
| Credits spent | not carried in this payload. The figure is on the collector account, not in the sweep output, so it is not stated rather than estimated |

**The corpus could barely have produced a hit on two of the three arms, and that
has to be said before anyone else says it.** Every notice in this sweep is an EU
Safety Gate alert: Danish fireworks, a French whisk, a Polish slime doll, an
Italian nail varnish. Those were searched on `amazon.com` and `flipkart.com`,
where European regional retail stock is not listed in the first place. A null
result there is closer to a statement about distribution than about recall
enforcement.

The DE arm is the only one where the question was posed fairly, and it returned
1,066 listings, joined 58 of 60 notices to candidates, and confirmed none of
them. That is the honest scope of the finding: **on one European storefront, no
searchable EU-recalled product was confirmed still buyable.**

The next sweep points CPSC notices at `amazon.com`, which is the pairing where a
hit is physically possible. Until that runs, the null result should be read
narrowly.

The payload the wall reads is `data/live.js`. It stamps itself:

```
fixture   false
stamp     LIVE MEASUREMENT. TRIAL SLICE, 60 of 207 notices.
          Denominators are not the full corpus.
```

Two earlier sweeps are archived beside it, at 3 notices and 30 notices, with all three arms WITHHELD.
Four payloads are committed at `data/live-s_*.json`, and three of the four measured nothing. They are
kept because a sweep that came back empty is the state this interface exists to render honestly.

**The published adjudication is a replay.** The fetches happened live on 19 August against real
marketplaces from geo-accurate exit IPs, and the raw rows were archived on receipt. The matcher then
changed, so those archived rows were re-scored offline through the current rules. No new fetch and
no new credits, and the sweep id ends in `-replay` so it cannot be passed off as a fresh capture.

The five fixture states remain reachable at `wall.html?state=...` for filming the failure modes.
They are stamped `fixture: true` and their RED rows are illustrative. Nothing in a fixture is a
finding about any product or seller.

---

## Weaknesses, before anything else

A limitation named first cannot be used against you. A limitation a judge finds first is the whole
review.

### The unsearchable rate was wrong, and here is the correction

This was the headline number on the wall. It said **96.1% of US recall notices name nothing a machine
can search for. The true figure is 20.4%.**

`data/pull_seeds.py` read two things when it looked for a US model number: `Products[].Model`, and
the product name. `Products[].Model` is empty on every CPSC record, as the section above
demonstrates, so a model number only ever arrived when it happened to appear in the product name. The
puller never opened the top-level `Description`, which arrives in the same JSON response and names
the model in prose: `model YJ MGC 5x5`, `SKU WMEDX-FC-TVK9CDC-RT`.

**What it cost.** The wall said 96 of 207 recall notices name nothing a machine can search for. That
was a measurement of our own parser presented as a measurement of the regulator.

```
US CPSC     was 96.1% (99/103)   ->   now 20.4% (21/103)
EU          0.0% (0/104) by the identifier rule, untouched by this bug.
            5.8% (6/104) once the six invalid barcodes below are refused
pooled      was 46.4% (96/207) CI [39.7, 53.2]
            now 10.1% (21/207) CI [6.7, 15.0], or 13.0% (27/207) counting
            those six as unsearchable
```

The intervals do not overlap. This was not a rounding difference, it was a different claim.

The pooled figure is given two ways because the two rules that can produce it disagree by six
notices, and picking the flattering one silently is the same class of error as the bug above. The
figure to read is the US one. The next weakness explains why the pooled one should not be read at
all.

**How it was found.** By checking the headline against the raw feed before publishing it, because it
was the headline. A rate saying CPSC names nothing searchable in 96 of every 100 notices is an
accusation against a regulator, and an accusation that size is worth four minutes with curl. The four
minutes found the identifier sitting in a key we had never opened. Nothing else in this repository
would have caught it, because every test agreed with the parser.

The correction cuts both ways and both are stated. It removed a headline. It also moved 77 CPSC
notices from unsweepable to sweepable, so US recalls can enter a sweep for the first time. The fix
mines `Description` and `Title` through a cue-word rule and gates every recovery through
`extract.identifier.classify()`, the same rule the wall publishes, so coverage can widen but no
identifier can be invented. Commit `b5237d9`.

### The corpus is not a random sample, so no pooled rate is a property of the world

`pull_seeds.py` sets `TARGET_PER_BAND = 26` and keeps the top-scoring 26 notices per regulator per
age band. That forces a roughly even split, **103 US against 104 EU**, out of populations that are
nothing like even:

| Window | CPSC recalls available | EU alerts available |
|---|---|---|
| 2026-06-28 to 2026-08-11 | 72 | 186 |
| 2026-04-29 to 2026-06-12 | 81 | 519 |
| 2025-07-28 to 2025-09-10 | 35 | 432 |
| 2024-07-28 to 2024-09-10 | 25 | 611 |
| **Total** | **213** | **1,748** |

The EU publishes roughly eight alerts for every CPSC recall in these windows, and this corpus draws
them one for one. Selection inside a band is not random either: the scorer prefers notices carrying
an identifier, which is exactly the variable the unsearchable rate measures.

**So a pooled rate across the two regulators is a property of our sampling frame, not of the world.**
The pooled figure above is reported only as the arithmetic of this corpus. The figures that mean
something are the by-authority ones, US 20.4% against an EU rate between 0.0% and 5.8%, and that
split is shown wherever the pooled number appears. Any comparison that averages the two regulators together describes this file
and nothing more.

### Survival is 0 of 58, from 60 of 207 notices on two of three arms

Zero listings reached RED. That is a real measurement and it is reported as one, with a Wilson
interval of [0, 6.2] rather than as a bare zero, because 58 observations cannot exclude a survival
rate of 6%.

What it is not: it is not a sweep of the corpus. 60 of 207 notices were queried, all of them Safety
Gate, so no US recall has been tested at all. Two arms of three ran, and one of those two came back
DEGRADED. **A degraded arm makes the zero a floor rather than an estimate.** A listing that arm
failed to match could exist. The wall labels the figure partial for that reason and does not round it
up into a claim that recalls work.

### Precision is not computed at all

Precision needs RED rows to hand-verify, and there are no RED rows. The figure reads `PENDING` on the
wall with the count needed printed beside it, 0 of 50 adjudicated, and the worksheet that will
produce it is in `golden/`. It is not estimated from the sweep, not inherited from the fixtures, and
not quoted from the adversarial set.

The adversarial set is a different measurement and is labelled as one. 21 deliberately confusable
near-misses, adjacent GTINs, successor SKUs, truncated identifiers and superstring traps, are fed to
the matcher and all 21 must land in DISCARDED. They do. That demonstrates the matcher refuses known
traps. It is not a precision figure, because we chose the inputs.

### Recall is not directly measured

We can hand-verify precision once there are rows. We cannot know how many live listings we walked
straight past. Capture-recapture across our two query strategies puts a floor under it, but the two
strategies share the model token and are positively correlated, which biases the estimate downward.
**The miss count is a lower bound on our blindness, not an estimate of it.** With an overlap below 3
the estimator is too unstable to publish at all, which is the present state, so the raw counts are
printed and recall is reported as unmeasured.

### The three arms are three different marketplaces, so country and marketplace are confounded

The arms are `kaufland.de` for Germany, `amazon.com` for the United States and `flipkart.com` for
India. Three countries, three different storefronts. **A cross-arm difference cannot be attributed to
geography, because the marketplace changes at the same time as the country.** No such comparison is
published, and if one ever is it carries this sentence next to it.

The within-country measure is unaffected: is this recalled product buyable in this market, right now.
That is the measure the headline makes.

Why the arms are three different marketplaces is worth stating. Bright Data's own documentation says
the AI Agent works best on regional ecommerce, and the large marketplaces are covered by pre-built
library scrapers that the competition rules disqualify. `amazon.de` needed two heals before it would
open a product page, and `amazon.com` cost a third heal cycle that turned out to be diagnosing our
own query bug. `kaufland.de` and `flipkart.com` built clean on the first attempt and are the two arms
that produced rows.

### Survival is confounded with cohort

A recall published in 2024 is not exchangeable with one published in 2026: enforcement, marketplace
policy and product mix all changed. The survival curve is a cross-sectional age profile, not a
within-product trajectory. It answers "what share of recalls of age *t* are still buyable today", not
"what happens to a recall as it ages".

### The identifier rule was wrong once before, and that correction also argued against us

The original rule accepted 8 of 12 real CPSC values that are useless to search: batch codes, serial
ranges, clothing sizes, model years, package dimensions. That inflated the searchable population and
so deflated the unsearchable rate, against our own headline. Fixed in `extract/identifier.py`, with
those 12 real values kept as a regression suite.

### Six of the Safety Gate barcodes are not barcodes

Of the 104 EU notices carrying a `gtin`, six hold a value that fails its own modulo-10 check digit,
at lengths 9, 10, 12 and 14. The notifying country types into a free-text box. They are refused as
unassertable rather than matched, because a ten-digit number searched against a retail page is a
false accusation waiting to happen.

They are the difference between the two EU figures above. Counting them as identifiers would put the
EU unsearchable rate at 0.0%, which is the flattering direction for a document that spends its lead
section on how much better the EU record format is. Refusing them puts it at 5.8%, and that is the
number the check digit supports.

### Currency does not prove which country answered, and we assumed it did

The plan rested on the storefront's currency symbol as the in-page attestation of the exit market. A
heal preview on 19 August returned a fully Danish page from `amazon.de`, "På lager", "Tilføj til
indkøbskurv", quoting EUR. The currency was correct and the market was not, because `amazon.de`
quotes EUR to every visitor from every exit. **A currency check cannot separate a German session from
a Danish one, and the entire cross-market comparison rests on that separation.** Page language is now
the attestation and currency is corroboration. The collectors emit `page_language` from the page's
own `lang` attribute. The buy-control check happened to catch this case because the Danish label is
not in the German list, but luck is not a control. Written up in `heals/2026-08-19-de-001.md`, which
is a refusal rather than a repair.

### Smaller ones, stated anyway

**eBay was cut before day one**, for time and credits. Three arms, not four.

**Coverage is 1280px and up.** Below that, columns are dropped rather than reflowed, because a hazard
ledger that reflows stops being a ledger.

---

## The correct output of a broken scraper is not an empty page

This is the whole thesis, so it is worth stating precisely.

Our output is a claim about **absence**: this product is *not* gone. When an extractor breaks and
returns zero rows, nothing throws. The wall goes empty. **An empty hazard wall does not read as
"broken", it reads as "safe".** A software bug silently becomes a clean bill of health for a product
that is still hurting people, and a row-count health check passes it happily.

So the arm never goes green and never goes empty. It goes black:

> **VERDICT WITHHELD.**
> DE collector unhealed since 14:02 UTC. We do not know, so we will not say.

Figures that the failure contaminates are struck through. Figures it does not touch stay live.
**There is no green anywhere in the interface, and the legend says so:**

> There is no green in this interface. The absence of a red row is not evidence of safety.

That distinction is doing work in the current sweep. The DE arm returned listings and matched none of
them, which is a measurement, so survival stays live at 0 of 58. The IN arm's join-key coverage fell
below its bound, which is a failure of ours, so border escape is withheld rather than reported as a
zero. The two look identical in a row count and are opposite in meaning.

---

## The seed layer never touches Bright Data, and that is deliberate

CPSC and the EU Safety Gate publish free official APIs. Pointing a commercial scraping platform at a
government API to inflate a usage claim would be dishonest, and Bright Data's own acceptable use
policy excludes government sites anyway. Every recall notice in this repository was pulled from
`saferproducts.gov/RestWebServices/Recall` and the Safety Gate open-data mirror at zero credits.

The EU half reads the Opendatasoft mirror rather than the official portal, because
`ec.europa.eu/safety-gate-alerts` is JavaScript rendered with no documented public JSON API. Every EU
seed carries its official alert URL, so any single row can be walked back to the primary source by
hand. That dependency is disclosed here rather than hidden.

Bright Data is used for the one thing no endpoint on earth answers:

> **Is this exact model number buyable right now, from inside the German market?**

Amazon's Product Advertising API requires affiliate approval and will not answer it. eBay retired the
open Finding API. Bright Data's prebuilt library scrapers are disqualified by the hackathon rules, so
the collectors here are custom Scraper Studio collectors. **Geo is the product, not a proxy detail.**
That is the part a curl loop cannot reproduce at any price.

---

## How a claim is made, and how you check it

Each row is a government recall notice matched to a live marketplace listing. A row reaches **RED**
only when both hold at capture time:

1. The exact model number or GTIN is **re-asserted from the fetched product page itself**, not from
   the URL and not from the search result.
2. An active buy control is present on that same page.

Identity re-assertion exists because Amazon substitutes ASINs on stale URLs. Without it, a live buy
button on the *wrong* product scores as a hazard still on sale, which is the worst mistake this
system could make. It is the entire reason 16,025 listings were discarded in the current sweep: the
recalled identifier was never re-asserted on the page that came back.

A model string alone does not settle identity either. Model numbers are not globally unique, so a
page carrying the right model under a different manufacturer is capped at AMBER. That guard is
deliberately not applied when the identifier is a valid GTIN, because GTINs are globally unique and a
reseller's name in the brand slot is not a conflict.

Anything matching on brand and category but lacking an exact identifier is **AMBER**: shown, labelled
unconfirmed, and excluded from every statistic. Everything else is **DISCARDED**, counted, and
reported by reason code.

**The acceptance test for a row, runnable by you with no code:** read one row aloud. If it is not a
true, sourced, dated, falsifiable claim, the row is not finished.

---

## How Bright Data Scraper Studio is used

Every collector here is custom, built through Scraper Studio's AI Agent from a natural-language
description. None is a library scraper. The seed layer deliberately never touches the platform, for
the reason above, so **every credit spent is spent on the one question no free endpoint answers.**

```
c_mt00jidz6zhqjbpew   DE   kaufland.de    built clean, swept, MEASURED
c_mt03cj5z2fo651wy8q  IN   flipkart.com   built clean, swept, MEASURED
c_mt01usw31e8y5ubqjs  US   amazon.com     built, one refused heal, not in the trial slice
c_mt000dde2qdd6uln7z  DE   amazon.de      healed twice and approved, held out of the arms
```

`amazon.de` is held separately on purpose. It is a second German storefront, not a fourth arm, and
the DE arm publishes kaufland rows only. Running both into one arm would double-count German
listings. It stays in the repository because it is where the heal loop was exercised hardest.

Four commands, in the order the project actually used them:

```bash
bdata scraper create <search-url> "<fields to extract>"   # AI builds the collector
bdata scraper run    <collector_id> <url> --json          # sweep
bdata scraper heal   <collector_id> "<what broke>" --url  # repair, stops at a gate
bdata scraper approve <collector_id> [--reject]           # promote, or refuse
```

**Geo comes from the Search scraper type**, which takes a keyword and a country, not from a CLI flag.
There is no `--country`. That matters because it means the country we requested lives in our own
configuration, and a config file is not evidence. See the currency weakness above: the page's own
`lang` attribute is the attestation.

### Three heals, two of them refused

All three are on real breaks that nobody staged. They are in `heals/`, written up in full.

`amazon.de` was built from a search URL, so it waited for `.s-main-slot`, the search-results grid, on
every page it was given. Product pages do not have one, so every product page died on a thirty-second
timeout. Since identity re-assertion is only valid against the product page itself, an arm that
cannot open one cannot make a RED claim at all.

**DE-001 fixed exactly that, and was refused anyway.** The repair worked. The canary caught two
things the prompt had not asked about: `ean` came back holding the review star rating, and `brand`
came back holding the visit-the-store link. Approving it would have restored the arm to working order
while filling the GTIN field with review furniture. An arm that looks healthier than before and is
less trustworthy than before is the exact outcome a two-sided gate exists to prevent. Production
template unchanged, arm stayed withheld.

**DE-002 was written against those three defects and approved, 3 of 3 canaries.** Same collector id
across both, nothing downstream touched, which is the property that made refusing the first one cheap
enough to be worth doing.

**US-001 was refused for a different reason: the diagnosis was wrong.** The `amazon.com` collector
was timing out on a search selector and the heal was written against that. The break was our own
query, not the collector. The heal file carries the correction at the end rather than being deleted,
because a repair ledger that keeps only its successes is not a ledger.

### What the platform's output actually looks like

`collector/fromstudio.py` is the only module allowed to know Bright Data's field names, because the
AI names its own fields and they differ per collector. Two things it handles that a naive reader
would not:

- **Absent keys are omitted, not nulled.** Preserved all the way to the screen as `MISSING`.
- **Identifiers came back doubled.** 25 of 28 real `kaufland.de` rows returned
  `"8721003407246 8721003407246"`, 26 digits, which fails its own check digit and throws away a
  usable barcode. Exact repeats are collapsed and counted. All 28 repaired EANs validate, which is
  the evidence the repair is right rather than merely convenient.

---

## Six of the exits are not what we said they were

`data/attest/exit-attestation-2026-08-20.json` holds three requests to
`brdtest.com/myip.json`, one per market. All three resolve to the country asked
for, with a matching timezone. Geo targeting works, and it is the capability the
three-arm design rests on.

It also refuted our own wording. Every ASN belongs to a hosting company:

```
US   AS20473    The Constant Company, LLC      Piscataway, New Jersey
DE   AS203020   HostRoyale Technologies        Berlin
IN   AS133499   HostRoyale Technologies        Asia/Kolkata
```

A residential exit names a carrier: Vodafone, Comcast, Reliance Jio. This
project's own standard, written on the wall, is that an ASN naming a consumer
ISP rather than a datacentre is the proof. By that standard these are not
residential, so the README no longer says residential. It says geo-accurate,
which is what was measured.

Two limits on what the file shows, both stated in it. It was measured through
the CLI's default unlocker zone rather than from inside a collector session, so
it neither confirms nor refutes the collectors' own exit type. And nothing can,
until a collector issues an attestation request in the same stage as its product
fetch. **The collectors do not currently do that**, which is why every arm on the
wall reads "exit not attested on this sweep" rather than showing a chip.

That is the largest open gap in this repository and it is named here rather than
left for a reader to find.

## Who this is for, and what it asks for

A measurement with no addressee is a curiosity. This one has both.

**The finding, in one sentence.** CPSC publishes a `Products[].Model` field and it
is empty on 183 of 183 product records across four date windows. The model number
exists: it is written in English prose in the `Description` instead. Every one of
104 EU Safety Gate alerts carries a typed barcode in its own field.

**The ask, addressed to CPSC.** Populate `Products[].Model`, or add a `ProductGTIN`
field alongside the existing `ProductUPCs`. The data is already being written, in
the same JSON response, one key away. Nothing new has to be collected.

**Who that helps.** Anyone trying to check a recall programmatically: a
marketplace running its own listings against the recall feed, a journalist asking
whether a specific product is still on sale, a customs authority, a comparison
site, and the regulator itself. Right now every one of them has to parse English
prose to find out which unit was recalled. We wrote that parser, it is in
`data/pull_seeds.py`, and it recovered an identifier for 82 of 103 US notices that
the structured field did not carry. Nobody should have to write it.

**What we are handing over.** Everything a reader needs to check this or build on
it, in `data/sweeps/` and `examples/`:

| | |
|---|---|
| `sweep-2026-08-20.csv` | Every notice-arm verdict, one row each |
| `s_*.jsonl` | Raw sweep rows |
| `s_*-health.json` | What every detector concluded, per sweep |
| `examples/` | The structured output shape, with its schema |

All of it is plain CSV, JSONL and JSON, served over HTTPS from the live link. No
key, no signup, no rate limit.

**What we are not claiming.** Nothing here says any product is on sale. Nothing
here names a seller. The one number this project would stake itself on is a count
of an empty field in a public feed, and it is reproducible with one curl command:

```
curl -s "https://www.saferproducts.gov/RestWebServices/Recall?format=json&RecallDateStart=2026-07-20&RecallDateEnd=2026-08-13"   | python3 -c "import json,sys; d=json.load(sys.stdin);     print(sum(1 for r in d for p in r['Products'] if not (p.get('Model') or '').strip()),           'of', sum(len(r['Products']) for r in d))"
```

See also `SCRAPER-STUDIO.md`, the written explanation of how the platform was
used, kept as its own file because it is one of the five mandatory items.

## The primary evidence

`data/sweeps/` is committed, not ignored. It holds the two things a reader needs
to check the claim rather than take it:

| File | What it is |
|---|---|
| `raw-row-kaufland-de.json` | One row exactly as Scraper Studio returned it, field names and all |
| `sweep-2026-08-20.csv` | The full three-arm sweep after adjudication, 180 notice-arm verdicts |

The field names in the raw row were chosen by the Scraper Studio AI Agent when it
built the collector from a natural-language brief. `add_to_cart_button_text` and
`manufacturer_part_number` are not names we would have picked, and a library
scraper would have returned a fixed schema we did not choose. That is the
difference the rules turn on.

Read the two together and the matcher is the distance between them. Three things
are visible in the raw row and nowhere else: values arrive doubled, so
`8721003407246 8721003407246` fails its own check digit until `collapse_repeat()`
runs; the brand field holds a part number; and the notice was a Besrey stroller
while the page returned a MamaLoes buggy from a reseller, barcode matching and
brand not, which is exactly the case `brand_conflict()` is written to allow
rather than reject.

## Run it

No dependencies. No build step. Python 3 and Node, both standard library only.

```bash
git clone https://github.com/shubhL-research/canon-event
cd canon-event
./verify.sh          # regenerates fixtures, validates output, runs ten suites
```

Then open `wall.html` directly in a browser. It reads a static JSON payload and never calls a
backend, so swap day is `cp`, not an integration.

**Every state is reachable from the address bar**, which is how the failure states get filmed. The
bare URL is the live trial sweep. Everything carrying a `state=` parameter is fixture data and says
so on screen.

| URL | State |
|---|---|
| `wall.html` | **Live.** Trial sweep, 60 of 207 notices, DE measured, IN degraded, zero RED |
| `wall.html?state=v1` | Fixture. Base sweep, DE withheld, with a rejected heal |
| `wall.html?state=healing` | Fixture. Heal in flight, IN stale |
| `wall.html?state=gate` | Fixture. Proposed template awaiting approval |
| `wall.html?state=blackout` | Fixture. Implausible cleanliness fired, whole board black |
| `wall.html?state=loading` | First paint, correct geometry, no data |

To re-run a sweep without spending a credit, `collector/sweep.py --from-raw` re-adjudicates the
archived raw rows through the current matcher. `--dry-run` prints the plan and the exact credit cost
before anything is fetched.

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

**On MISSING.** Bright Data omits absent keys rather than nulling them. Most consumers treat that as
a parser annoyance. Here it is rendered deliberately, as a struck-through field name and the word
`MISSING`, because rendering absence as `0` converts a gap in our own measurement into a claim about
the world.

---

## The numbers, and how they are computed

Every proportion carries a **Wilson score interval**, not just the one that qualifies the others.
Wilson rather than the normal approximation because the normal interval is badly wrong exactly where
this project operates, at small *n* and proportions near 0 or 1, where it can produce a lower bound
below zero.

**Survival** is fitted as a monotone curve by isotonic regression (pool adjacent violators), with a
seeded bootstrap band. Kaplan-Meier is the wrong tool here and it is worth saying why: KM needs an
observed event or censoring time per subject. We observe each recall exactly once, at a known age,
with a binary answer. That is current-status data, and PAVA is its nonparametric MLE. No hazard shape
is assumed and no smoothing parameter is chosen. Curve points resting on fewer than five observations
are flagged `thin` and are not publishable, which at present is every point on the curve.

**Recall floor** uses Chapman's bias-corrected capture-recapture over the two query strategies. It is
currently below the overlap at which that estimator is stable, so it is not published.

**Unsearchable rate** is computed entirely from the free seed layer. No scraper can contaminate it,
and it survives every collector failing. It is the figure the wall falls back to for its headline
when no listing reaches RED, which is the present state.

**Denominators exclude what we could not look for.** Survival is scored over searchable notices only.
Scoring an unsearchable notice as not-buyable would convert our own blindness into evidence of
safety, which is the failure this project exists to refuse.

---

## Verification

`./verify.sh` runs ten suites, in about five seconds, from a clean clone.

| Suite | What it checks |
|---|---|
| Fixture regeneration | Fixtures rebuilt from real CPSC notices, never hand-edited |
| Structured output | 828 rows across four fixtures validated against `contract/row.schema.json` by a dependency-free checker, itself tested against 8 deliberate corruptions |
| Statistics | 31 checks. Wilson against published reference values, the isotonic fit property-tested for monotonicity across 200 random datasets |
| Example output | `examples/` regenerated from the contract so it cannot drift |
| Identifier extraction | 49 checks, built as a regression suite from real CPSC values |
| Collector normalizer | 83 checks: doubled identifiers, check digits, page language, absent keys |
| Adversarial precision set | 21 deliberately confusable near-misses. Any one reaching RED blocks the freeze |
| Sweep | 76 checks over the adapter, arm combination and detectors, all offline |
| Hand-verification worksheet | Grades whatever has been adjudicated by hand, and says so when nothing has |
| Wall renderer | Headless, across the live payload and all five states, checking that no `undefined`, `NaN` or `[object Object]` reaches the page |

The tests check against values derivable by hand, not against the code's own output.

---

## Disclosure

**AI assistance.** This project was built with AI coding assistance (Claude). It is disclosed here
because the rules require it. The architecture, the thesis, the statistical choices and every
judgement call about what may and may not be claimed are the author's, and the code is understood and
defensible line by line. Where a model is used *inside* the product it is confined to measurement and
can never change a published number: `extract/identifier.py` runs a model as a second opinion whose
only power is to flag a case for human adjudication. The deterministic rule always decides.
Introducing a model into the RED path would destroy the falsifiability the entire project rests on.

**Pre-hackathon work.** Planning, architecture, interface specification and corpus research were
prepared before the hackathon began, which the rules permit. All code in this repository was written
after the hackathon opened on 17 August 2026. The commit history is the evidence.

**Independence.** Not affiliated with, endorsed by, or operated by CPSC, the EU Safety Gate, Bright
Data, or any marketplace named in this repository. The interface is set in Public Sans, the US Web
Design System typeface, as a visual citation of the regulator being audited, not as a claim of
official status.

---

## Layout

```
contract/     the frozen contract: schema, states, tokens, declared keys
data/         seed puller, fixtures, and every live sweep this project has run
stats/        wilson, isotonic survival, capture-recapture, with tests
extract/      identifier searchability, rule primary, model second opinion
collector/    adapter, normalizer, sweep, health detectors, publisher
golden/       the hand-verification worksheet precision will come from
heals/        three real heals: two refused, one approved
examples/     required structured output, generated
wall.html     the interface. open it directly, no server needed
validate.py   dependency-free contract checker
verify.sh     runs everything
```
