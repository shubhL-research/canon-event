# CANON EVENT, demo script

120 seconds. Six shots, roughly 20 seconds each. Shootable by someone who did not
write the code: every shot below names what is on screen, the exact file or URL
to open, the action, and the words spoken over it.

Nothing in this script asks you to stage a failure or to imply one happened. Two
shots are named at the bottom that must never appear.

---

## Before you record

### 1. Prove the build is good

```bash
cd canon-event
./verify.sh
```

Wait for `ALL CHECKS PASSED`. If anything fails, stop. Do not film a red suite
and narrate over it.

### 2. Confirm the wall is showing measurement, not fixture

Open `wall.html` and scroll to the bottom. The provenance strip prints one of two
things:

- `LIVE MEASUREMENT. Republished from the archived sweep payload.` Good, shoot it.
- Anything containing `FIXTURE`. Then `data/live.js` is missing. Stop and ask
  before filming, because the whole script assumes the live payload.

### 3. Read the numbers off the screen before you record the voiceover

This is the one rule that matters more than the shot list. The script below
quotes the figures as they stand today:

| Where | Figure as scripted |
|---|---|
| Hero sentence | `The US recall feed has a model-number field. It is empty on 183 of 183 product records. Every one of 104 EU alerts carries a barcode, and 98 of them pass their own check digit.` |
| Figure 1 | `0.0%` still on sale, `0 of 176 searchable notices`, CI `0.0% to 2.1%` |
| Figure 2 | `15.0%` unsearchable, `31 of 207 notices` |
| Regulators | CPSC `24.3%` unsearchable against Safety Gate `5.8%`, intervals do not overlap |
| Discard panel | `identifier not reasserted 246`, `brand conflict 15`, `no join key 4` |
| Ledger | `207 rows`, `173 AMBER`, `34 DISCARDED`, `0 RED` |
| Arm rail | all three `DEGRADED`, join coverage `44.0%` US, `53.1%` DE, `26.6%` IN against an 80% bound |
| Listings adjudicated | `23,811` across three arms. Shot 1 says this as words, so check it against the arm rail before recording |
| Detectors | `2 of 8 firing`, `3 could not run` |
| Act 06 | one confirmed RED found by hand, Acer AES015 at `$379.99`, outside the sweep |
| Every arm | `exit not attested on this sweep` |

If a re-sweep has moved any of these, **say the number that is on the screen**,
not the number printed here. A voiceover that disagrees with its own frame is the
single worst thing this video could do.

Two hard gates, both meaning the payload on disk is stale. Do not film either;
republish `data/live.js` first.

- Hero reads `96 of 207` or Figure 2 reads `46.4%`. That payload predates the
  identifier correction and those numbers are known to be wrong.
- Hero reads `27 of 207 recall notices name nothing a machine can search for`.
  That sentence was retired: the repository's own AMBER tier forms queries for
  exactly those notices, so it asserts something the code refutes.

**Say `exit not attested` out loud if the arm rail is on screen.** Three heals
tried to make the collectors report their own exit IP and all three were refused
for stripping the extraction, which is in `heals/`. The README says geo-accurate
rather than residential because the exits measured from the CLI resolve to hosting
companies, not carriers. Do not narrate "residential" over any frame.

### 4. Windows and tabs, opened before the camera rolls

Nothing is typed on camera except the one command in Shot 2.

| Tab | What to open |
|---|---|
| B1 | `wall.html` (no query string) |
| B2 | `https://www.cpsc.gov/Recalls/2024/Fisher-Price-Recalls-Dumbbell-Toy-in-Baby-Biceps-Gift-Sets-Due-to-Choking-Hazard` |
| B3 | `https://www.saferproducts.gov/RestWebServices/Recall?format=json&RecallNumber=24351` |
| B4 | `wall.html?state=blackout` |
| E1 | Editor, `heals/2026-08-19-de-001.md` |
| E2 | Editor, `examples/row.json` |
| T1 | Terminal, in the repo root, cleared |

Use Firefox for B3. Its built-in JSON viewer renders `Model: ""` legibly and
lets you filter. In Chrome the same tab is a wall of unwrapped text.

If the wall is deployed to a public URL by shoot day, use that URL for B1, B4 and
Shot 6, keeping the query strings identical. Otherwise `file://` is fine.

### 5. Capture settings

- Record 1920x1080 at 30fps. Browser window 1440x900 or larger. Coverage below
  1280px drops columns rather than reflowing, so a narrow window loses the ledger.
- Browser zoom at 100%.
- Leave reduced motion **off**. The count-up is the unit of the sentence, not
  decoration. See the warning below.
- Cursor visible. No zoom effects, no transitions, no music bed under speech.

---

## The count-up warning, read this before Shot 1

The hero number does not appear instantly. `wall.js` waits 380ms after paint,
then counts from 0 to the value over 1300ms. A still frame grabbed at load reads
**`0 of 207`**, which is a false statement sitting in your thumbnail.

**Hold the first frame for a full two seconds before you cut or grab a still.**
Total settle time is about 1.7 seconds. Two seconds is the safe number.

The same applies to the two percentages in Act 01. They count up when the section
scrolls into view, so pause on them rather than scrolling through them.

---

## Two shots that must never appear

1. **A fake terminal panel inside the interface.** Terminals in this video are
   real terminal windows, obviously separate from the browser. The wall never
   pretends to be a shell.
2. **Any moment where it is ambiguous whether a break was induced or organic.**
   Shot 5 shows a failure state. The narration says out loud that it was opened
   from the address bar and that nothing broke during filming. Do not cut that
   sentence to save time. Cut a different one.

---

## Shot 1 · 0:00 to 0:20 · The problem, and the one we found

**On screen.** Tab B1, `wall.html`, top of page. The hero sentence, then the
hazard-ruled line beneath it naming the scooter.

**Action.**

- 0:00 to 0:02 Hold on first paint. Do not cut, the number is still counting.
- 0:02 to 0:12 Static on the settled hero sentence.
- 0:12 to 0:20 Scroll just far enough to bring the **We found one anyway** line
  fully into frame. Stop there. Do not continue into Act 01.

**Say.**

> Governments recall products for burning, choking and killing children. Nobody
> checks whether those products actually leave the shelves. We checked. Three
> marketplaces, two regulators, twenty three thousand eight hundred and eleven
> listings, and the sweep came back with nothing. Then we looked somewhere it does
> not cover, and found a recalled electric scooter on sale.

**Why this shot is first.** Five of the eight public projects in this hackathon
are self-healing scrapers. Opening on a heal gate makes this the sixth. Opening
on a recalled product still for sale makes it the only one.

---

## Shot 2 · 0:20 to 0:45 · The scooter, and our own blind spot

**On screen.** Act 06, the first finding card. RED chip, the hazard sentence, the
facts grid, then the cross-reference line under it.

**Action.**

- 0:20 to 0:26 Land on the RED card. Hold on the hazard sentence and the price.
- 0:26 to 0:34 Move down the facts grid. Let `AES015 11x on page`,
  `Add to Cart` and `$379.99` be legible.
- 0:34 to 0:45 Hold on the cross-reference line, then on the banner above the
  list. Both must be readable in the cut.

**Say.**

> Recalled because the front tube can fold down while you are riding it. On sale
> today at three hundred and seventy nine dollars, with a live Add to Cart, and
> the word recall appears nowhere on that page. We fetched it, committed it, and
> the same classifier that ran the sweep scored it red.
>
> And here is the part we are not hiding. Our own sweep searched for this scooter
> in three marketplaces and returned not found in every one. It is a row in the
> ledger further up this page. This is not a different story from our zero. It is
> our zero, seen from outside.

**Do not** cut the second paragraph to save time. It is the most honest thing in
the video and it is the reason the finding is credible. Cut from Shot 4 instead.

---

## Shot 3 · 0:45 to 1:10 · The zero, and why it is worth believing

**On screen.** Act 01 figures, then the regulator comparison, then
**Before you believe the zero** in Act 07.

**Action.**

- 0:45 to 0:52 The two figures. Let them finish counting.
- 0:52 to 1:00 Scroll to the two regulator cards. Hold so both percentages and
  both intervals are legible.
- 1:00 to 1:10 Jump to the two matcher-proof cards. Hold on the counts.

**Say.**

> Zero of a hundred and eighty searchable notices found on sale. A zero is only
> worth anything if you can tell it apart from a broken matcher, so we prove both
> directions: thirteen planted products that must all come back red, and
> twenty one deliberate near misses that must all be discarded. Both hold.
>
> The finding that needs no scraper at all is here. One in five American recall
> notices names nothing you could type into a search box. For Europe it is one in
> seventeen, and the confidence intervals do not overlap. A recall nobody can
> search for cannot be enforced by anyone.

---

## Shot 4 · 1:10 to 1:28 · Bright Data, and the structured output

**On screen.** Act 04, the field-name chips and the geo table, then a cut to
`examples/row.json` open in the editor.

**Action.**

- 1:10 to 1:18 Hold on the row of field-name chips. `add_to_cart_button_text`
  and `manufacturer_part_number` must both be legible.
- 1:18 to 1:23 The geo table, asked against observed.
- 1:23 to 1:28 Cut to tab E1, `examples/row.json`. Hold still, do not scroll.

**Say.**

> The rules disqualify prebuilt scrapers, so the question is whether these are
> custom. The agent named these fields itself. Nobody picks
> add_to_cart_button_text by hand. Three requests, three countries asked for,
> three countries observed. And this is what comes out the other end: one row,
> one schema, every absent field marked missing rather than guessed.

**Structured output is a submission requirement**, and this is the only shot that
shows it. If you cut anything here, cut the geo table, not `row.json`.

---

## Shot 5 · 1:28 to 1:48 · The repair we refused to ship

**On screen.** Act 04, the heal cards, then the three-refusal table.

**Action.**

- 1:28 to 1:36 The refusal cards. Let one `REFUSED AT THE GATE` and its stated
  reason be readable.
- 1:36 to 1:48 The three-attempt table, then the loud line beneath it.

**Say.**

> Five repairs run against live collectors. Four refused. Three of them on one
> collector, failing the same way every time: asked to add one field, it dropped
> eleven. Every one came back awaiting approval. Any pipeline that reads a status
> and promotes on a pass would have shipped all three, and the third would have
> emptied a working collector two days before this deadline.

---

## Shot 6 · 1:48 to 2:00 · The black screen, and the ask

**On screen.** `wall.html?state=blackout`, typed in the address bar on camera,
then a cut to Act 08.

**Action.**

- 1:48 to 1:51 Type the state into the address bar in frame. This is what makes
  it unambiguous that the failure was opened, not induced.
- 1:51 to 1:57 Hold on the black hero and the hatched, greyed rows beneath it.
- 1:57 to 2:00 Cut to Act 08, the ask.

**Say.**

> This is what the page does when a detector says the data got suspiciously
> better. I opened that from the address bar just now, nothing broke during
> filming. Every figure is withheld and the rows go grey, because red is an
> accusation and we cannot stand behind one here.
>
> All we are asking is that the American regulator fill in a field it already
> writes, one key away in the same response.

**Do not** cut the sentence about the address bar. It is in the never-film rules
above for a reason.

---

## After the shoot

- Watch it once with the sound off. Every number on screen must be one you can
  point at in the repo.
- Watch it once with the picture off. Every number you say must be one that was
  on screen when you said it.
- Total run time under 2:00. Never over 2:30.
- Upload to YouTube, **public**, marked **Not for Kids**. An age restricted video
  can block a judge and the submission is scored as if the video does not exist.
- Put the link in the submission form and in the README.

---

## What each shot is doing, against the five criteria

The criteria are equally weighted, so nothing may be orphaned and nothing should
get two shots while another gets none.

| Shot | Criteria it feeds |
|---|---|
| 1 | Idea and impact. The problem, and a real product on sale in the first twenty seconds |
| 2 | Idea and impact, and technical execution. The finding, and the sweep admitting it missed it |
| 3 | Technical execution. The zero, both directions of the matcher proof, and the one result no scraper failure can touch |
| 4 | Bright Data Scraper Studio, and the structured output requirement |
| 5 | Self-healing. Four refusals and what they characterised |
| 6 | Presentation, and idea again. The failure state that is the thesis, then the ask |

**The ordering is deliberate.** Five of the eight public projects in this
hackathon are self-healing scrapers, because the organisers' own suggested-project
list names it the hero project. Self-healing is our method, not our product, so it
sits at 1:28 as supporting evidence rather than opening the video. A judge who has
already watched four gate demos today should meet the scooter first.

**What is deliberately not in the video, and where it lives instead.** The
capture-recapture calibration, the platform telemetry disagreement, the detector
board and act 07 are all strong and none of them survives a 120 second cut. They
are what the README and the wall are for. A demo that tries to show everything
shows nothing.
