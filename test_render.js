/* Headless smoke test for the wall renderer.
 *
 * No jsdom, no puppeteer, no devDependencies: a minimal DOM shim covering only
 * what wall.js actually touches. The point is that `node test_render.js` runs on
 * a clean clone with nothing installed, which is what the D6 clean-clone check
 * needs and what a judge can run in four seconds.
 *
 * Catches the class of bug a syntax check cannot: a template reading a property
 * that does not exist on the payload, which renders the literal string
 * "undefined" into the page and is invisible until someone looks at the screen.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = __dirname;
const VARIANTS = ["v1", "healing", "gate", "blackout", "loading"];

/* The live payload is a different shape from the fixtures: it is assembled by
   collector/publish.py rather than by data/make_fixture.py, and the two can drift.
   They did — the live payload omitted stats.credits, which threw inside
   renderInstruments and halted boot() after the rows had rendered, so the page
   looked complete while the motion layer never ran and every suite still passed.
   Rendering it here is what makes that impossible to repeat. */
const LIVE = path.join(ROOT, "data", "live.js");

function makeNode(id) {
  return {
    id,
    innerHTML: "",
    textContent: "",
    dataset: {},
    classList: { _s: new Set(), add(c) { this._s.add(c); }, contains(c) { return this._s.has(c); } },
    set className(v) { this._cn = v; },
    get className() { return this._cn || ""; },
    addEventListener() {},
    insertAdjacentHTML() {},
    remove() {},
    querySelectorAll() { return []; },
    closest() { return null; },
    nextElementSibling: null,
  };
}

function run(variant, livePath, nowMs) {
  const nodes = {};
  // Every element the renderer writes into. "figures" and the two notes were
  // added with the five-act restructure and were missing here, so nothing the
  // renderer put in them was ever checked.
  const ids = ["verdict", "figures", "instruments", "armRail", "wall", "pager",
               "curve", "notSeen", "healLedger", "provenance", "machinery",
               "sortNote", "historicalNote", "rail", "platform", "detectors", "hunt"];
  ids.forEach((i) => (nodes[i] = makeNode(i)));

  const sandbox = {
    window: {},
    document: {
      readyState: "complete",
      body: makeNode("body"),
      getElementById: (id) => nodes[id] || makeNode(id),
      // The stub holds no real elements, so a lookup finds nothing. The
      // first-row-open behaviour is exercised in a real browser instead; this
      // only has to not throw.
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener: () => {},
    },
    location: { search: variant === "v1" ? "" : "?state=" + variant },
    URLSearchParams,
    // Freshness is the one thing on this page decided by the reader's clock
    // rather than by the payload, so it can only be tested by moving the clock.
    Date: nowMs === undefined ? Date : new Proxy(Date, {
      get: (t, k) => (k === "now" ? () => nowMs : Reflect.get(t, k)),
      construct: (t, a) => (a.length ? new t(...a) : new t(nowMs)),
    }),
    Math,
    console,
  };
  sandbox.window.CANON_FIXTURES = undefined;
  vm.createContext(sandbox);

  vm.runInContext(fs.readFileSync(path.join(ROOT, "data", "fixtures.js"), "utf8"), sandbox);
  if (livePath) {
    vm.runInContext(fs.readFileSync(livePath, "utf8"), sandbox);
  }
  vm.runInContext(fs.readFileSync(path.join(ROOT, "wall.js"), "utf8"), sandbox);

  const html = ids.map((i) => nodes[i].innerHTML).join("\n") + "\n" + nodes.pager.textContent;
  // A guarded section reports its own failure in place, so counting those is how
  // the test sees a half-rendered page that would otherwise look fine.
  const failures = (html.match(/render-fail/g) || []).length;
  return { nodes, html, failures };
}

let failures = 0;
function check(cond, msg) {
  if (!cond) { console.log("  FAIL  " + msg); failures++; }
}

console.log("wall renderer smoke test\n");

/* A retracted claim must not survive anywhere a reader can see it.

   The exits were measured and every one resolves to a hosting ASN rather than a
   consumer ISP, so "residential" was withdrawn. It came out of the README first,
   then wall.html and wall.js, and it was still sitting in all four fixtures,
   which are exactly the states the demo films. A word retracted in one file and
   left in another is not retracted. */
{
  /* Line-scoped, not file-scoped. A whole-file exemption meant one sentence
     explaining the retraction licensed every other use of the word in the same
     file, which is how it survived in the fixtures. This flags an AFFIRMATIVE
     use and allows the retraction itself to be written down, which the project
     needs to do in several places. */
  /* Match the CLAIM, not the word. The project has to be able to write the
     retraction down, define what a residential exit would be, and tell the
     presenter not to say it, all of which contain the word. What it may never
     do again is assert that its own traffic came from one, and that assertion
     has a shape: a preposition in front of it. "from residential exit IPs" is
     the sentence that was published and withdrawn. "A residential exit names a
     carrier" is the sentence that withdraws it. */
  const RETRACTED = /\b(from|via|using|through|on|over)\s+residential\b/i;
  const ALLOWED = /not residential|no longer|retracted|rather than|withdrew|withdrawn|do not narrate|NOT prove/i;
  for (const f of ["wall.html", "wall.js", "wall.css", "data/fixtures.js",
                   "index.html", "README.md", "SCRAPER-STUDIO.md", "DEMO.md"]) {
    const full = path.join(ROOT, f);
    if (!fs.existsSync(full)) continue;
    const bad = fs.readFileSync(full, "utf8").split("\n")
      .map((line, i) => ({ line, n: i + 1 }))
      .filter((x) => RETRACTED.test(x.line) && !ALLOWED.test(x.line));
    check(bad.length === 0,
          '"residential" is retracted and must not be asserted in ' + f +
          (bad.length ? " (line " + bad[0].n + ")" : ""));
  }
}


/* The withheld hero must not look like a healthy one.

   This is the project's entire thesis and it silently stopped being true. The
   hero was styled #000000 unconditionally, and the withheld rules still pointed
   at `.verdict`, a class wall.html had stopped emitting. Every suite passed
   while the signature state rendered identically to a good day, because nothing
   here was looking at colour. */
{
  const css = fs.readFileSync(path.join(ROOT, "wall.css"), "utf8");
  const heroRule = /\.act-finding\s*\{[^}]*background:\s*var\(--([a-z-]+)\)/.exec(css);
  check(!!heroRule, "the hero declares a background token");
  check(heroRule && heroRule[1] !== "void",
        "the hero ground is NOT black: black has to stay available as a signal");
  check(/\.act-finding\.is-withheld\s*\{[^}]*background:\s*var\(--void\)/.test(css),
        "the withheld hero IS black, on the class the renderer actually applies");
  check(/\.act-finding\.is-withheld[^{]*\{[^}]*border-top:[^;]*var\(--hazard\)/.test(css),
        "the withheld hero carries a hazard rule, so it survives greyscale");
  const html = fs.readFileSync(path.join(ROOT, "wall.html"), "utf8");
  check(!/\.verdict\.is-withheld/.test(css) || /class="[^"]*\bverdict\b/.test(html),
        "no withheld styling points at a class the markup no longer emits");
}


/* The live payload, if one has been published.
   It is assembled by collector/publish.py, the fixtures by data/make_fixture.py,
   and the two drifted: the live payload omitted stats.credits, which threw inside
   renderInstruments and halted boot() after the rows had drawn. The page looked
   complete, the motion layer never ran, and every suite passed. */
if (fs.existsSync(LIVE)) {
  const out = run("v1", LIVE);
  const html = out.html;
  console.log("live payload (data/live.js)");
  check(!/\bundefined\b/.test(html), '"undefined" leaked into the live payload');
  check(!/\bNaN\b/.test(html), '"NaN" leaked into the live payload');
  check(!/\[object Object\]/.test(html), '"[object Object]" leaked into the live payload');
  check(out.failures === 0,
        `no section failed to render (${out.failures} did)`);
  // The invariant is that a headline renders, not that it is a withheld one.
  // Whether the verdict band appears depends on whether a collector broke, and a
  // test should not require the sweep to have gone badly.
  check(/<h1>/.test(out.nodes.verdict.innerHTML),
        "the live payload renders a headline");
  check(out.nodes.figures.innerHTML.indexOf("figure-claim") > -1,
        "the live payload renders its two figures");

  // ACT 06. The hunt rows are the only rows on this page that were found by
  // hand, so the two things that keep them honest are load-bearing and tested:
  // the banner disclaiming them as sweep results, and the fact that they leave
  // the sweep's own denominator alone. A hunt section that renders its findings
  // WITHOUT the disclaimer is worse than one that renders nothing.
  const hunt = out.nodes.hunt ? out.nodes.hunt.innerHTML : "";
  if (hunt) {
    check(/These are not sweep results/.test(hunt),
          "the hunt act disclaims itself as non-sweep output");
    check(/hunt-item/.test(hunt), "the hunt act renders its findings");
    check(/hunt-chip is-red/.test(hunt),
          "the hunt act renders the confirmed RED as red");
    check(/hunt-evidence/.test(hunt),
          "every hunt finding links the committed page it was derived from");
    // The number in the banner must be the sweep's real denominator, not a
    // figure the hunt inflated. If a hand-found row ever reaches `survival`,
    // this is the assertion that catches it.
    const src = fs.readFileSync(LIVE, "utf8");
    const doc = JSON.parse(src.slice(src.indexOf("{"), src.lastIndexOf(";")));
    check(hunt.indexOf(`${doc.stats.survival.n} of ${doc.stats.survival.d}`) > -1,
          "the hunt banner quotes the sweep's untouched survival denominator");
    check(doc.hunt.findings.every((f) => !("days" in f) && !("tier" in f)),
          "no hunt finding carries sweep row fields");
  }
  /* Every class the renderer emits must have a rule somewhere.
     This exists because of a real bug that shipped: `.verdict.is-withheld`
     styled a class the renderer never emitted, so a WITHHELD verdict rendered
     in the same black as a healthy one and every suite still passed, because
     nothing in the suite looked at colour. A dead selector is invisible to a
     test that only asks whether text appeared. This asks the other question. */
  const styles = fs.readFileSync(path.join(ROOT, "wall.css"), "utf8") +
                 fs.readFileSync(path.join(ROOT, "contract", "tokens.css"), "utf8");
  const wordChar = new RegExp("[A-Za-z0-9_-]");
  const emitted = new Set();
  (html.match(/class="([^"]+)"/g) || []).forEach((m) =>
    m.slice(7, -1).trim().split(" ").forEach((c) => c && emitted.add(c.trim())));

  // A rule counts only if the class name ENDS there. Matching ".hunt" inside
  // ".hunt-item" would let a genuinely dead class pass.
  function hasRule(cls) {
    const needle = "." + cls;
    for (let k = styles.indexOf(needle); k > -1;
         k = styles.indexOf(needle, k + 1)) {
      if (!wordChar.test(styles.charAt(k + needle.length))) return true;
    }
    return false;
  }
  const orphans = [...emitted].filter((c) => !hasRule(c));
  check(orphans.length === 0,
        "every rendered class has a CSS rule (" + orphans.length + " orphan: " +
        orphans.slice(0, 8).join(", ") + ")");

  // The verdict colours must be distinct rules, not the same one twice. This is
  // the specific shape of the bug above: two states, one colour, silent.
  function ruleBody(sel) {
    const k = styles.indexOf(sel);
    if (k < 0) return "";
    return styles.slice(k, styles.indexOf("}", k));
  }
  const redBody = ruleBody(".hunt-chip.is-red");
  const amberBody = ruleBody(".hunt-chip.is-amber");
  check(redBody.indexOf("var(--hazard)") > -1,
        "the hunt RED chip resolves to the hazard token");
  check(amberBody.indexOf("var(--amber)") > -1,
        "the hunt AMBER chip resolves to the amber token");
  check(redBody !== amberBody,
        "hunt RED and AMBER are different rules, not the same colour twice");





  console.log("");
} else {
  console.log("live payload: none published, skipping\n");
}

for (const variant of VARIANTS) {
  let out;
  try {
    out = run(variant);
  } catch (e) {
    console.log(`FAIL ${variant}: threw ${e.message}`);
    failures++;
    continue;
  }
  const html = out.html;

  console.log(`?state=${variant}`);

  // The bug class this file exists to catch.
  check(!/\bundefined\b/.test(html), `"undefined" leaked into rendered HTML`);
  check(!/\[object Object\]/.test(html), `"[object Object]" leaked into rendered HTML`);
  check(!/\bNaN\b/.test(html), `"NaN" leaked into rendered HTML`);

  // There is no green in this interface, and that has to stay true in the markup.
  //
  // Scoped to OUR markup, not to the regulator's. CPSC notice 24338 reads "even
  // if the indicator is green, the car seat may not be properly attached", and
  // hazard text is quoted verbatim and never paraphrased. This check fired the
  // moment that row entered the visible page, which made it a test that forbids
  // the corpus rather than a test that forbids a colour.
  const ours = html.replace(/<div class="quote">[\s\S]*?<\/div>/g, "")
                   .replace(/<blockquote[\s\S]*?<\/blockquote>/g, "");
  check(!/(green|#0[0-9a-f]?[a-f8-9][0-9a-f]{3}\b.*green)/i.test(ours),
        "a green token appeared in the interface's own markup");

  if (variant === "loading") {
    check(/skeleton/.test(html), "loading state renders skeleton rows");
    check(/Loading sweep/.test(html), "loading state names the sweep it is waiting for");
    continue;
  }

  check(out.nodes.wall.innerHTML.length > 1000, "wall rendered rows");
  check(/CPSC/.test(html), "regulator is cited on the rows");
  check(/class="chip v-/.test(html), "arm chips rendered");
  check(/class="track"/.test(html), "day bars rendered");

  if (variant === "blackout") {
    check(/is-withheld/.test(out.nodes.verdict.className) ||
          /withheld-mark/.test(out.nodes.verdict.innerHTML), "blackout renders the withheld band");
    check(/implausible_cleanliness/.test(html), "blackout names the detector that fired");
  }
  if (variant === "v1") {
    // Case-insensitive, and paired with the class, because the assertion is that
    // the withheld band renders — not that the copy is upper-cased in the markup.
    // The band is now written in sentence case and upper-cased by the stylesheet,
    // which is a typographic decision the test should not be able to veto.
    check(/verdict withheld/i.test(html) && /withheld-mark/.test(html),
          "v1 renders the withheld verdict band");
    check(/HEAL REJECTED/.test(html), "v1 renders the rejected heal, the hardest thing to fake");
    check(/prompt budget \d+ \/ 1000/.test(html), "prompt budget meter rendered");
    check(/Vodafone|Reliance|Comcast/.test(html), "exit attestation names a residential ASN");
    check(/MISSING/.test(html) === false, "MISSING only appears once a receipt is opened");
    check(/capture-recapture/i.test(html), "recall floor is stated");
    check(/of \d+ shown/.test(html), "pager reconciles displayed rows to the finding set");
    check(/Survival by age/.test(html), "survival curve section rendered");
    check(/isotonic regression/.test(html), "curve names the method it used");
    check(/curve-band/.test(html), "curve bars drawn");
  }
  if (variant === "healing") {
    check(/Heal in flight/.test(html), "healing renders the step track copy");
  }
  if (variant === "gate") {
    check(/AWAITING APPROVAL/.test(html), "gate renders the approval state");
    check(/Locked until/.test(html), "approve is visibly locked");
  }
}

/* The receipt card only renders on click, so exercise it directly: this is where
   the MISSING path lives and it is the single most important thing on screen. */
console.log("\nreceipt card");
{
  const fixtures = {};
  vm.runInNewContext(fs.readFileSync(path.join(ROOT, "data", "fixtures.js"), "utf8"),
                     { window: fixtures });
  const doc = fixtures.CANON_FIXTURES.v1;
  const withMissing = doc.rows.filter(
    (r) => r.evidence && !r.evidence.assertion.dom_path);
  check(withMissing.length >= 1, "fixture contains a row exercising the MISSING path");

  const full = doc.rows.filter((r) => r.evidence && r.evidence.assertion.dom_path);
  check(full.length >= 10, "fixture contains enough FULL-evidence rows for the video");

  const red = doc.rows.filter((r) => r.tier === "RED");
  check(red.every((r) => Object.values(r.arms).some((v) => v === "RED")),
        "every RED row has at least one RED arm");
  check(red.every((r) => r.evidence && r.evidence.assertion.needle),
        "every RED row carries an identity re-assertion needle");
  check(red.every((r) => r.evidence.assertion.context.includes(r.evidence.assertion.needle)),
        "every needle actually appears in its own captured context");
}

/* FRESHNESS, tested by moving the clock forward.

   The suite had zero coverage of the word STALE. It could not have had any: the
   payload's own freshness detector is computed at publish time, where the age is
   always zero, so nothing in a static payload can ever be stale. The condition
   only exists in a browser, hours later, which is exactly when a judge opens it.

   So the clock is moved instead. Once past the bound the page must say so in
   three places, and all three matter: the note above the rows, the detector
   card, and the summary count that would otherwise contradict its own card. */
/* The acts are a numbered sequence and must actually be one.

   Two acts both printed 04 for as long as the Bright Data act existed, so the
   page read 01 02 03 04 05 06 04. Half the numbers are static in wall.html and
   half are written by the renderer, which is why neither file looked wrong on
   its own. They are only wrong together, so they are checked together. */
{
  const markup = fs.readFileSync(path.join(ROOT, "wall.html"), "utf8");
  const js = fs.readFileSync(path.join(ROOT, "wall.js"), "utf8");
  const nums = [];
  for (const src of [markup, js]) {
    for (const m of src.matchAll(/act-num">(\d+)</g)) nums.push(m[1]);
  }
  const dupes = nums.filter((n, i) => nums.indexOf(n) !== i);
  check(dupes.length === 0,
        "every act number is unique (duplicated: " + [...new Set(dupes)].join(", ") + ")");

  const sorted = [...nums].sort();
  const expected = nums.map((_, i) => String(i + 1).padStart(2, "0"));
  check(JSON.stringify(sorted) === JSON.stringify(expected),
        "act numbers run 01.." + expected[expected.length - 1] +
        " with no gaps (found " + sorted.join(" ") + ")");

  // Every rail destination must exist, or the only wayfinding on a very long
  // page silently drops the reader nowhere.
  const railTargets = [...markup.matchAll(/<a href="#([\w-]+)"><span class="rail-dot"/g)]
    .map((m) => m[1]);
  check(railTargets.length > 0, "the rail has entries");
  for (const t of railTargets) {
    check(markup.includes('id="' + t + '"'),
          'rail target #' + t + " exists in the document");
  }
}

if (fs.existsSync(LIVE)) {
  const src = fs.readFileSync(LIVE, "utf8");
  const doc = JSON.parse(src.slice(src.indexOf("{"), src.lastIndexOf(";")));
  const sweptAt = Date.parse(doc.swept_at);
  const bound = doc.freshness_bound_s * 1000;

  console.log("freshness, clock moved past the bound");

  const fresh = run("v1", LIVE, sweptAt + bound - 60000);
  check(fresh.nodes.historicalNote.textContent === "",
        "inside the bound the page claims no staleness");
  check(!/freshness bound\. The/.test(fresh.nodes.detectors.innerHTML),
        "inside the bound the freshness detector stays quiet");

  const stale = run("v1", LIVE, sweptAt + bound + 60000);
  check(/past its \d+h freshness bound/.test(stale.nodes.historicalNote.textContent),
        "past the bound the page states its own staleness above the rows");
  // Scoped to the freshness CARD. "det is-fired" also matches join_key_coverage,
  // which fires on every sweep, so the looser pattern passed even with the stale
  // path disabled: another assertion that could not fail.
  check(/past its \d+h freshness bound/.test(stale.nodes.detectors.innerHTML),
        "past the bound the freshness detector fires and states the age");
  check(/2 of 8 detectors/.test(stale.nodes.detectors.innerHTML),
        "the detector summary counts the firing freshness card");
  check(/days frozen/.test(stale.nodes.wall.innerHTML),
        "past the bound every day counter is marked frozen");
  check(/arm state-\w+ is-stale/.test(stale.nodes.armRail.innerHTML),
        "the stale hatch is added to the arm state, not substituted for it");
  check(/join_key_coverage|notices matched one/.test(stale.nodes.armRail.innerHTML),
        "the arm still says why it degraded after going stale");

  // A fixture with a swept_at in the future must never be called stale.
  const future = run("v1", LIVE, sweptAt - 3600000);
  check(future.nodes.historicalNote.textContent === "",
        "a clock behind the sweep is not staleness");
  console.log("");
}

console.log(failures ? `\n${failures} FAILURES` : "\nall checks passed");
process.exit(failures ? 1 : 0);
