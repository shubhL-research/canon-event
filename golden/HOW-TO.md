# Hand verification: the two passes

The only number on this wall a machine cannot produce is precision. Everything
else is qualified by it. This is how it gets made.

## Before you start

```bash
python3 golden/make_worksheet.py     # writes golden/worksheet.csv, 50 rows
```

Open `worksheet.csv` in Excel or Sheets. Fill the **IN**, **COM** and **DE**
columns. Nothing else.

**Do not look at what the collector decided.** If you check a row after seeing
the machine's answer you are not measuring the machine, you are agreeing with
it. The entire value of this exercise is that it was produced independently.

## The three verdicts

Copy the value in `search_this` into the marketplace search box.

| Write | When |
|---|---|
| `RED` | You opened the **product page**, the identifier appears **on that page**, and there is a live buy control |
| `AMBER` | Looks like the right product, but the identifier is not visible on the page |
| `NOT_FOUND` | Sixty seconds elapsed |

**Sixty seconds per cell. Use a timer.** The timeout is not giving up, it is the
measurement: it is exactly what the collector gets. Giving yourself five minutes
on a hard row makes the human standard incomparable to the machine one.

Search the identifier alone first. If nothing, try brand + identifier. **Write
down the query that worked** in `query_that_worked`, because that becomes the
matcher's query strategy.

## Pass 1, rows 1 to 15: the reality check

About 45 minutes. This answers whether recalled products are findable at all
and whether the three marketplaces differ.

```bash
python3 golden/grade.py
```

It scores against the pre-registered gate and tells you which branch you are on,
so the decision is not made by whoever is most tired at the time:

- **PASS** proceed unchanged
- **PASS, IN WEAK** border escape demotes to a body statistic with its real
  small n printed, survival becomes the hero
- **MARGINAL** headline survives, widen the query strategy now, print the small n
- **FAIL** pivot to the unsearchable rate. The fallback hero sentence is already
  written in `CONTRACT-v0.9.md` section 4, so this costs zero copy time

Stop here and read the verdict before doing the other 35. If it says FAIL, the
remaining rows serve a different headline and the sample should be re-cut.

## Pass 2, rows 16 to 50: the golden set

About 90 minutes. Same method, no change.

When the collector has run a full sweep:

```bash
python3 golden/grade.py --against data/sweeps/latest.jsonl
```

That prints precision with its Wilson interval, lists every disagreement, and
separates the two error types properly:

- **machine RED, human not** is a false positive. This is precision, and it is a
  public claim against a real listing.
- **human RED, machine not** is a miss. That is recall, not precision, and it is
  bounded separately by capture-recapture. Mixing the two would flatter one and
  slander the other.

## Why the sample is not random

It is stratified: 25 with a GTIN, 7 with a prose-mined model, 18 with no
identifier at all, spread across 13 to 748 days. A random draw from this corpus
would be dominated by EU alerts carrying GTINs, which are the easy case, and the
precision figure would flatter the matcher. The strata force the hard cases in.

Rows with no identifier are there on purpose: they must **never** reach RED, and
if one does, that is a precision bug worth more than any confirmation.

## Two things this also produces, free

**The identifier effect.** `grade.py` reports the find rate split by identifier
type with intervals. If the GTIN and no-identifier intervals do not overlap,
that gap is a finding in its own right, and it is the fallback headline.

**The query strategy.** The `query_that_worked` column is the collector's future
search logic, measured rather than guessed.
