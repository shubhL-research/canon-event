# Heal US-003 — REFUSED, and the pattern across three refusals

    collector   c_mt1fh690ebsllah9n   (arm US, amazon.com)
    raised      2026-08-20 18:22 UTC
    resolved    2026-08-20 18:47 UTC
    outcome     REJECTED at the approval gate
    production  unchanged, verified after the refusal
    decision    stop. Three attempts is enough to call it.

## The attempt

`2026-08-20-us-002.md` refused a heal that was asked to add an in-stage exit
attestation and instead removed the extraction. The single instruction it
discarded was "keep every existing field exactly as it is", and the same
instruction had been discarded by `2026-08-19-us-001.md` before it.

So this prompt stopped relying on that phrase and named all eleven fields:

> Keep the existing extraction exactly as it is. Every emitted row must continue
> to contain all of these fields with the same names and the same values as now:
> title, brand, price, currency_symbol, availability, add_to_cart_button,
> seller_name, manufacturer_part_number, barcode, page_language,
> product_page_url. Do not remove, rename or stop populating any of them. In
> addition, and only in addition, make one request to
> https://brdtest.com/myip.json in the same stage that fetches the product pages
> [...] If that one request fails, omit those three fields and still emit every
> field listed above.

26 steps. `awaiting_approval`. Preview empty again, so again it decided nothing,
and again the draft was run instead.

    bdata scraper run <id> --version=dev  https://www.amazon.com/s?k=Smalto

    240 rows, each containing exactly: input, product_page_url

    exit_ip, exit_country, asn_org              ABSENT
    title, brand, price, currency_symbol        ABSENT
    availability, add_to_cart_button            ABSENT
    seller_name, manufacturer_part_number       ABSENT
    barcode, page_language                      ABSENT

Every one of the eleven fields named in the prompt as must-not-be-removed was
removed. Production, re-run after the refusal, returns 240 rows with seven fields
populated. Nothing lost.

## The pattern, which is the actual finding

Three heals on this collector, three refusals, the same failure each time.

| | asked for | returned |
|---|---|---|
| US-001 | wait for the right results container | rows containing only a URL |
| US-002 | add three attestation fields, keep the rest | rows containing only a URL |
| US-003 | add three fields, eleven named as protected | rows containing only a URL |

**Asked to add one field, it dropped eleven.** Naming them explicitly changed
nothing, which is the part worth reporting: the failure is not the prompt being
vague. A repair that reduces a collector to the URLs it visited is a valid
transformation of "make this page work" and an invalid answer to every question
actually asked.

All three returned `awaiting_approval`. Any pipeline that reads a status field and
promotes on green would have shipped all three, and the third would have silently
emptied a working production collector two days before a deadline.

## What actually caught them

US-001 was caught by reading preview rows. That worked only because its preview
happened to be non-empty.

US-002 and US-003 had empty previews, and an empty preview here proves nothing:
production returns zero rows for the same query. The thing that decided both was
`--version=dev`, running the proposed template against a query the archive shows
had produced 798 listings on production.

That is the documented path and it should have been the first move all three
times. A preview is a sample the platform chose. A draft run is the template
answering a question you chose.

## Why this stops here

The attestation would have upgraded one sentence on the wall from "exit not
attested on this sweep" to a named ASN. The remaining route is the Scraper Studio
IDE, where `request()` is written rather than described, and that is a larger
piece of work than the thing it buys.

Nothing overclaims in the meantime. The exits measured from the CLI resolve to
hosting companies rather than carriers, so the README says geo-accurate rather
than residential, and every arm on the wall says it was not attested. The gap is
visible, named, and now carries three documented attempts.

A limitation with three refusals behind it is a stronger artifact than the
attestation would have been.
