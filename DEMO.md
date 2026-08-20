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

- `LIVE MEASUREMENT. TRIAL SLICE, 60 of 207 notices.` Good, shoot it.
- Anything containing `FIXTURE`. Then `data/live.js` is missing. Stop and ask
  before filming, because the whole script assumes the live payload.

### 3. Read the numbers off the screen before you record the voiceover

This is the one rule that matters more than the shot list. The script below
quotes the figures as they stand today:

| Where | Figure as scripted |
|---|---|
| Hero sentence | `21 of 207 recall notices name nothing a machine can search for` |
| Figure 1 | `0.0%` still on sale, `0 of 58 searchable notices`, CI `0.0% to 6.2%` |
| Figure 2 | `10.1%` unsearchable, `21 of 207 notices` |
| Discard panel | `AMBER 5812` |
| Ledger row 2 | `Foam mat`, `719` days, `SAFETY_GATE A12/02404/24` |

If a re-sweep has moved any of these, **say the number that is on the screen**,
not the number printed here. A voiceover that disagrees with its own frame is the
single worst thing this video could do.

One hard gate. If the hero sentence reads `96 of 207` and Figure 2 reads `46.4%`,
the payload on disk predates the identifier correction and those numbers are
known to be wrong. Do not film it. `data/live.js` needs republishing first.

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

## Shot 1 · 0:00 to 0:20 · The problem, and the headline

**On screen.** Tab B1, `wall.html`, top of page, Act I only. The corner filing
mark top left, the hero sentence centred, nothing else in frame.

**Action.**

- 0:00 to 0:02 Hold on first paint. Do not cut. The number is still counting.
- 0:02 to 0:14 Static on the settled hero sentence.
- 0:14 to 0:20 Slow scroll down just far enough that the scroll cue and the top
  of Act 01 enter frame. Stop before the figures start counting.

**Say.**

> Governments recall products for burning, choking and killing people. Nobody
> checks whether those products actually leave the shelves. This is what one week
> of checking looks like. Twenty one of two hundred and seven recall notices name
> nothing a machine can search for. Nobody can check those at all.

**Do not** read the number from this file. Read it from the screen.

---

## Shot 2 · 0:20 to 0:40 · The finding, verifiable live

This is the strongest twenty seconds in the project. It is a finding, and the
viewer can reproduce it while the video is still playing.

**On screen.** Two browser windows side by side. Left is B2, the CPSC recall
notice page for the Fisher-Price dumbbell toy. Right is B3, the same recall from
CPSC's own API, in the Firefox JSON viewer.

**Action.**

- 0:20 to 0:24 Both windows in frame. Left shows the notice, headline visible.
- 0:24 to 0:30 On the right, expand `Products` then `0`. Put the cursor on the
  line `Model: ""`. Hold on it.
- 0:30 to 0:34 On the right, scroll to `Description`. Highlight the phrase
  `The model number GJD49 is located on the back of the kettlebell toy in the
  gift set.`
- 0:34 to 0:40 Cut to T1. Type and run one line:

```bash
curl -s "https://www.saferproducts.gov/RestWebServices/Recall?format=json&RecallDateStart=2025-08-20&RecallDateEnd=2026-08-20" | grep -o '"Model":"[^"]*"' | sort | uniq -c
```

  One line of output comes back. It reads `543 "Model":""` or whatever the count
  is on the day you shoot. Hold on that output for three seconds.

**Say.**

> Here is why. A CPSC recall notice, and the same notice from CPSC's own API. The
> Model field is empty. The model number is in the description, written in prose.
> One line checks a year of them. Five hundred and forty three product records,
> every Model field empty.

**Caption**, lower third, plain white on black, from 0:36 to 0:40:

> EU Safety Gate, same corpus: 104 of 104 alerts carry a typed barcode.

**Do not** say a count the terminal did not print. The command prints its own
number. Read that one. CPSC keeps publishing, so it climbs.

---

## Shot 3 · 0:40 to 1:00 · What the sweep measured, and what it could not

**On screen.** Tab B1, scrolled to Act 01, then Act 03.

**Action.**

- 0:40 to 0:48 Act 01, both figures settled. Left figure reads `0.0%` with
  `0 of 58 searchable notices · 95% confidence 0.0% to 6.2%` under it. Right
  figure reads `10.1%` with `no scraper touches this figure` under it.
- 0:48 to 0:53 Scroll to Act 03. Hold on the instrument strip. The `Precision`
  cell reads `PENDING` with its reason printed beside it.
- 0:53 to 0:57 Continue to the arm rail. Two arms: `DE kaufland.de` measured,
  `IN flipkart.com` degraded, collector ids visible.
- 0:57 to 1:00 Jump to Act 04, the `What we did not see` panel. Put the cursor on
  the line reading `AMBER 5812`.

**Say.**

> Two arms ran. Five thousand eight hundred and twelve listings came back, and
> every one was adjudicated. None was a recalled product. Zero of fifty eight,
> with the interval printed beside it. The scraper was not broken, it looked.
> Precision says pending, because there are no red rows to hand check.

**Note for the editor.** This is the densest shot. If it runs long, cut the last
sentence and hold the `PENDING` cell in silence instead. The screen says it.

**If the arm rail states the adjudicated listing count directly**, point there
for the 5,812 instead of at the discard panel. Either location is the same
number.

---

## Shot 4 · 1:00 to 1:20 · The heal the agent refused to ship

Nobody fakes a rejection. This is the hardest thing in the project to fabricate
and it is a plain text file with a date on it.

**On screen.** Editor E1, `heals/2026-08-19-de-001.md`. Full screen, no browser
in frame.

**Action.**

- 1:00 to 1:05 Top of file. The title line reads `Heal DE-001`, followed by the
  word REFUSED. The header block under it is in view:

  ```
      collector   c_mt000dde2qdd6uln7z   (arm DE, amazon.de)
      outcome     REJECTED at the approval gate
      production  unchanged
  ```

- 1:05 to 1:09 Scroll to `## The break, as observed`. Hold on the
  `wait_element_timeout` block for two seconds.
- 1:09 to 1:16 Scroll to `## What the canary found`. Hold on this line and let it
  sit:

  ```
  ean   "4.1 4.1 ud af 5 stjerner (50) 4.1 ud af 5 stjerner"
  ```

- 1:16 to 1:20 Show the folder listing for `heals/`. Three files. Two say
  REFUSED, one says APPROVED.

**Say.**

> The German collector broke on a real product page. The repair worked, and it
> was refused anyway. The canary found the barcode field holding a review star
> rating, in Danish. Digits are what the matcher searches for. The template is
> unchanged. The arm is still withheld, and the reason is written down.

**Do not** cut to `wall.html?state=gate` here. That screen renders a fixture heal
pointing at a ledger file that does not exist, and putting it beside this real
refusal would blur which of the two happened. The file is the evidence. Stay in
the file.

---

## Shot 5 · 1:20 to 1:40 · The black screen

**On screen.** Tab B4, `wall.html?state=blackout`. Full bleed black,
`Verdict withheld · every collector`, and the line
`We do not know, so we will not say.`

**Action.**

- 1:20 to 1:23 Cut in on the wall as normal, Act 01, one second.
- 1:23 to 1:26 Show the address bar. The query string `?state=blackout` must be
  legible in frame. This is the honesty of the shot and it is not optional.
- 1:26 to 1:34 Hold on the black screen. Say nothing for the first two seconds of
  the hold. Silence is the point.
- 1:34 to 1:40 Scroll down two screens. Every figure struck through. Every arm
  black. The ledger rows still present and labelled historical rather than
  deleted.

**Say.**

> When the collector breaks, the wall goes empty. An empty hazard wall does not
> read as broken. It reads as safe. So it goes black instead, and says what it
> does not know. This is the fixture state, opened from the address bar. Nothing
> broke while filming and I am not pretending it did.

**Do not** shorten the last two sentences. They are the reason this shot is
allowed to exist.

---

## Shot 6 · 1:40 to 2:00 · One row, the schema under it, and the check

**On screen.** Tab B1, Act 02 ledger, then editor E2, then terminal T1, then an
end card.

**Action.**

- 1:40 to 1:44 Ledger in view. Click the **second row**, currently `Foam mat`,
  `SAFETY_GATE A12/02404/24`, `719` days. It expands in place into the two pane
  receipt card. If the ledger has been re-swept and that row has moved, use any
  row whose hazard sentence names a child, and read that sentence instead.
- 1:44 to 1:50 Hold on the open card. Left pane is the regulator's record. Right
  pane says the listing was not confirmed, and that the row is excluded from every
  statistic.
- 1:50 to 1:54 Cut to E2, `examples/row.json`. The first line on screen is the
  `_STATUS` key reading `FIXTURE DATA`. Scroll to the `evidence` block: assertion
  needle, dom path, content hash, trace, job id.
- 1:54 to 1:58 Cut to T1. Run `./verify.sh`. Hold on `ALL CHECKS PASSED`.
- 1:58 to 2:00 End card, no voice. White text on black:

  ```
  There is no green in this interface.
  The absence of a red row is not evidence of safety.

  github.com/shubhL-research/canon-event
  ```

**Say.**

> The regulator's record on the left, what we found on the right. Recalled seven
> hundred and nineteen days ago because a child could choke on it. We looked twice
> in each country. Not found, so it stays amber. Every row ships as structured
> output against a frozen schema, and one command checks all of it on a clean
> clone.

**Do not** open a row from `?state=v1` for this shot. That fixture has red rows
with full evidence chains and no live sweep has produced one. Showing a fixture
receipt while narrating a real finding is the exact confusion this project exists
to refuse.

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

## What each shot is doing, against criterion 6

Criterion 6 asks whether the demo explains the problem, the scraper workflow, the
structured output, and the final product. Nothing in the rubric may be orphaned.

| Shot | Covers |
|---|---|
| 1 | The problem, and the final product on screen in its normal state |
| 2 | The problem again at source, and the seed layer, which spends zero credits by design |
| 3 | The scraper workflow, what it measured, and what it refuses to publish |
| 4 | Extraction failure and self-healing, with the gate refusing a repair |
| 5 | The final product's failure state, which is the thesis |
| 6 | The structured output, the audit trail, and the clean clone check |
