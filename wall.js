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

  function renderVerdict(doc) {
    var node = el("verdict");
    var withheld = doc.arms.filter(function (a) { return a.state === "WITHHELD"; });
    var blackout = doc.global_blackout && doc.global_blackout.fired;
    var hero = doc.stats.hero;

    if (blackout) {
      node.className = "verdict is-withheld";
      node.innerHTML =
        '<span class="withheld-mark">VERDICT WITHHELD · ALL ARMS</span>' +
        "<h1>We do not know, so we will not say.</h1>" +
        '<p class="sub">' + esc(doc.global_blackout.copy) + "</p>" +
        '<p class="clause">implausible_cleanliness fired: observed drop ' +
        pct(doc.global_blackout.observed_drop) + " against a " +
        pct(doc.global_blackout.threshold) + " threshold. " +
        "Every figure on this page is struck until a sweep corroborates it.</p>";
      return;
    }

    if (withheld.length) {
      var a = withheld[0];
      node.className = "verdict is-withheld";
      node.innerHTML =
        '<span class="withheld-mark">VERDICT WITHHELD</span>' +
        "<h1>" + esc(hero.sentence) + "</h1>" +
        '<p class="sub">' + esc(a.code) + " collector unhealed since " +
        esc(doc.swept_at.slice(11, 16)) + " UTC. We do not know, so we will not say.</p>" +
        '<p class="clause">' + doc.stats.arms_measured.n + " of " + doc.stats.arms_measured.d +
        " arms measured. Figures that depend on " + esc(a.code) +
        " are struck. Figures computed from the seed corpus are not.</p>";
      return;
    }

    node.className = "verdict";
    node.innerHTML =
      "<h1>" + esc(hero.sentence) + "</h1>" +
      '<p class="sub">Every row below is a government recall notice matched to a live marketplace listing, ' +
      "with the product identifier re-asserted from the fetched page at capture time.</p>" +
      '<p class="clause">' + doc.stats.arms_measured.n + " of " + doc.stats.arms_measured.d + " arms measured.</p>";
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

    out.push(instrument("Survival", pct(s.survival.v),
      s.survival.n + " of " + s.survival.d + " · " + ci(s.survival.ci95), struck(s.survival)));

    if (s.border_escape.v === null) {
      out.push(instrument("Border escape", "PENDING",
        esc(s.border_escape.pending.slice(0, 64)) + "…", "is-pending"));
    } else {
      out.push(instrument("Border escape", pct(s.border_escape.v),
        s.border_escape.n + " of " + s.border_escape.d + " · " + ci(s.border_escape.ci95),
        struck(s.border_escape)));
    }

    out.push(instrument("Unsearchable", pct(s.unsearchable.v),
      s.unsearchable.n + " of " + s.unsearchable.d + " · " + ci(s.unsearchable.ci95), ""));

    /* Precision carries its interval next to the number it qualifies, never in a
       footnote. Recall is not directly measured: capture-recapture across the two
       query strategies puts a floor under what we missed. */
    var rc = s.precision.recall;
    out.push(instrument("Precision", pct(s.precision.v),
      s.precision.n + " of " + s.precision.d + " hand-verified · " + ci(s.precision.ci95)));
    out.push(instrument("Recall, floor", "≥ " + Math.round(rc.missed_floor) + " missed",
      "capture-recapture, " + esc(rc.estimator.split(" ")[0]) + " · lower bound"));

    out.push(instrument("Arms measured", s.arms_measured.n + " of " + s.arms_measured.d,
      doc.arms.map(function (a) { return a.code + " " + a.state.toLowerCase(); }).join(" · ")));

    out.push(instrument("Last sweep", '<span style="font-size:12px">' +
      esc(freshness(doc.swept_at)) + "</span>",
      "freshness bound " + doc.freshness_bound_s / 3600 + "h"));

    out.push(instrument("Credits", commas(s.credits.used),
      "of " + commas(s.credits.cap) + " · " + commas(s.credits.code) + " code, " +
      commas(s.credits.browser) + " browser"));

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
        '" data-rank="' + r.rank + '" tabindex="0">' +
        '<div class="c-gutter">' + (i + 1) + "</div>" +
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

    return '<div class="receipt"><div class="receipt-grid">' +
      '<div class="receipt-pane"><h3>Regulator record</h3>' + regulatorPane(r) + "</div>" +
      '<div class="receipt-pane"><h3>Live listing, captured ' + esc(e.captured_at) + "</h3>" +
        field("Identifier searched", a.needle, { mono: true }) +
        field("DOM path", a.dom_path, { mono: true }) +
        '<div class="assertion">' + ctx +
          '<span class="why">Identity re-assertion. Amazon substitutes ASINs on stale URLs, so a live ' +
          "buy control on the wrong product would score as a hazard still on sale. That is the worst " +
          "mistake this system could make, so the identifier must reappear on the fetched page itself.</span>" +
        "</div>" +
        field("Buy control", bc.label, { mono: true }) +
        field("In stock", bc.in_stock === undefined ? undefined : String(bc.in_stock)) +
        field("Ships from", bc.ships_from, { mono: true }) +
        (bc.present ? '<div class="buy">' + esc(bc.label || "buy control present") + "</div>" : "") +
        '<div class="attest-chip">exit country <b>' + esc(e.currency ? currencyCountry(e.currency) : "?") +
          "</b> · page currency <b>" + esc(e.currency || "MISSING") + "</b></div>" +
        field("Response", e.http, { mono: true }) +
        field("Content hash", e.sha256, { mono: true }) +
        field("Trace", e.trace, { mono: true }) +
      "</div></div></div>";
  }

  function currencyCountry(c) { return { EUR: "DE", USD: "US", INR: "IN" }[c] || "?"; }

  function regulatorPane(r) {
    return field("Authority", r.source.authority) +
      field("Notice", r.source.ref, { mono: true }) +
      field("Published", r.source.published, { mono: true }) +
      field("Product", r.name) +
      field("Model", r.model, { mono: true }) +
      field("GTIN", r.gtin, { mono: true }) +
      '<div class="assertion">“' + esc(r.hazard) + '”' +
        '<span class="why">The regulator\'s own sentence, quoted exactly. Never paraphrased, ' +
        "never summarised, never softened.</span></div>" +
      field("Days unremedied", commas(r.days), { mono: true });
  }

  function wireRows(doc) {
    var byRank = {};
    doc.rows.forEach(function (r) { byRank[r.rank] = r; });

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
    if (next && next.classList.contains("receipt")) { next.remove(); return; }
    document.querySelectorAll(".receipt").forEach(function (n) { n.remove(); });
    row.insertAdjacentHTML("afterend", receipt(data));
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
    renderInstruments(doc);
    renderArms(doc);
    renderRows(doc);
    renderCurve(doc);
    renderNotSeen(doc);
    renderHeal(doc);
    renderProvenance(doc);

    if (doc.global_blackout && doc.global_blackout.fired) {
      document.querySelectorAll(".instrument").forEach(function (n) { n.classList.add("is-struck"); });

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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
