# data/sweeps

Sweep output, committed rather than gitignored.

`data/sweeps/` used to be excluded. That left the repository with no primary
evidence that any scrape had happened: four collector ids typed into a README and
three markdown ledgers. The wall's own footer pointed a reader at this directory
for the full row set, and on a clean clone the directory did not exist.

## What is here

`raw-row-kaufland-de.json`
One row exactly as Scraper Studio returned it, field names and all. The field
names were chosen by the Scraper Studio AI Agent when it built the collector from
a natural-language brief, which is why they are `add_to_cart_button_text` and
`manufacturer_part_number` rather than anything we would have picked. A library
scraper would have handed back a fixed schema we did not choose.

`sweep-2026-08-20.csv`
The full three-arm sweep after adjudication. 60 notices, three storefronts, 180
notice-arm verdicts, one row each. Carries the arm state and coverage, the
verdict, the tier, the discard reasons and which of the two query strategies
found the listing.

## Reading them together

The raw row is what the platform returned. The CSV is what survived
adjudication. The distance between them is the matcher, and it is where every
claim on the wall is either earned or refused.

Three things are visible in the raw row and nowhere else:

- Values arrive doubled. `ean` reads `8721003407246 8721003407246`. It fails its
  own check digit as written and passes once collapsed, which is why
  `collapse_repeat()` runs before any identity test.
- The brand field holds a part number, not a brand.
- The notice was a Besrey stroller and the page returned a MamaLoes buggy from a
  reseller. The barcode matches and the brand does not, which is the exact case
  `brand_conflict()` is written to allow rather than reject.

## What is not here

Snapshots expire on the platform after 16 days, so the archived JSON payloads in
`data/` are the durable record. The per-arm health reports that carry the listing
totals were not committed at the time of the sweep, so the figure they produce is
carried forward and labelled as carried wherever it appears.
