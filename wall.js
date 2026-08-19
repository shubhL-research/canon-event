/* CANON EVENT wall renderer.
 *
 * No framework, no build step, no backend. The wall reads a static JSON payload
 * and nothing else, so swap day is `cp`, not an integration.
 *
 * Switch states with the query string:
 *   wall.html                  base sweep, DE withheld with a rejected heal
 *   wall.html?state=healing    heal in flight, IN stale
 *   wall.html?state=gate       proposed template awaiting approval
 *   wall.html?state=blackout   implausible cleanliness fired, whole board black
 *   wall.html?state=loading    first paint, correct geometry, no data
 */
(function () {
  "use strict";

  var PAGE_CAP = 40;
  var ARM_ORDER = ["US", "DE", "IN"];

  // ---------------------------------------------------------------- helpers

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function el(id) { return document.getElementById(id); }

  function pct(v) { return (v * 100).toFixed(1) + "%"; }

  function ci(pair) {
    return pair ? "CI " + pct(pair[0]) + " to " + pct(pair[1]) : "";
  }

  function commas(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }

  /* Freshness renders absolute and relative together, always both. A relative
     time alone hides when the capture actually happened; an absolute time alone
     hides how stale it is. */
  function freshness(iso) {
    var t = Date.parse(iso);
    var clock = iso.replace("T", " ").replace(/\.\d+/, "");
    var delta = Date.now() - t;
    if (isNaN(t)) return clock;
    if (delta < 0) return clock + " · fixture, sweep not yet run";
    var mins = Math.floor(delta / 60000);
    var rel = mins < 60 ? mins + "m ago"
      : mins < 1440 ? Math.floor(mins / 60) + "h " + (mins % 60) + "m ago"
        : Math.floor(mins / 1440) + "d ago";
    return clock + " · " + rel;
  }

  // ------------------------------------------------------------ MISSING path

  /* Bright Data omits absent keys rather than nulling them. A missing key is not
     an error and it is not a zero. It renders as the struck field name and the
     word MISSING, so absence is shown without implying a value. */
  function field(label, value, opts) {
    opts = opts || {};
    var present = value !== undefined && value !== null && value !== "";
    var cls = "field" + (present ? "" : " is-missing") + (opts.mono ? " mono-v" : "");
    var shown = present ? esc(value) : "MISSING";
    return '<div class="' + cls + '">' +
      '<div class="k">' + esc(label) + "</div>" +
      '<div class="v' + (opts.mono && present ? " mono" : "") + '">' + shown + "</div>" +
      "</div>";
  }

  // ------------------------------------------------------------ verdict band

  /* The hero sentence, with the day count marked up so it can be counted.

     A number that arrives already at 714 is a fact. A number that counts to 714
     is a duration, which is what it actually is: the days this product stayed on
     sale after a government told people it could kill a child. The animation is
     not decoration, it is the unit. */
  function heroSentence(sentence) {
    if (!sentence) return "";
    return esc(sentence).replace(/(\d[\d,]*)(\s*days)/,
      function (_, n, tail) {
        return '<span class="count" data-to="' + n.replace(/,/g, "") + '">0</span>' + tail;
      });
  }

  function renderVerdict(doc) {
    var node = el("verdict");
    var withheld = doc.arms.filter(function (a) { return a.state === "WITHHELD"; });
    var blackout = doc.global_blackout && doc.global_blackout.fired;
    var hero = doc.stats.hero;
    var body;

    if (blackout) {
      body =
        '<span class="withheld-mark">Verdict withheld · every collector</span>' +
        "<h1>We do not know, so we will not say.</h1>" +
        '<p class="sub">' + esc(doc.global_blackout.copy) + "</p>" +
        '<p class="clause">implausible_cleanliness fired: observed drop ' +
        pct(doc.global_blackout.observed_drop) + " against a " +
        pct(doc.global_blackout.threshold) + " threshold. " +
        "Every figure on this page is withheld until a sweep corroborates it.</p>";
    } else if (withheld.length) {
      var a = withheld[0];
      body =
        '<span class="withheld-mark">Verdict withheld · ' + esc(a.code) + "</span>" +
        "<h1>" + heroSentence(hero.sentence) + "</h1>" +
        '<p class="sub">Every one of these is a product a government recalled, ' +
        "found on sale again from a residential connection in that country.</p>" +
        '<p class="clause">The ' + esc(a.code) + " collector has been broken since " +
        esc(doc.swept_at.slice(11, 16)) + " UTC, so anything that depends on it is " +
        "withheld rather than published. " + doc.stats.arms_measured.n + " of " +
        doc.stats.arms_measured.d + " countries measured.</p>";
    } else {
      body =
        "<h1>" + heroSentence(hero.sentence) + "</h1>" +
        '<p class="sub">Every one of these is a product a government recalled, ' +
        "found on sale again from a residential connection in that country.</p>" +
        '<p class="clause">' + doc.stats.arms_measured.n + " of " +
        doc.stats.arms_measured.d + " countries measured.</p>";
    }

    node.className = "act act-finding" + (blackout || withheld.length ? " is-withheld" : "");
    node.innerHTML = '<div class="finding-inner">' + body +
      '<p class="scroll-cue">What the sweep found</p></div>';
  }

  /* ------------------------------------------------------ ACT II: the figures

     Two numbers, said in a sentence a reader can repeat. The intervals and the
     method names are not removed, they move to ACT IV: a reader who does not
     know what a Wilson interval is should still be able to leave with the
     finding, and a reader who does should be able to check it. */
  function figure(value, claim, basis, cls) {
    return '<div class="figure ' + (cls || "") + '">' +
      '<div class="figure-value">' + value + "</div>" +
      '<p class="figure-claim">' + claim + "</p>" +
      '<p class="figure-basis">' + basis + "</p></div>";
  }

  function renderFigures(doc) {
    var s = doc.stats, out = [];

    /* STILL ON SALE. Contaminated by any broken collector, so it is the figure
       most often withheld — which is why it is not the only one here. */
    out.push(figure(
      s.survival.contaminated ? pct(s.survival.v) : '<span class="count" data-to="' +
        (s.survival.v * 100).toFixed(1) + '" data-suffix="%">0</span>',
      "of recalled products we could search for are still on sale today",
      s.survival.n + " of " + s.survival.d + " searchable notices · 95% confidence " +
        pct(s.survival.ci95[0]) + " to " + pct(s.survival.ci95[1]),
      s.survival.contaminated ? "is-withheld" : ""));

    /* NEVER CHECKABLE. Computed entirely from the free government corpus, so no
       scraper can contaminate it and it survives every collector failing at
       once. On the project's worst day this is the only publishable figure, and
       that is exactly why it leads alongside the other one. */
    out.push(figure(
      '<span class="count" data-to="' + (s.unsearchable.v * 100).toFixed(1) +
        '" data-suffix="%">0</span>',
      "of recall notices name nothing a machine can search for, so nobody can " +
        "check them at all",
      s.unsearchable.n + " of " + s.unsearchable.d + " notices · 95% confidence " +
        pct(s.unsearchable.ci95[0]) + " to " + pct(s.unsearchable.ci95[1]) +
        " · no scraper touches this figure"));

    el("figures").innerHTML = out.join("");
  }

  // --------------------------------------------------------- instrument line

  function instrument(label, value, qualifier, cls) {
    return '<div class="instrument ' + (cls || "") + '">' +
      '<div class="label">' + esc(label) + "</div>" +
      '<div class="value">' + value + "</div>" +
      '<div class="qualifier">' + qualifier + "</div></div>";
  }

  function renderInstruments(doc) {
    var s = doc.stats, out = [];
    var struck = function (stat) { return stat.contaminated ? "is-struck" : ""; };

    // The two headline figures are NOT repeated here. ACT II publishes them in
    // plain English; restating them in the apparatus strip is the same number
    // twice, and it left this grid with a ragged row of empty cells. What belongs
    // here is only what qualifies those two: the measures that are still pending,
    // the precision that bounds them, the floor under what we missed, and what
    // the sweep cost.

    if (s.border_escape.v === null) {
      out.push(instrument("Border escape", "PENDING",
        esc(s.border_escape.pending.slice(0, 64)) + "…", "is-apparatus is-pending"));
    } else {
      out.push(instrument("Border escape", pct(s.border_escape.v),
        s.border_escape.n + " of " + s.border_escape.d + " · " + ci(s.border_escape.ci95),
        "is-apparatus " + struck(s.border_escape)));
    }

    /* Precision carries its interval next to the number it qualifies, never in a
       footnote. Recall is not directly measured: capture-recapture across the two
       query strategies puts a floor under what we missed. */
    var rc = s.precision.recall;
    out.push(instrument("Precision", pct(s.precision.v),
      s.precision.n + " of " + s.precision.d + " hand-verified · " + ci(s.precision.ci95),
      "is-apparatus"));
    out.push(instrument("Recall, floor", "≥ " + Math.round(rc.missed_floor) + " missed",
      "capture-recapture, " + esc(rc.estimator.split(" ")[0]) + " · lower bound",
      "is-apparatus"));

    out.push(instrument("Arms measured", s.arms_measured.n + " of " + s.arms_measured.d,
      doc.arms.map(function (a) { return a.code + " " + a.state.toLowerCase(); }).join(" · "),
      "is-apparatus"));

    out.push(instrument("Last sweep", '<span style="font-size:11px">' +
      esc(freshness(doc.swept_at)) + "</span>",
      "freshness bound " + doc.freshness_bound_s / 3600 + "h", "is-apparatus"));

    out.push(instrument("Credits", commas(s.credits.used),
      "of " + commas(s.credits.cap) + " · " + commas(s.credits.code) + " code, " +
      commas(s.credits.browser) + " browser", "is-apparatus"));

    el("instruments").innerHTML = out.join("");
  }

  // -------------------------------------------------------------- arm rail

  function armCopy(a, doc) {
    var j = a.job, h = a.heal;
    switch (a.state) {
      case "MEASURED":
        return "Measured " + doc.swept_at.slice(11, 19) + "Z. " + j.data_lines +
          " of " + j.inputs + " inputs returned rows. " + j.fails + " fails.";
      case "DEGRADED":
        return "Partial. " + j.fails + " of " + j.inputs + " inputs returned no row and no " +
          "archived empty-result page. Rows from this arm are shown. Counts carry a partial stamp.";
      case "WITHHELD":
        return h.status === "rejected"
          ? "Heal rejected. " + esc(h.failed_canary) + ". Production template unchanged at " +
            esc(a.template) + ". Arm remains withheld."
          : "Collector unhealed. We do not know, so we will not say.";
      case "HEALING":
        return "Heal in flight. Step " + h.step + " of 7. Rows below are frozen at the last sweep.";
      case "AWAITING_APPROVAL":
        return "Proposed template awaiting approval. Canary " + h.canary_pass + " of " +
          h.canary_total + " resolving RED on version=dev. Approve is locked until " +
          h.canary_total + " of " + h.canary_total + ".";
      case "STALE":
        return "Last sweep exceeds the " + doc.freshness_bound_s / 3600 +
          "h freshness bound. Rows are historical. Day counters are frozen at last capture, not counting.";
      default:
        return "";
    }
  }

  function renderArms(doc) {
    el("armRail").innerHTML = doc.arms.map(function (a) {
      var extra = "";
      if (a.state === "DEGRADED") {
        var cov = a.job.data_lines / a.job.inputs;
        extra = '<div class="coverage"><i style="width:' + (cov * 100).toFixed(1) + '%"></i></div>';
      }
      if (a.state === "HEALING") {
        var cells = "";
        for (var i = 1; i <= 7; i++) {
          cells += "<i class=\"" + (i < a.heal.step ? "done" : i === a.heal.step ? "active" : "") + "\"></i>";
        }
        extra = '<div class="steps">' + cells + "</div>";
      }

      var at = a.attest;
      /* A config file claiming `de` is unfalsifiable. An ASN reading Vodafone
         rather than a datacentre, captured at the same timestamp as the buy
         control, is proof. Geo goes in the evidence on every arm, every row. */
      var attest = a.state === "WITHHELD" && !doc.global_blackout
        ? "telemetry suppressed · " + doc.swept_at.slice(11, 19) + "Z"
        : at.exit_ip + " · " + at.country + " · " + at.asn_org + " · AS" + at.asn + " · " + at.city;

      return '<div class="arm state-' + a.state + '">' +
        '<div class="arm-head">' +
          '<span class="arm-code">' + esc(a.code) + "</span>" +
          '<span class="arm-host">' + esc(a.host) + "</span>" +
          '<span class="arm-state">' + esc(a.state.replace("_", " ")) + "</span>" +
        "</div>" +
        extra +
        '<div class="arm-copy">' + armCopy(a, doc) + "</div>" +
        '<div class="arm-attest">' + esc(attest) + "</div>" +
      "</div>";
    }).join("");
  }

  // ------------------------------------------------------------- the wall

  // Display order: findings first, then by age within tier.
  //
  // The fixture generator sorts by DAY N descending alone, deliberately, so that
  // "the oldest" in the hero sentence is unambiguous and nothing is reordered to
  // flatter the claim. That reasoning holds for the hero, which is computed over
  // the qualifying RED subset and is unaffected by wall order.
  //
  // It does not hold for the ledger. Measured on the fixture: the first RED row
  // sat 2,623px down, past two and a half screens, behind 28 consecutive rows
  // reading "no machine-matchable identifier / not captured". A hazard wall whose
  // hazards are below the fold is a hazard wall nobody reads, and the headline
  // claims a number the table appears to contradict.
  //
  // Reordering here cannot flatter anything, because no row changes tier and no
  // figure is computed from this order. What would be dishonest is hiding the
  // order, so it is printed in the table header instead.
  var TIER_RANK = { RED: 0, AMBER: 1, DISCARDED: 2 };

  function displayOrder(rows) {
    return rows.slice().sort(function (a, b) {
      var ta = TIER_RANK[a.tier], tb = TIER_RANK[b.tier];
      if (ta !== tb) return ta - tb;
      if (b.days !== a.days) return b.days - a.days;
      return String(a.source.ref).localeCompare(String(b.source.ref));
    });
  }

  function renderRows(doc) {
    var rows = displayOrder(doc.rows);
    var maxDays = Math.max.apply(null, rows.map(function (r) { return r.days; }));
    var shown = rows.slice(0, PAGE_CAP);

    // Name the sort where the columns are named. A reader who can see the order
    // can check it; a reader who cannot has to trust it.
    // Findings-first ordering means a full page of RED can push every AMBER row
    // out of view, and the AMBER rows are the ones carrying "we could not check
    // this". The blindness is still reported in WHAT WE DID NOT SEE, but the
    // ledger must not imply the reader has seen the tier mix. So the header
    // states it: what is shown, out of what, and how it splits.
    var sortNote = el("sortNote");
    if (sortNote) {
      var mix = {};
      doc.rows.forEach(function (r) { mix[r.tier] = (mix[r.tier] || 0) + 1; });
      var parts = ["RED", "AMBER", "DISCARDED"].filter(function (t) { return mix[t]; })
        .map(function (t) { return mix[t] + " " + t; });
      sortNote.textContent = "sorted: confirmed first, then longest unremedied · "
        + "showing " + shown.length + " of " + doc.rows.length
        + " · " + parts.join(", ") + " · full set in the structured output";
    }

    el("wall").innerHTML = shown.map(function (r, i) {
      var ident = [r.model, r.gtin ? "GTIN " + r.gtin : null].filter(Boolean).join(" · ")
        || "no machine-matchable identifier";
      var chips = ARM_ORDER.map(function (code) {
        var v = r.arms[code];
        var glyph = v === "RED" ? code : v === "WITHHELD" ? "–" : code;
        return '<span class="chip v-' + v + '" title="' + code + " " + v + '">' + glyph + "</span>";
      }).join("");

      // The gutter shows the reader's position in the ledger, not r.rank. Rank is
      // a stable row identity assigned by the sweep and it survives on data-rank
      // for the expand handler, but printing it here after reordering produced a
      // column reading 29, 35, 30, 31, which looks like a rendering fault.
      return '<article class="row' + (r.tier === "AMBER" ? " is-amber" : "") +
        '" data-rank="' + r.rank + '" tabindex="0" role="button"' +
        ' aria-expanded="false" aria-label="' + esc(r.name) +
        ', open evidence chain">' +
        '<div class="c-gutter">' + (i + 1) +
          '<span class="open-mark" aria-hidden="true"></span></div>' +
        '<div class="c-id"><div class="name">' + esc(r.name) + "</div>" +
          '<div class="ident">' + esc(ident) + "</div></div>" +
        '<div class="c-hazard"><div class="quote">“' + esc(r.hazard) + "”</div>" +
          '<div class="src">' + esc(r.source.authority) + " " + esc(r.source.ref) +
          " · published " + esc(r.source.published) + "</div></div>" +
        '<div class="chips">' + chips + "</div>" +
        '<div class="c-bar"><div class="track"><i style="width:' +
          ((r.days / maxDays) * 100).toFixed(2) + '%"></i></div>' +
          '<div class="days' + (r.days_frozen ? " frozen" : "") + '">' + commas(r.days) + "</div></div>" +
        '<div class="c-tier"><span class="tier-box t-' + r.tier + '">' + r.tier + "</span>" +
          '<div class="cap">' + (r.evidence ? esc(r.evidence.captured_at.slice(11, 19)) + "Z" : "not captured") +
          "</div></div>" +
      "</article>";
    }).join("");

    el("pager").textContent = doc.stats.findings.footer;
    wireRows(doc);
  }

  // -------------------------------------------------- two-receipt card

  function receipt(r) {
    var e = r.evidence;
    if (!e) {
      return '<div class="receipt"><div class="receipt-grid">' +
        '<div class="receipt-pane"><h3>Regulator record</h3>' + regulatorPane(r) + "</div>" +
        '<div class="receipt-pane"><h3>Live listing</h3>' +
        '<p class="lede">No listing was confirmed for this notice. It is shown as AMBER, ' +
        "labelled unconfirmed, and excluded from every statistic on this page.</p>" +
        (r.discarded || []).map(function (d) {
          return field(d.code, d.reason);
        }).join("") + "</div></div></div>";
    }

    var a = e.assertion || {};
    var ctx = esc(a.context || "");
    if (a.needle) {
      ctx = ctx.replace(esc(a.needle), "<mark>" + esc(a.needle) + "</mark>");
    }
    var bc = e.buy_control || {};

    /* Two doors, and the order is the point.
       DOM path, response code, content hash and trace used to arrive first, in
       mono, unexplained. They are the most technical things this project owns and
       they were the first thing a reader met — which is the wrong way round. They
       are proof, and proof is what you reach for after the claim, not before it.

       So door one answers "why are you confident", in sentences. Door two is
       closed, and holds everything an auditor would reopen the case with. */
    var confidence =
      '<div class="assertion">' + ctx +
        '<span class="why">The recall names this identifier. We found that exact ' +
        "string inside the product page we fetched, not in the URL and not in the " +
        "search result — because a marketplace will quietly serve a different " +
        "product on a stale link, and a live buy button on the wrong product is " +
        "the worst mistake this system could make.</span>" +
      "</div>" +
      field("The buy control we found", bc.label, { mono: true }) +
      field("In stock", bc.in_stock === undefined ? undefined : (bc.in_stock ? "yes" : "no")) +
      field("Sold or shipped by", bc.ships_from) +
      '<div class="attest-chip">fetched from <b>' +
        esc(e.currency ? currencyCountry(e.currency) : "?") +
        "</b> · the page priced itself in <b>" + esc(e.currency || "MISSING") +
        "</b>, which is how we know which country answered</div>";

    var audit =
      '<details class="audit"><summary>Audit trail</summary>' +
      '<p class="audit-why">Everything needed to reproduce or contest this row. ' +
      "The hash pins the exact bytes we read, so a later change to the page cannot " +
      "quietly rewrite what we claimed.</p>" +
      field("Identifier searched", a.needle, { mono: true }) +
      field("Where on the page", a.dom_path, { mono: true }) +
      field("HTTP response", e.http, { mono: true }) +
      field("Content hash", e.sha256, { mono: true }) +
      field("Trace", e.trace, { mono: true }) +
      field("Job", e.job_id, { mono: true }) +
      "</details>";

    return '<div class="receipt"><div class="receipt-grid">' +
      '<div class="receipt-pane"><h3>What the regulator said</h3>' + regulatorPane(r) + "</div>" +
      '<div class="receipt-pane"><h3>What we found, ' + esc(e.captured_at) + "</h3>" +
        confidence + audit +
      "</div></div></div>";
  }

  function currencyCountry(c) { return { EUR: "DE", USD: "US", INR: "IN" }[c] || "?"; }

  function regulatorPane(r) {
    // The hazard sentence first. It is the reason anyone is reading the row, and
    // it was arriving sixth, under four lines of filing metadata.
    return '<div class="assertion">“' + esc(r.hazard) + '”' +
        '<span class="why">The regulator\'s own sentence, quoted exactly. Never ' +
        "paraphrased, never summarised, never softened.</span></div>" +
      field("Product", r.name) +
      field("Recalled by", r.source.authority === "CPSC"
        ? "US Consumer Product Safety Commission"
        : "EU Safety Gate") +
      field("On", r.source.published, { mono: true }) +
      field("Still on sale, days since", commas(r.days), { mono: true }) +
      field("Notice", r.source.ref, { mono: true }) +
      field("Model", r.model, { mono: true }) +
      field("Barcode", r.gtin, { mono: true });
  }

  function wireRows(doc) {
    var byRank = {};
    doc.rows.forEach(function (r) { byRank[r.rank] = r; });

    // Open the first row on arrival. The acceptance test for a row is that a
    // reader can check it, so the check has to be visible without being found.
    var first = document.querySelector("#wall .row");
    if (first) toggle(first, byRank[first.dataset.rank]);

    el("wall").addEventListener("click", function (ev) {
      var row = ev.target.closest(".row");
      if (!row) return;
      toggle(row, byRank[row.dataset.rank]);
    });
    el("wall").addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      var row = ev.target.closest(".row");
      if (!row) return;
      ev.preventDefault();
      toggle(row, byRank[row.dataset.rank]);
    });
  }

  function toggle(row, data) {
    var next = row.nextElementSibling;
    if (next && next.classList.contains("receipt")) {
      next.remove();
      row.classList.remove("is-open");
      row.setAttribute("aria-expanded", "false");
      return;
    }
    document.querySelectorAll(".receipt").forEach(function (n) { n.remove(); });
    document.querySelectorAll(".row.is-open").forEach(function (n) {
      n.classList.remove("is-open");
      n.setAttribute("aria-expanded", "false");
    });
    row.insertAdjacentHTML("afterend", receipt(data));
    row.classList.add("is-open");
    row.setAttribute("aria-expanded", "true");
  }

  // -------------------------------------------------------- survival curve

  /* The curve is FITTED UPSTREAM, in stats/survival.py, and rendered here from
     decided values. The wall never performs inference: what is on screen is
     exactly what examples/stats.json publishes, so a reader can recompute it. */
  function renderCurve(doc) {
    var c = doc.stats.survival_curve;
    var node = el("curve");
    if (!c || c.insufficient) {
      node.innerHTML = "<h2>Survival by age</h2>" +
        '<p class="lede">Not enough observations to fit a curve yet' +
        (c ? " (" + c.n + ")" : "") + ". A shape fitted to a handful of products " +
        "is a picture, not a finding.</p>";
      return;
    }

    var cols = c.grid.map(function (g) {
      var lo = g.ci95[0], hi = g.ci95[1];
      // Bar spans the interval, so its HEIGHT is the uncertainty. A single
      // value drawn as a point would hide how little some of these rest on.
      var top = Math.max(2, (hi - lo) * 100);
      return '<div class="curve-col' + (g.thin ? " is-thin" : "") + '">' +
        '<div class="v">' + (g.thin ? "&mdash;" : pct(g.survival)) + "</div>" +
        '<div class="curve-band" style="height:' + top.toFixed(1) + "%;margin-bottom:" +
          (lo * 100).toFixed(1) + '%" title="day ' + g.day + ": " + pct(g.survival) +
          ", CI " + pct(lo) + " to " + pct(hi) + ", block n=" + g.block_n + '"></div>' +
      "</div>";
    }).join("");

    var axis = c.grid.map(function (g) {
      return "<span>day " + g.day + (g.thin ? "" : " · n=" + g.block_n) + "</span>";
    }).join("");

    node.innerHTML =
      "<h2>Survival by age</h2>" +
      '<p class="lede">Share of recalled products still buyable, by how long ago the ' +
      "notice was published. Each bar spans the 95% interval, so its height is the " +
      "uncertainty. Hatched bars rest on too few observations to publish.</p>" +
      '<div class="curve-plot">' + cols + "</div>" +
      '<div class="curve-axis">' + axis + "</div>" +
      '<div class="curve-note"><b>' + esc(c.method) + ".</b> " + esc(c.confound) +
      " " + esc(c.interval_method) + "</div>";
  }

  // ---------------------------------------------------------------- panels

  function renderNotSeen(doc) {
    var s = doc.stats, d = s.discarded;
    var rows = Object.keys(d.by_code).map(function (k) {
      return "<dt>" + esc(k.replace(/_/g, " ")) + "</dt><dd>" + d.by_code[k] + "</dd>";
    }).join("");

    el("notSeen").innerHTML =
      "<h2>What we did not see</h2>" +
      '<p class="lede">A dashboard that only shows what it found is a dashboard that lies. ' +
      "This panel is the other half of the measurement.</p>" +
      "<dl>" + rows +
        "<dt>AMBER, shown and excluded from every statistic</dt><dd>" + s.findings.amber + "</dd>" +
        "<dt>Seeds published with no searchable identifier</dt><dd>" + s.unsearchable.n + "</dd>" +
        "<dt>Listings we estimate we never saw at all</dt><dd>≥ " +
          Math.round(s.precision.recall.missed_floor) + "</dd>" +
      "</dl>" +
      '<p class="lede" style="margin-top:16px">' + esc(s.precision.recall.note) + "</p>" +
      '<p class="lede">Adversarial precision set: ' + s.adversarial_precision_set.n +
      " deliberate near-misses fed to the matcher, " +
      (s.adversarial_precision_set.all_discarded ? "all discarded" : "ONE REACHED RED") + ". " +
      esc(s.adversarial_precision_set.note) + "</p>";
  }

  /* The prompt budgeter is deterministic and hard-capped. Fixed priority order:
     arm id, symptom deltas, sample URL, missing field list, raw snippet last.
     The snippet is last precisely because it is the first thing to be truncated. */
  function healPrompt(arm, doc) {
    var lines = [
      "arm=" + arm.code + " collector=" + arm.collector_id,
      "template=" + arm.template + " version=dev",
      "symptom: data_lines " + arm.job.data_lines + "/" + arm.job.inputs +
        " (prev 164), success_rate " + arm.job.success_rate + " (prev 0.911)",
      "detector: " + (arm.reason || "n/a"),
      "sample=https://" + arm.host + "/s?k=PS-1000",
      "missing_fields: identity_token, buy_control.label, price.currency",
      "snippet: <div class=\"s-main-slot\"><span class=\"a-price\">…</span></div>"
    ];
    var text = lines.join("\n");
    return { text: text.slice(0, 1000), used: Math.min(text.length, 1000) };
  }

  function renderHeal(doc) {
    var arm = doc.arms.filter(function (a) { return a.heal && a.heal.status !== "none"; })[0];
    var node = el("healLedger");

    if (!arm) {
      node.innerHTML = "<h2>Heal ledger</h2>" +
        '<p class="lede">No heal has been triggered this sweep. Self-healing does not fire ' +
        "automatically: it is triggered, and something has to do the detecting. That something is us.</p>";
      return;
    }

    var p = healPrompt(arm, doc);
    var h = arm.heal;
    var rejected = h.status === "rejected";
    var gate = h.status === "awaiting_approval";

    node.innerHTML =
      "<h2>Heal ledger</h2>" +
      '<p class="lede">There is no rollback endpoint. Verification sits before the commit, ' +
      "not after it, so this is approval-gated promotion and never auto-rollback.</p>" +
      '<div class="heal-entry' + (rejected ? " rejected" : "") + '">' +
        '<div class="heal-verdict">' +
          (rejected ? "HEAL REJECTED" : gate ? "AWAITING APPROVAL" : "HEAL IN FLIGHT") +
        "</div>" +
        field("Arm", arm.code) +
        field("Canaries resolved", (h.canary_pass == null ? undefined : h.canary_pass + " of " + h.canary_total)) +
        field("Production template", arm.template + (rejected ? " (unchanged)" : ""), { mono: true }) +
        field("Ledger", h.ledger, { mono: true }) +
        (rejected ? '<div class="btn-approve">Approve promotion</div>' +
          '<div class="btn-reason">Locked. ' + esc(h.failed_canary || "a negative canary did not resolve") +
          ". A heal that makes everything match is exactly as broken as one that matches nothing, " +
          "so the gate is two-sided.</div>" : "") +
        (gate ? '<div class="btn-approve">Approve promotion</div>' +
          '<div class="btn-reason">Locked until ' + h.canary_total + " of " + h.canary_total +
          " canaries resolve on version=dev.</div>" : "") +
        '<div class="budget"><div class="meter"><i style="width:' +
          ((p.used / 1000) * 100).toFixed(1) + '%"></i></div>' +
          '<div class="cap">prompt budget ' + p.used + " / 1000 characters, deterministic assembler</div></div>" +
        '<div class="prompt-box">' + esc(p.text) + "</div>" +
      "</div>";
  }

  // ------------------------------------------------------ provenance + drawer

  function renderProvenance(doc) {
    var a = doc.stats.arithmetic;
    el("provenance").innerHTML =
      '<span class="fixture-stamp">' + esc(doc.provenance.stamp) + "</span>" +
      "<span>sweep " + esc(doc.sweep_id) + "</span>" +
      "<span>" + esc(a.working) + "</span>" +
      "<span>seeds: " + esc(doc.provenance.seed_source) + "</span>";

    el("machinery").innerHTML =
      "<table><tr><th>arm</th><th>collector</th><th>template</th><th>job</th>" +
      "<th>inputs</th><th>rows</th><th>fails</th><th>page loads</th><th>exit</th></tr>" +
      doc.arms.map(function (x) {
        return "<tr><td>" + x.code + "</td><td>" + x.collector_id + "</td><td>" + x.template +
          "</td><td>" + x.job.id + "</td><td>" + x.job.inputs + "</td><td>" + x.job.data_lines +
          "</td><td>" + x.job.fails + "</td><td>" + x.job.page_loads + "</td><td>" +
          x.attest.country + " AS" + x.attest.asn + "</td></tr>";
      }).join("") + "</table>";
  }

  // ------------------------------------------------------------ loading state

  function renderLoading() {
    var skeleton = "";
    for (var i = 0; i < 12; i++) {
      skeleton += '<article class="row skeleton">' +
        '<div class="c-gutter">' + (i + 1) + "</div>" +
        '<div class="c-id"><div class="name">skeleton</div><div class="ident">skeleton</div></div>' +
        '<div class="c-hazard"><div class="quote">skeleton</div><div class="src">skeleton</div></div>' +
        '<div class="chips"><span class="chip"></span><span class="chip"></span><span class="chip"></span></div>' +
        '<div class="c-bar"><div class="track"></div><div class="days"></div></div>' +
        '<div class="c-tier"></div></article>';
    }
    el("wall").innerHTML = skeleton;
    el("verdict").innerHTML = '<p class="clause">Loading sweep 2026-08-21T14:02Z.</p>';
  }

  // ------------------------------------------------------------------- boot

  function boot() {
    var variant = new URLSearchParams(location.search).get("state") || "v1";

    if (variant === "loading") { renderLoading(); return; }

    var all = window.CANON_FIXTURES;
    if (!all) {
      el("verdict").innerHTML = "<h1>No data loaded.</h1>" +
        '<p class="sub">data/fixtures.js did not load. Run <code>python3 data/make_fixture.py</code>.</p>';
      return;
    }
    var doc = all[variant] || all.v1;

    renderVerdict(doc);
    renderFigures(doc);
    renderInstruments(doc);
    renderArms(doc);
    renderRows(doc);
    renderCurve(doc);
    renderNotSeen(doc);
    renderHeal(doc);
    renderProvenance(doc);

    animate();

    if (doc.global_blackout && doc.global_blackout.fired) {
      document.querySelectorAll(".instrument").forEach(function (n) { n.classList.add("is-struck"); });
      document.querySelectorAll(".figure").forEach(function (n) {
        n.classList.remove("is-pending");
        n.classList.add("is-withheld");
      });

      // Every figure is struck, every arm is black — and the ledger underneath
      // was still rendering exactly as it does on a good day. A reader scrolling
      // past the masthead met forty rows that looked current, in the one state
      // that exists to say we do not know.
      //
      // The rows stay on the page, because deleting them would be a different lie
      // and because a reader needs to see what the last trustworthy sweep found.
      // They are marked historical instead, which is the same treatment STALE
      // already gives them, and the reason is stated rather than implied.
      if (document.body) document.body.classList.add("is-blackout");
      var note = el("historicalNote");
      if (note) {
        note.textContent = "Rows below are frozen at the last sweep that "
          + "corroborated them and are historical, not current. No row here is a "
          + "claim about what is on sale right now.";
      }
    }
  }

  // ------------------------------------------------------------------ motion

  /* Two behaviours only, and both are about meaning rather than polish.

     A count-up turns a number into a duration: 714 arriving instantly is a fact,
     714 counting up is the time a recalled product stayed on sale. And a reveal
     on approach is what makes five acts feel like a document being read rather
     than a page being dumped.

     Everything here degrades to nothing under prefers-reduced-motion, which the
     stylesheet enforces independently — this only skips the work. */
  function reducedMotion() {
    return window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function countUp(node) {
    var to = parseFloat(node.getAttribute("data-to"));
    var suffix = node.getAttribute("data-suffix") || "";
    var decimals = (node.getAttribute("data-to") || "").indexOf(".") > -1 ? 1 : 0;
    if (isNaN(to)) return;
    if (reducedMotion()) {
      node.textContent = to.toFixed(decimals) + suffix;
      return;
    }
    var start = null, dur = 1300;
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / dur);
      // Same easing curve as the stylesheet, so type and numbers move together.
      var eased = 1 - Math.pow(1 - p, 3);
      node.textContent = (to * eased).toFixed(decimals) + suffix;
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function animate() {
    if (!("IntersectionObserver" in window)) {
      document.querySelectorAll(".count").forEach(countUp);
      return;
    }

    // The hero is already on screen, so it counts immediately.
    var hero = document.querySelector(".act-finding .count");
    if (hero) setTimeout(function () { countUp(hero); }, 380);

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add("is-in");
        e.target.querySelectorAll(".count").forEach(countUp);
        io.unobserve(e.target);      // reveal once, never again
      });
    }, { rootMargin: "-12% 0px -8% 0px", threshold: 0 });

    document.querySelectorAll(".act:not(.act-finding), .figure, .arm, .instrument")
      .forEach(function (n) { n.classList.add("reveal"); io.observe(n); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
