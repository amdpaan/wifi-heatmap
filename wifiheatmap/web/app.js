"use strict";
// wifi-heatmap dashboard. Polls /api/state; every name from the data goes in via textContent.

const $ = (id) => document.getElementById(id);
const SVGNS = "http://www.w3.org/2000/svg";
const KEY = { "great": "great", "ok": "ok", "poor": "poor", "dead zone": "dead", "unranked": "none" };
const BARS = { great: 4, ok: 3, poor: 2, dead: 1, none: 0 };
const LABELS = [["great", "great"], ["ok", "ok"], ["poor", "poor"], ["dead", "dead zone"]];

let S = null;            // last /api/state
let placing = false;     // pin mode
let timer = null;
let openId = null;       // place shown in the detail sheet

// ---------- helpers
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") Object.assign(el.style, v);   // CSSOM: the CSP blocks style attributes
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) el.append(k instanceof Node ? k : String(k));
  return el;
}
function s(tag, attrs) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  return el;
}

async function api(path, opts = {}) {
  const init = { credentials: "same-origin", method: opts.method || "GET", headers: {} };
  if (opts.json !== undefined) {
    init.method = "POST";
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.json);
  } else if (opts.file) {
    init.method = "POST";
    init.headers["Content-Type"] = opts.file.type;
    init.body = opts.file;
  }
  const r = await fetch(path, init);
  let d = {};
  try { d = await r.json(); } catch (e) { /* not JSON */ }
  if (!r.ok) { const err = new Error(d.error || r.statusText); err.status = r.status; throw err; }
  return d;
}

/** Signal-bars icon: n of 4 bars filled, in currentColor. */
function barsIcon(n) {
  const svg = s("svg", { viewBox: "0 0 16 14", class: "bars", "aria-hidden": "true" });
  [4, 7, 10, 13].forEach((ht, i) => {
    const r = s("rect", { x: i * 4, y: 14 - ht, width: 3, height: ht, rx: 1 });
    if (i >= n) r.setAttribute("class", "off"); else r.setAttribute("fill", "currentColor");
    svg.append(r);
  });
  return svg;
}
function rssiBars(rssi) {
  if (rssi == null) return 0;
  return [-80, -72, -65, -55].filter((t) => rssi >= t).length;
}
function chip(label) {
  const k = KEY[label] || "none";
  return h("span", { class: "chip s-" + k }, barsIcon(BARS[k]), h("span", null, label));
}
const fmt = {
  dbm: (v) => (v == null ? "—" : Math.round(v) + " dBm"),
  ms: (v) => (v == null ? "—" : Math.round(v) + " ms"),
  pct: (v) => (v == null ? "—" : (v < 1 && v > 0 ? v.toFixed(1) : Math.round(v)) + "%"),
  mbps: (v) => (v == null ? "no test" : (v < 10 ? v.toFixed(1) : Math.round(v)) + " Mbit/s"),
  time: (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  day: (ts) => new Date(ts * 1000).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }),
  ago: (secs) => (secs < 90 ? Math.round(secs) + " s" : Math.round(secs / 60) + " min"),
};
function byId(id) { return S && S.places.find((p) => p.id === id); }

// ---------- the antenna-bot: wifi-heatmap's own pixel mascot (16×22 grid). Letters are colours
// (style.css .bot-*); 1-4 are the chest's signal bars. The base is always drawn; each layer only draws
// the cells that differ from it ("z" paints over with the page colour), and CSS shows the layers for the mood.
const BOT = [
  "................",
  ".......tt.......",
  ".......tt.......",
  ".......aa.......",
  ".......aa.......",
  "..oooooooooooo..",
  "..obbbbbbbbbbo..",
  "..obssssssssbo..",
  "..obseesseesbo..",
  ".dobseesseesbod.",
  "..obssssssssbo..",
  "..obssmmmmssbo..",
  "..obbbbbbbbbbo..",
  "..oooooooooooo..",
  "......oddo......",
  "...oooooooooo...",
  "..dobbbbbbb4od..",
  "..dobbbbb3b4od..",
  "..oobbb2b3b4oo..",
  "...ob1b2b3b4o...",
  "...oooooooooo...",
  "....ww....ww....",
];
const BOT_LAYERS = {
  "happy": { 8: "..obsessssesbo..", 9: ".dobesessesebod.", 11: "..obsmmmmmmsbo.." },
  "worried": { 7: "..obssssssssboq.", 8: "..obssssssssboq." },
  "sad": { 9: ".dobssssssssbod.", 10: "..obssmmmmssbo..", 11: "..obsmssssmsbo.." },
  "lids": { 8: "..obssssssssbo.." },   // worried and blinking eyes: only the bottom row
  "sparks": { 0: "....y......y....", 1: "...y........y...", 3: "..y..........y.." },
  "droop": { 1: ".......zz.......", 2: ".....aaaz.......", 3: "...tt.aaz.......", 4: "...tt..aa......." },
};
const MOODS = {   // face + antenna for each mood, and what it says
  great: ["happy sparks", "sparking: a great spot"],
  ok: ["", "content: an ok spot"],
  poor: ["worried lids", "worried: a poor spot"],
  dead: ["sad droop", "drooping: a dead zone"],
  idle: ["", "waiting for some data"],
};

function drawBot() {
  const svg = s("svg", { viewBox: "0 0 16 22", "shape-rendering": "crispEdges", "aria-hidden": "true" });
  const cells = (rows, layer) => {
    const g = s("g", layer ? { class: "layer " + layer } : {});
    for (const [y, row] of Object.entries(rows)) {
      [...row].forEach((c, x) => {
        if (c === "." || (layer && BOT[y][x] === c)) return;
        g.append(s("rect", { class: "bot-" + c, x, y, width: 1.02, height: 1.02 }));
      });
    }
    return g;
  };
  svg.append(cells(BOT));
  for (const [name, rows] of Object.entries(BOT_LAYERS)) svg.append(cells(rows, name));
  $("bot").replaceChildren(svg);
}

/** mood: great/ok/poor/dead/idle; level: chest bars lit (0-4); logging: antenna blinks. */
function setBot(mood, level, logging) {
  const el = $("bot");
  el.className = "bot m-" + mood + " lv-" + level + (logging ? " logging" : "") + " "
    + MOODS[mood][0].split(" ").filter(Boolean).map((l) => "show-" + l).join(" ");
  el.setAttribute("aria-label", "The antenna-bot, " + MOODS[mood][1] + (logging ? ", logging now" : ""));
}

function botMood() {
  const lv = S.live && S.live.sample;
  if (lv) {   // logging: the face and bars follow the live signal
    const n = lv.connected ? rssiBars(lv.rssi) : 0;
    return [["dead", "dead", "poor", "ok", "great"][n], n, true];
  }
  const top = S.places.find((p) => p.score != null);
  if (!top) return ["idle", 0, !!S.live];
  const k = KEY[top.label];
  return [k, BARS[k], !!S.live];
}

// ---------- tooltip (enhances; every value is also in the table or the sheet)
const tip = $("tip");
function showTip(target, title, lines) {
  tip.replaceChildren(h("strong", null, title), ...lines.map((l) => h("div", null, l)));
  tip.hidden = false;
  const r = target.getBoundingClientRect();
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  let x = r.left + r.width / 2 - tw / 2, y = r.top - th - 10;
  if (y < 8) y = r.bottom + 10;
  x = Math.max(8, Math.min(x, window.innerWidth - tw - 8));
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
function hideTip() { tip.hidden = true; }
function tipOn(el, title, lines) {
  el.addEventListener("pointerenter", () => showTip(el, title, lines));
  el.addEventListener("pointerleave", hideTip);
  el.addEventListener("focus", () => showTip(el, title, lines));
  el.addEventListener("blur", hideTip);
}

// ---------- render
function render() {
  const ranked = S.places.filter((p) => p.score != null);
  const best = S.best.map(byId), dead = S.dead.map(byId);
  $("eyebrow").textContent = S.demo ? "wifi-heatmap · demo" : "wifi-heatmap";
  setBot(...botMood());
  $("headline").textContent = !S.places.length ? "No places yet"
    : best.length ? "Best spot: " + best[0].name
    : ranked.length ? "No great spot yet" : "Not enough data yet";
  const bits = [];
  if (S.places.length) bits.push(ranked.length + " of " + S.places.length + " places ranked");
  if (dead.length) bits.push(dead.length + " dead zone" + (dead.length === 1 ? "" : "s") + " (" + dead.map((p) => p.name).join(", ") + ")");
  if (!S.places.length) bits.push("Check in somewhere to start logging.");
  $("subtitle").textContent = bits.join(" · ");

  const note = $("notice");
  if (S.session_error) { note.textContent = S.session_error; note.className = "notice bad"; note.hidden = false; }
  else if (S.demo) { note.textContent = "Demo: a made-up campus and made-up measurements. Nothing can be changed here."; note.className = "notice"; note.hidden = false; }
  else note.hidden = true;

  $("checkin-btn").hidden = S.demo;
  $("checkin-btn").disabled = !!S.live;
  $("map-tools").hidden = S.demo;
  renderLive();
  renderMap();
  renderTable();
  if (openId && $("detail").open) loadDetail(openId, true);
}

function renderLive() {
  const lv = S.live, box = $("live");
  box.hidden = !lv;
  if (!lv) return;
  const p = byId(lv.place);
  $("live-place").textContent = "Logging at " + (p ? p.name : lv.place);
  const st = $("live-stats");
  const smp = lv.sample;
  const parts = [];
  if (smp && smp.connected) {
    parts.push(h("span", null, barsIcon(rssiBars(smp.rssi))), h("span", null, fmt.dbm(smp.rssi)),
      h("span", null, "ping " + fmt.ms(smp.ping_ms)), h("span", null, "loss " + fmt.pct(smp.loss)));
  } else if (smp) parts.push(h("span", null, "Not connected to Wi-Fi"));
  else parts.push(h("span", null, lv.speed ? "Starting…" : "Speed test running…"));
  if (lv.speed && lv.speed.dl_mbps != null) parts.push(h("span", null, fmt.mbps(lv.speed.dl_mbps) + " down"));
  parts.push(h("span", null, lv.samples + " samples · " + fmt.ago(S.now - lv.since)));
  st.replaceChildren(...parts);
  const stop = $("stop-btn");
  stop.hidden = lv.owner !== "web";
  if (lv.owner === "terminal") st.append(h("span", null, "· from the terminal (stop it there)"));
}

function renderMap() {
  const has = !!S.map;
  $("map").hidden = !has;
  $("map-empty").hidden = has || S.demo;
  $("pin-btn").hidden = !has;
  const img = $("map-img");
  if (has && img.dataset.src !== S.map.url) {
    img.dataset.src = S.map.url;
    img.onload = drawOverlay;
    img.src = S.map.url;
  } else if (has && img.complete) drawOverlay();
  const lg = $("legend");
  lg.replaceChildren(...LABELS.map(([, label]) => chip(label)), chip("unranked"),
    h("span", null, "Glow and pin colour show the score; the number is the score (0–100)."));
}

function drawOverlay() {
  const img = $("map-img");
  const W = img.naturalWidth || 1000, H = img.naturalHeight || 640;
  const svg = $("heat");
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  svg.replaceChildren();
  const defs = s("defs");
  for (const [k] of LABELS) {
    const g = s("radialGradient", { id: "g-" + k });
    [[0, 0.5], [0.55, 0.18], [1, 0]].forEach(([o, a]) => {
      const st = s("stop", { offset: o });
      st.style.setProperty("stop-color", "var(--" + k + ")");
      st.style.setProperty("stop-opacity", a);
      g.append(st);
    });
    defs.append(g);
  }
  svg.append(defs);
  const pins = $("pins");
  pins.replaceChildren();
  const placed = S.places.filter((p) => p.pin);
  // weakest drawn first, so a strong spot's glow sits on top
  for (const p of [...placed].sort((a, b) => (a.score ?? -1) - (b.score ?? -1))) {
    const k = KEY[p.label] || "none";
    if (p.score != null) {
      svg.append(s("circle", { cx: p.pin.x * W, cy: p.pin.y * H, r: 0.1 * W, fill: "url(#g-" + k + ")" }));
    }
  }
  for (const p of placed) {
    const k = KEY[p.label] || "none";
    const live = S.live && S.live.place === p.id;
    const b = h("button", {
      class: "pin s-" + k + (live ? " live-pin" : ""), type: "button",
      style: { left: p.pin.x * 100 + "%", top: p.pin.y * 100 + "%" },
      "aria-label": p.name + ": " + (p.score != null ? "score " + p.score + ", " + p.label : "not ranked yet"),
      onclick: () => { if (!placing) openDetail(p.id); },
    }, h("b", null, p.score != null ? p.score : "–"));
    tipOn(b, p.name, p.score != null
      ? [p.score + " · " + p.label, fmt.dbm(p.rssi) + " · p90 " + fmt.ms(p.ping_p90) + " · " + fmt.pct(p.loss) + " loss"]
      : [p.samples + " of " + S.min_samples + " samples needed"]);
    pins.append(b);
  }
}

function renderTable() {
  const tbody = $("rows");
  const ranked = S.places.filter((p) => p.score != null);
  const waiting = S.places.filter((p) => p.score == null);
  tbody.replaceChildren(...ranked.map((p, i) => h("tr", null,
    h("td", { class: "rank" }, i + 1),
    h("td", null, h("button", { class: "link", type: "button", onclick: () => openDetail(p.id) }, p.name)),
    h("td", null, h("div", { class: "score-cell" }, h("strong", null, p.score), chip(p.label))),
    h("td", { class: "num" }, fmt.dbm(p.rssi)),
    h("td", { class: "num" }, fmt.ms(p.ping_p90)),
    h("td", { class: "num" }, fmt.pct(p.loss)),
    h("td", { class: "num" }, fmt.mbps(p.dl_mbps)),
    h("td", { class: "why" }, p.why || ""),
  )));
  $("rank-table").hidden = !ranked.length;
  const empty = $("rank-empty");
  empty.hidden = !!ranked.length;
  empty.textContent = S.places.length
    ? "Nothing ranked yet: a place needs " + S.min_samples + " samples (1 minute of logging)."
    : "No places yet. Press Check in, or run: wifi-heatmap log --place \"Library L2\"";
  const w = $("waiting");
  w.hidden = !waiting.length;
  w.replaceChildren("Not ranked yet (needs " + S.min_samples + " samples): ",
    ...waiting.flatMap((p, i) => [i ? ", " : "", h("button", { class: "link", type: "button", onclick: () => openDetail(p.id) }, p.name), " (" + p.samples + ")"]));
}

// ---------- detail sheet
async function openDetail(id) {
  openId = id;
  $("detail-body").replaceChildren(h("p", { class: "hint" }, "Loading…"));
  if (!$("detail").open) $("detail").showModal();
  await loadDetail(id);
}

async function loadDetail(id, quiet) {
  let d;
  try { d = await api("/api/places/" + encodeURIComponent(id)); }
  catch (e) { if (!quiet) $("detail-body").replaceChildren(h("p", { class: "form-error" }, e.message)); return; }
  if (openId !== id) return;
  const body = $("detail-body");
  const head = h("div", { class: "dlg-head" },
    h("div", null, h("h2", { id: "d-name" }, d.name),
      h("p", { class: "sub" }, d.samples + " samples over " + d.sessions + " visit" + (d.sessions === 1 ? "" : "s")
        + (d.first ? " · first " + fmt.day(d.first) + ", last " + fmt.day(d.last) : ""))),
    h("button", { class: "icon-btn close", type: "button", "aria-label": "Close", onclick: () => $("detail").close() }, "✕"));

  const hero = d.score != null
    ? h("div", { class: "hero-score" }, h("span", { class: "big" }, d.score), chip(d.label),
      d.why ? h("span", { class: "why" }, d.why) : null)
    : h("p", { class: "hint" }, "Not ranked yet: " + d.samples + " of " + S.min_samples + " samples. Log here for a minute.");

  const names = { signal: "Signal", latency: "Latency", loss: "Loss", speed: "Speed" };
  const parts = d.score != null ? h("div", { class: "parts", role: "list", "aria-label": "Score parts" },
    ...Object.keys(names).map((k) => {
      const v = d.parts[k];
      return h("div", { class: "part" + (v == null ? " missing" : ""), role: "listitem" },
        h("span", { class: "lbl" }, names[k]),
        h("span", { class: "track" }, v == null ? null : h("span", { class: "fill", style: { width: v + "%" } })),
        h("span", { class: "val" }, v == null ? "—" : Math.round(v)));
    }),
    d.parts.speed == null ? h("p", { class: "hint" }, "No speed test here yet, so the score uses the other three.") : null) : null;

  const stat = (k, v) => h("div", null, h("dt", null, k), h("dd", null, v));
  const stats = h("dl", { class: "stats" },
    stat("Median signal", fmt.dbm(d.rssi)), stat("SNR", d.snr == null ? "—" : Math.round(d.snr) + " dB"),
    stat("Median ping", fmt.ms(d.ping_ms)), stat("p90 ping", fmt.ms(d.ping_p90)),
    stat("Packet loss", fmt.pct(d.loss)), stat("Connected", Math.round(d.connected * 100) + "% of samples"),
    stat("Download", fmt.mbps(d.dl_mbps)), stat("Upload", fmt.mbps(d.ul_mbps)),
    stat("Speed tests", d.speedtests), stat("Access points", d.aps || "—"),
    stat("Bands", d.bands.length ? d.bands.join(", ") : "—"));

  const sessions = d.recent.length ? h("div", null, h("h3", null, "Recent visits"),
    h("ul", { class: "sessions" }, ...d.recent.map((r) => h("li", null,
      h("span", null, fmt.day(r.start)),
      h("span", null, r.samples + " samples · " + fmt.dbm(r.rssi) + " · ping " + fmt.ms(r.ping_ms)))))) : null;

  const actions = S.demo ? null : h("div", { class: "dlg-actions" },
    S.map ? h("button", { class: "btn ghost small", type: "button", onclick: () => { $("detail").close(); startPlacing(d.id); } },
      d.pin ? "Move pin" : "Place pin") : null,
    h("button", { class: "btn ghost small", type: "button", onclick: () => rename(d) }, "Rename"));

  body.replaceChildren(...[head, hero, parts, stats, hoursChart(d.hours), sessions, actions].filter(Boolean));
}

function hoursChart(hours) {
  const wrap = h("div", { class: "hours" }, h("h3", null, "Score by hour of day"));
  if (!hours.length) { wrap.append(h("p", { class: "hint" }, "No samples yet.")); return wrap; }
  const lo = Math.min(7, ...hours.map((x) => x.hour)), hi = Math.max(23, ...hours.map((x) => x.hour + 1));
  const W = 560, H = 150, L = 28, B = 22, T = 6;
  const bw = (W - L) / (hi - lo);
  const y = (v) => T + (H - T - B) * (1 - v / 100);
  const svg = s("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Score for each hour of the day with samples" });
  for (const v of [0, 50, 100]) {
    svg.append(s("line", { class: "grid", x1: L, x2: W, y1: y(v), y2: y(v) }));
    const t = s("text", { class: "tick", x: L - 6, y: y(v) + 4, "text-anchor": "end" }); t.textContent = v; svg.append(t);
  }
  for (let hr = lo; hr <= hi; hr += 3) {
    const t = s("text", { class: "tick", x: L + (hr - lo) * bw, y: H - 6, "text-anchor": "middle" });
    t.textContent = String(hr).padStart(2, "0") + ":00"; svg.append(t);
  }
  let few = false;
  for (const x of hours) {
    const x0 = L + (x.hour - lo) * bw + 1, w = Math.max(2, bw - 2);   // 2px gap between bars
    const v = x.score;
    const lines = [x.samples + " samples", fmt.dbm(x.rssi) + " · p90 " + fmt.ms(x.ping_p90) + " · " + fmt.pct(x.loss) + " loss"];
    const label = String(x.hour).padStart(2, "0") + ":00–" + String(x.hour + 1).padStart(2, "0") + ":00";
    const hit = s("rect", { class: "hit", x: x0 - 1, y: T, width: bw, height: H - T - B, tabindex: 0,
      "aria-label": label + ": " + (v == null ? "too few samples" : "score " + v) });
    hit.addEventListener("pointerenter", () => showTip(hit, v == null ? "Too few samples" : "Score " + v, [label, ...lines]));
    hit.addEventListener("pointerleave", hideTip);
    hit.addEventListener("focus", () => showTip(hit, v == null ? "Too few samples" : "Score " + v, [label, ...lines]));
    hit.addEventListener("blur", hideTip);
    svg.append(hit);
    if (v == null) {
      few = true;
      svg.append(s("rect", { class: "few", x: x0 + 0.75, y: y(8), width: w - 1.5, height: y(0) - y(8), rx: 2 }));
    } else {
      const top = y(Math.max(v, 2));
      // rounded top, square base: a 4px-radius path anchored to the baseline
      const r = Math.min(4, w / 2, y(0) - top);
      const d = "M" + x0 + "," + y(0) + "V" + (top + r) + "Q" + x0 + "," + top + " " + (x0 + r) + "," + top
        + "H" + (x0 + w - r) + "Q" + (x0 + w) + "," + top + " " + (x0 + w) + "," + (top + r) + "V" + y(0) + "Z";
      svg.append(s("path", { d, class: "b" }));
    }
  }
  wrap.append(svg);
  if (few) wrap.append(h("p", { class: "note" }, "Outlined hours have fewer than 6 samples, so no score yet."));
  const tbl = h("table", null, h("thead", null, h("tr", null, ...["Hour", "Score", "Samples", "Signal", "p90 ping", "Loss"].map((t) => h("th", null, t)))),
    h("tbody", null, ...hours.map((x) => h("tr", null,
      h("td", null, String(x.hour).padStart(2, "0") + ":00"), h("td", null, x.score == null ? "—" : x.score),
      h("td", null, x.samples), h("td", null, fmt.dbm(x.rssi)), h("td", null, fmt.ms(x.ping_p90)), h("td", null, fmt.pct(x.loss))))));
  wrap.append(h("details", null, h("summary", null, "Show as a table"), h("div", { class: "table-wrap" }, tbl)));
  return wrap;
}

async function rename(d) {
  const name = prompt("New name for " + d.name + " (its history is kept):", d.name);
  if (!name || name === d.name) return;
  try { await api("/api/places/" + d.id, { json: { name } }); await refresh(); loadDetail(d.id); }
  catch (e) { alert(e.message); }
}

// ---------- pins
function startPlacing(id) {
  placing = true;
  const sel = $("pin-place");
  sel.replaceChildren(...S.places.map((p) => h("option", { value: p.id }, p.name + (p.pin ? "" : " (no pin yet)"))));
  if (id) sel.value = id;
  else { const first = S.places.find((p) => !p.pin); if (first) sel.value = first.id; }
  $("pin-bar").hidden = false;
  $("map").classList.add("placing");
  $("map").scrollIntoView({ behavior: "smooth", block: "center" });
}
function stopPlacing() {
  placing = false;
  $("pin-bar").hidden = true;
  $("map").classList.remove("placing");
}
$("pin-btn").addEventListener("click", () => (placing ? stopPlacing() : startPlacing()));
$("pin-done").addEventListener("click", stopPlacing);
$("pin-clear").addEventListener("click", async () => {
  try { await api("/api/places/" + $("pin-place").value, { json: { pin: null } }); await refresh(); }
  catch (e) { alert(e.message); }
});
$("map").addEventListener("click", async (ev) => {
  if (!placing) return;
  const r = $("map-img").getBoundingClientRect();
  const x = (ev.clientX - r.left) / r.width, y = (ev.clientY - r.top) / r.height;
  if (x < 0 || x > 1 || y < 0 || y > 1) return;
  const sel = $("pin-place");
  try {
    await api("/api/places/" + sel.value, { json: { pin: { x, y } } });
    await refresh();
    const next = S.places.find((p) => !p.pin);   // move on to the next place without a pin
    startPlacing(next ? next.id : sel.value);
  } catch (e) { alert(e.message); }
});

$("map-file").addEventListener("change", async (ev) => {
  const f = ev.target.files[0];
  ev.target.value = "";
  if (!f) return;
  try { await api("/api/map", { file: f }); await refresh(); if (S.places.some((p) => !p.pin)) startPlacing(); }
  catch (e) { alert("Couldn't use that map: " + e.message); }
});

// ---------- check in / stop
const ci = $("checkin");
$("checkin-btn").addEventListener("click", () => {
  $("ci-places").replaceChildren(...S.places.map((p) => h("option", { value: p.name })));
  $("ci-error").hidden = true; $("ci-new-row").hidden = true; $("ci-new").checked = false;
  ci.showModal();
  $("ci-place").focus();
});
$("checkin-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const go = $("ci-go");
  go.disabled = true;
  try {
    await api("/api/checkin", { json: { place: $("ci-place").value, speedtest: $("ci-speed").checked, new: $("ci-new").checked } });
    ci.close();
    await refresh();
  } catch (e) {
    $("ci-error").textContent = e.message; $("ci-error").hidden = false;
    if (/Did you mean/.test(e.message)) $("ci-new-row").hidden = false;
  } finally { go.disabled = false; }
});
$("stop-btn").addEventListener("click", async () => {
  const b = $("stop-btn");
  b.disabled = true;
  try { await api("/api/checkout", { json: {} }); await refresh(); }
  catch (e) { alert(e.message); }
  finally { b.disabled = false; }
});
document.addEventListener("click", (ev) => {
  const c = ev.target.closest("[data-close]");
  if (c) c.closest("dialog").close();
});
$("detail").addEventListener("close", () => { openId = null; hideTip(); });
for (const d of document.querySelectorAll("dialog")) {
  d.addEventListener("click", (ev) => { if (ev.target === d) d.close(); });   // click the backdrop
}

// ---------- theme
function setTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  try { if (t) localStorage.setItem("theme", t); else localStorage.removeItem("theme"); } catch (e) { /* private mode */ }
}
try { const t = localStorage.getItem("theme"); if (t) setTheme(t); } catch (e) { /* ignore */ }
$("theme-btn").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  setTheme(dark ? "light" : "dark");
});

// ---------- polling
async function refresh() {
  try {
    S = await api("/api/state");
    render();
  } catch (e) {
    $("notice").textContent = "Can't reach wifi-heatmap: " + e.message + ". Is `wifi-heatmap serve` still running?";
    $("notice").className = "notice bad"; $("notice").hidden = false;
  }
  clearTimeout(timer);
  timer = setTimeout(refresh, S && S.live ? 5000 : 30000);
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
drawBot();
window.addEventListener("resize", hideTip);
refresh();
