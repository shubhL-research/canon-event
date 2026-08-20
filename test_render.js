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

function run(variant, livePath) {
  const nodes = {};
  // Every element the renderer writes into. "figures" and the two notes were
  // added with the five-act restructure and were missing here, so nothing the
  // renderer put in them was ever checked.
  const ids = ["verdict", "figures", "instruments", "armRail", "wall", "pager",
               "curve", "notSeen", "healLedger", "provenance", "machinery",
               "sortNote", "historicalNote", "rail", "platform"];
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
    Date,
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
  check(!/\.verdict\.is-withheld/.test(css) || /class="[^"]*verdict/.test(html),
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

console.log(failures ? `\n${failures} FAILURES` : "\nall checks passed");
process.exit(failures ? 1 : 0);
