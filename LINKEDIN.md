# LinkedIn post

One post. The track is judged on the single best post, so there is no thread and
no follow-up. Copy everything between the two rules.

---

CPSC's recall API gives every recalled product a Model field. I pulled a year of
US recalls to search marketplaces for those products. 543 product records. The
Model field is an empty string on all 543.

One line, and it prints the count itself:

curl -s "https://www.saferproducts.gov/RestWebServices/Recall?format=json&RecallDateStart=2025-08-20&RecallDateEnd=2026-08-20" | grep -o '"Model":"[^"]*"' | sort | uniq -c

The count moves as CPSC publishes. The empty string does not.

The model number is not missing. It is in the Description, as prose: "The model
number GJD49 is located on the back of the kettlebell toy in the gift set."

I read the structured field and published an unsearchable rate of 46.4%. That
figure measured my parser, not the regulator. Corrected, the US figure is 20.4%.
The correction argued against my own headline, which is how I knew it was worth
making.

For contrast, all 104 EU Safety Gate alerts carry a barcode in a typed field.

Second thing I found this week: my repair agent fixed a broken scraper and I
refused its fix, because the barcode field came back holding a review star
rating.

Built this week for @WeMakeDevs and Bright Data.
Repo: github.com/shubhL-research/canon-event

---

## Posting notes

- 191 words counting the curl line, 179 without it. Do not add hashtags, emoji or
  a comment with the link in it.
- Tag WeMakeDevs by typing `@WeMakeDevs` and selecting the company page from the
  dropdown. A tag that is only plain text does not notify anyone.
- Run the curl line once before posting. If the count is no longer 543, change
  the two numbers in the first paragraph to match what it prints. The claim is
  that every Model is empty, not that there are 543 of them.
- Post it as text. No image, no document carousel. The line is the artifact and
  LinkedIn's preview card would push it below the fold.
