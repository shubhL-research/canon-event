# Collector contract

Everything the collector has to do, and nothing it doesn't.

**You emit flat rows. `normalize.py` turns them into contract rows.** You never
read `row.schema.json`, never decide RED versus AMBER, never compute a statistic.
If a field below is hard to get, omit it: an omitted key is a legitimate,
handled state. Guessing a value is not.

---

## Emit these fields

| Field | Notes |
|---|---|
| `seed_ref` | **Required.** The recall reference, passed in as collector input. Without it the row is orphaned. |
| `arm` | **Required.** `US` \| `DE` \| `IN` |
| `query_kind` | **Required.** `brand_model` \| `model_only`. See the warning below. |
| `needle` | The identifier searched for (GTIN or model) |
| `url` | The product page actually fetched |
| `http_status` | |
| `captured_at` | ISO 8601 with `Z` |
| `page_text` | Text of the fetched product page. Used for identity re-assertion. |
| `dom_path` | Where the needle was found |
| `buy_label` | The marketplace's own words, in its own language. `In den Einkaufswagen`, not a translation. |
| `in_stock` | |
| `ships_from` | |
| `currency` | `EUR` \| `USD` \| `INR`. **Symbol only. Never a price value.** |
| `sha256` | Hash of the captured HTML |
| `trace` | Pairs with `embed_html_comment()` |
| `job_id` | |
| `error` | A Bright Data error code, if the input failed |
| `warning` | |

Test your output before spending credits on a full sweep:

```bash
python3 collector/test_normalize.py
```

---

## The four things that will cost us the week if missed

### 1. `query_kind` on every single hit

Two queries run per recall per arm: brand+model, then model alone. **Record
which one found it.** Those are the two capture occasions in the Chapman
estimator, and they are the only reason we can say "we missed at least N
listings" instead of "recall is unmeasured".

If the first sweep goes out without `query_kind`, the recall floor is
unrecoverable for the rest of the week. It cannot be reconstructed afterwards.

### 2. Never fabricate a missing value

Bright Data omits absent keys rather than nulling them, and that is handled all
the way to the screen, where it renders as a struck field name and the word
`MISSING`. Filling a gap with `""`, `0` or `"unknown"` converts a hole in our
measurement into a claim about the world. Omit the key.

### 3. `page_text` must come from the FETCHED page

Identity re-assertion is the load-bearing check in the project. Amazon
substitutes ASINs on stale URLs, so a live buy control on the *wrong* product
would score as a hazard still on sale, which is the worst mistake this system
can make. The identifier has to reappear in the page's own text. A match against
the URL or the search result does not count.

Matching is already case- and separator-insensitive, so `ps 1000` satisfies
`PS-1000`. You do not need to normalise anything.

### 4. Currency, never price

`hackathon.md` keeps us clear of the organisers' own price-intelligence idea, so
no price value is ever recorded or displayed. The currency symbol alone is the
fingerprint detector: every DE row EUR, every IN row INR, every US row USD. One
line of code that kills an entire country-drift failure class which cross-arm
comparison is structurally blind to.

---

## Platform notes worth knowing before you burn credits

- **Worker per stage.** Stage 1 on search HTML uses the **Code worker**: cheap,
  and one page load returns 30 to 60 records. Escalate to the **Browser worker**
  only on `blocked()` or a missing grid.
- **Do not chain with `next_stage`.** Chaining auto-promotes every discovered
  listing to a product-page load and multiplies credits by roughly forty.
  Promotion is decided outside Studio by the matcher, so only RED candidates
  cost a browser load.
- **Every `request()` is billable**, including the exit-IP probe. Attest **once
  per arm per sweep**, not per row.
- **Triggering is not idempotent** and does not dedupe. Every naive retry doubles
  spend. Use `get-errors-for-job` and retry only the failed inputs.
- **Snapshots expire after 16 days** and are unrecoverable. An empty result often
  means expiry, not zero rows. Persist every row to `data/sweeps/*.jsonl` on
  receipt.
- **16MB per-session accumulation cap.** Never compute detection features on raw
  HTML inside the scraper, and never put screenshots inside rows.
- **Never re-run `create` to fix a broken scraper.** It builds a new collector and
  orphans the old one. Use heal, which preserves the id.
- **`blocked` and `block` are different events.** `blocked` means our own code
  called `blocked()`; `block` is the fetch layer. The wall reports them
  separately, so don't collapse them.
- **`version=dev` exists on every trigger endpoint.** Run the healed draft
  against the canaries before promoting. Verification before promotion is the
  documented happy path, not a workaround.
- **Max 3 concurrent AI-flow jobs.** We cap at 2. A heal can take up to 15
  minutes and the CLI's default 600s poll timeout is shorter than that.

---

## Exit attestation

One `request('https://brdtest.com/myip.json')` per arm per sweep, emitting
`exit_ip`, `exit_country`, `asn_org`, `city`, `tz`.

**Geo is the product, not a proxy detail.** A config file claiming `de` is
unfalsifiable. An ASN reading `Vodafone GmbH` rather than a datacentre, captured
at the same timestamp as the buy control and next to the page's own EUR price,
is proof. Cross-check it against the page's own currency and delivery-location
string.

Open question for day one: does the attestation request share an exit IP with
the product fetch in the same stage? `preserve_proxy_session()` is documented as
reusing the session across child stages, but sharing within a single stage is an
inference. Test it. If it does not hold, attest per stage and say so on the wall.

---

## Corpus

`data/seeds.json`, **207 notices**, US CPSC and EU Safety Gate, spanning 13 to
748 days old. Regenerate with `python3 data/pull_seeds.py`. Zero Bright Data
credits: the seed layer never touches the platform, deliberately, and the README
says so in its first paragraph.

**Start with the EU seeds.** All 104 carry a GTIN, so the matcher has an exact
identifier to work with. Only about 4% of the US notices expose one, so
`amazon_de` and `amazon_in` will produce findings long before `amazon_com` does.

Budget: 207 seeds x 2 queries x 3 arms = 1,242 search loads, plus a product-page
load per RED candidate. Roughly 1,350 of 5,000 free-tier credits, before the $50.
