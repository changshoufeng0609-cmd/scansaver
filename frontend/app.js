/* ScanSaver frontend — voice-first single page.
   Element IDs are the contract with the backend integration: never rename. */

const $ = (id) => document.getElementById(id);

// Flicker fix: skip innerHTML writes when content is unchanged, so poll loops
// never replay entry animations or reset scroll positions.
const _htmlCache = {};
function setHTML(id, html) {
  if (_htmlCache[id] === html) return false;
  _htmlCache[id] = html;
  $(id).innerHTML = html;
  return true;
}

// Every backend/transcript-derived string is untrusted (live phone audio).
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

const fmt = (n) => "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

let specId = null;
let specConfirmed = false;
let baselineLoaded = false;   // first /api/specs/latest fetch = baseline, no auto-confirm
let lineItemLabels = {};
let estimatorAgentId = null;
let agentDisplayName = "estimator";

function reveal(id) {
  const el = $(id);
  if (el.hidden) el.hidden = false;
}

/* ================= voice module ================= */

let conv = null;
let vizMode = "idle";          // idle | listening | speaking

function setVoiceStatus(t) { $("voice-status").textContent = t; }

function addCaption(source, message) {
  const you = source === "user";
  const line = document.createElement("div");
  line.className = "cap-line";
  line.innerHTML =
    `<span class="cap-chip ${you ? "you" : "agent"}">${you ? "you" : esc(agentDisplayName)}</span>` +
    `<span class="cap-text">${esc(message)}</span>`;
  $("captions").appendChild(line);
  $("captions").scrollTop = $("captions").scrollHeight;
}

async function toggleVoice() {
  if (conv) { try { await conv.endSession(); } catch (e) { /* already closed */ } return; }
  if (!estimatorAgentId) {
    setVoiceStatus("estimator agent not provisioned — run setup_agents");
    return;
  }
  setVoiceStatus("connecting…");
  try {
    // JS SDK (not the <elevenlabs-convai> widget: it can't be centered and
    // hides its transcript). The agent must be public.
    const { Conversation } =
      await import("https://cdn.jsdelivr.net/npm/@elevenlabs/client/+esm");
    await navigator.mediaDevices.getUserMedia({ audio: true });
    conv = await Conversation.startSession({
      agentId: estimatorAgentId,
      onConnect: () => {
        document.body.classList.add("voice-live");
        vizMode = "listening";
        setVoiceStatus("listening…");
      },
      onDisconnect: () => {
        conv = null;
        vizMode = "idle";
        document.body.classList.remove("voice-live");
        pollSpecAfterCall();
      },
      onModeChange: ({ mode }) => {
        vizMode = mode === "speaking" ? "speaking" : "listening";
        setVoiceStatus(mode === "speaking" ? "agent speaking…" : "listening…");
      },
      onMessage: ({ message, source }) => addCaption(source, message),
      onError: (e) => { console.error("conversation error", e); },
    });
  } catch (e) {
    console.error("voice SDK failed, falling back to widget", e);
    conv = null;
    setVoiceStatus("voice sdk unavailable — using fallback widget");
    fallbackWidget();
  }
}
$("talk-btn").onclick = toggleVoice;

function fallbackWidget() {
  if ($("widget-mount").childElementCount) { $("widget-mount").hidden = false; return; }
  const w = document.createElement("elevenlabs-convai");
  w.setAttribute("agent-id", estimatorAgentId || "");
  $("widget-mount").appendChild(w);
  const s = document.createElement("script");
  s.src = "https://unpkg.com/@elevenlabs/convai-widget-embed";
  s.async = true;
  document.body.appendChild(s);
  $("widget-mount").hidden = false;
}

// The Estimator's submit_spec server tool can land after the socket closes,
// so retry the latest-spec endpoint for a bit after every disconnect.
async function pollSpecAfterCall() {
  setVoiceStatus("call ended — fetching your spec…");
  for (let i = 0; i < 6; i++) {
    await sleep(2000);
    if (await loadLatest()) { setVoiceStatus("spec captured ✓"); return; }
  }
  setVoiceStatus("tap to talk");
}

/* ---------- circular visualizer ---------- */

const vizCanvas = $("viz-canvas");
const vctx = vizCanvas.getContext("2d");
const BAR_COUNT = 72;
let freqBuf = new Uint8Array(128);

function vizGradient() {
  const g = vctx.createLinearGradient(0, vizCanvas.height, vizCanvas.width, 0);
  g.addColorStop(0, "#fc4c02");
  g.addColorStop(0.5, "#ef2cc1");
  g.addColorStop(1, "#bdbbff");
  return g;
}
const vizStroke = vizGradient();

function drawViz(now) {
  const W = vizCanvas.width, H = vizCanvas.height;
  const cx = W / 2, cy = H / 2;
  const inner = 74;               // just outside the 92px talk button
  vctx.clearRect(0, 0, W, H);
  vctx.lineWidth = 3;
  vctx.lineCap = "round";
  vctx.strokeStyle = vizStroke;

  let levels;
  if (vizMode !== "idle" && conv) {
    const data = vizMode === "speaking"
      ? conv.getOutputByteFrequencyData()
      : conv.getInputByteFrequencyData();
    if (data && data.length) freqBuf = data;
    levels = (i) => {
      const v = freqBuf[Math.floor(i * freqBuf.length / BAR_COUNT / 2)] || 0;
      return 4 + (v / 255) * 46;
    };
    vctx.globalAlpha = 1;
  } else {
    // idle: gentle breathing sine ripple at 50% alpha
    const t = now / 900;
    levels = (i) => 6 + (reducedMotion.matches ? 0 : 5 * (1 + Math.sin(t + i * 0.35)));
    vctx.globalAlpha = 0.5;
  }

  for (let i = 0; i < BAR_COUNT; i++) {
    const a = (i / BAR_COUNT) * Math.PI * 2 - Math.PI / 2;
    const len = levels(i);
    vctx.beginPath();
    vctx.moveTo(cx + Math.cos(a) * inner, cy + Math.sin(a) * inner);
    vctx.lineTo(cx + Math.cos(a) * (inner + len), cy + Math.sin(a) * (inner + len));
    vctx.stroke();
  }
  vctx.globalAlpha = 1;

  if (reducedMotion.matches && vizMode === "idle") return; // static ring, stop looping
  requestAnimationFrame(drawViz);
}
requestAnimationFrame(drawViz);
reducedMotion.addEventListener("change", () => requestAnimationFrame(drawViz));

/* ================= spec ================= */

function renderSpecSheet(spec) {
  const cells = Object.entries(spec || {}).map(([k, v]) => {
    const val = (v && typeof v === "object")
      ? (Array.isArray(v) ? v.map((x) => typeof x === "object" ? JSON.stringify(x) : x).join(", ")
                          : JSON.stringify(v))
      : String(v ?? "—");
    return `<div class="spec-kv"><div class="k">${esc(k.replaceAll("_", " "))}</div>` +
           `<div class="v">${esc(val)}</div></div>`;
  }).join("");
  setHTML("spec-sheet", cells || `<div class="empty">empty spec</div>`);
}

async function confirmSpec(id) {
  await fetch(`/api/specs/${id}/confirm`, { method: "POST" });
  specConfirmed = true;
  $("spec-status").textContent = `spec ${id} · confirmed ✓`;
  reveal("results-section");
  reveal("report-section");
}

// Returns true when a spec exists. New specs (after the initial baseline)
// auto-confirm and reveal the downstream sections — no confirm button in the
// happy path.
async function loadLatest() {
  let data;
  try { data = await (await fetch("/api/specs/latest")).json(); }
  catch (e) { return false; }
  if (!data.spec) {
    baselineLoaded = true;
    $("spec-status").textContent = "no spec yet";
    return false;
  }
  const isNew = data.id !== specId;
  specId = data.id;
  specConfirmed = !!data.confirmed;
  renderSpecSheet(data.spec);
  // don't clobber the textarea while the user is editing it
  if (isNew || document.activeElement !== $("spec-json"))
    $("spec-json").value = JSON.stringify(data.spec, null, 2);
  reveal("spec-section");
  if (specConfirmed) { reveal("results-section"); reveal("report-section"); }
  $("spec-status").textContent =
    `spec ${specId} ${specConfirmed ? "· confirmed ✓" : "· draft"}`;

  if (isNew && baselineLoaded) {
    if (!specConfirmed) await confirmSpec(specId);
    $("spec-section").scrollIntoView({
      behavior: reducedMotion.matches ? "auto" : "smooth", block: "start",
    });
  }
  baselineLoaded = true;
  return true;
}
setInterval(loadLatest, 4000);
$("load-latest-btn").onclick = loadLatest;

$("confirm-btn").onclick = async () => {
  let spec;
  try { spec = JSON.parse($("spec-json").value); }
  catch { return alert("Spec is not valid JSON"); }
  if (!specId) {
    const res = await (await fetch("/api/specs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec }),
    })).json();
    specId = res.spec_id;
  } else {
    await fetch(`/api/specs/${specId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec }),
    });
  }
  renderSpecSheet(spec);
  await confirmSpec(specId);
};

/* ---------- document path (same spec schema) ---------- */

$("add-doc-btn").onclick = () => $("doc-file").click();
$("doc-file").onchange = () => { if ($("doc-file").files[0]) parseDocument(); };
$("parse-btn").onclick = parseDocument;

async function parseDocument() {
  const f = $("doc-file").files[0];
  if (!f) return alert("Choose a file first");
  setVoiceStatus("parsing document…");
  const fd = new FormData();
  fd.append("file", f);
  const r = await fetch("/api/parse-document", { method: "POST", body: fd });
  const res = await r.json();
  if (!r.ok) {
    setVoiceStatus("document rejected");
    $("spec-status").textContent = `✗ ${res.detail}`;
    reveal("spec-section");
    return;
  }
  specId = res.spec_id;
  renderSpecSheet(res.spec);
  $("spec-json").value = JSON.stringify(res.spec, null, 2);
  reveal("spec-section");
  setVoiceStatus("spec captured ✓");
  await confirmSpec(specId);
  $("spec-section").scrollIntoView({
    behavior: reducedMotion.matches ? "auto" : "smooth", block: "start",
  });
}

/* ================= market + calls ================= */

async function startCall(to, facility, negotiate) {
  $("call-status").textContent = `dialing ${facility}…`;
  try {
    const res = await fetch("/api/calls/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to_number: to, facility_name: facility, negotiate }),
    });
    const data = await res.json();
    $("call-status").textContent = res.ok
      ? `ringing ${facility} — ${data.conversation_id}` : `error: ${data.detail}`;
  } catch (e) { $("call-status").textContent = "error: " + e; }
}

function renderMarket(market) {
  setHTML("market-rows", (market || []).map((cp) => {
    const phone = cp.phone || "";
    return `<li>
      <span class="fac">${esc(cp.facility_name)}</span>
      <span class="dots"></span>
      <span>${esc(phone) || "no number set"}</span>
      <button class="btn btn-primary" data-call data-phone="${esc(phone)}"
        data-facility="${esc(cp.facility_name)}" ${phone ? "" : "disabled"}>call</button>
      <button class="btn btn-ghost" data-call data-negotiate="1" data-phone="${esc(phone)}"
        data-facility="${esc(cp.facility_name)}" ${phone ? "" : "disabled"}>negotiate</button>
    </li>`;
  }).join(""));
}
$("market-rows").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-call]");
  if (!b || b.disabled) return;
  startCall(b.dataset.phone, b.dataset.facility, !!b.dataset.negotiate);
});

$("call-btn").onclick = () => {
  const to = $("call-to").value.trim();
  const facility = $("call-facility").value.trim();
  if (!to.startsWith("+")) return alert("Number must be E.164, e.g. +16505551234");
  if (!facility) return alert("Enter a facility name (used for logging + the agent's script)");
  startCall(to, facility, $("call-negotiate").checked);
};

/* ---------- autopilot ---------- */

let apWasRunning = false;
async function pollAutopilot() {
  try {
    const d = await (await fetch("/api/autopilot")).json();
    $("autopilot-toggle").checked = d.enabled;
    const show = d.running || d.log.length > 0;
    $("autopilot-log").style.display = show ? "block" : "none";
    if (show) setHTML("autopilot-log",
      d.log.map((l) => `<div>${esc(l)}</div>`).join("") +
      (d.running ? "<div>⏳ running…</div>" : ""));
    if (apWasRunning && !d.running) generateReport();   // zero-click finish
    apWasRunning = d.running;
  } catch (e) { /* backend restarting */ }
}
setInterval(pollAutopilot, 4000);

$("run-market-btn").onclick = async () => {
  if (!confirm("Auto-call every facility in the market (then negotiate)?")) return;
  $("run-market-btn").disabled = true;
  const res = await fetch("/api/autopilot/run", { method: "POST" });
  const d = await res.json();
  $("call-status").textContent = res.ok
    ? `market round started (spec ${d.spec_id})` : `error: ${d.detail}`;
  $("autopilot-log").style.display = "block";
  setTimeout(() => { $("run-market-btn").disabled = false; }, 5000);
};

$("autopilot-toggle").onchange = async () => {
  await fetch("/api/autopilot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: $("autopilot-toggle").checked }),
  });
  pollAutopilot();
};

/* ---------- inbound line ---------- */

async function loadInbound() {
  try {
    const d = await (await fetch("/api/inbound")).json();
    if (!d.phone_number) return;
    $("inbound-number").textContent = d.phone_number;
    setHTML("inbound-agent", d.agents.map((a) =>
      `<option value="${esc(a)}" ${a === d.assigned ? "selected" : ""}>${esc(a)}</option>`
    ).join(""));
  } catch (e) { /* backend not ready */ }
}

$("inbound-btn").onclick = async () => {
  $("inbound-status").textContent = "switching…";
  const res = await fetch("/api/inbound", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_key: $("inbound-agent").value }),
  });
  $("inbound-status").textContent = res.ok ? "switched ✓"
    : "error: " + (await res.json()).detail;
  setTimeout(() => { $("inbound-status").textContent = ""; }, 3000);
};

/* ================= results rendering ================= */

function stamp(flag) {
  const cls = flag.severity === "high" ? "" : " low";
  return `<span class="stamp${cls}" title="${esc(flag.explanation || "")}">⚑ ${esc(flag.label)}</span>`;
}

function latestQuotesByFacility(quotes) {
  const byFac = {};
  quotes.forEach((q) => (byFac[q.facility_name] ||= []).push(q));
  return byFac;
}

function renderQuotes(quotes, benchmark) {
  const byFac = latestQuotesByFacility(quotes);
  const cards = Object.entries(byFac).map(([fac, qs]) => {
    const q = qs[qs.length - 1];
    const moved = new Set(qs.map((x) => x.total)).size > 1;
    const prev = moved ? qs[qs.length - 2].total : null;
    const items = (q.line_items || []).map((li) =>
      `<li><span>${esc(li.label || lineItemLabels[li.id] || li.id)}</span>` +
      `<span class="dots"></span><span>${fmt(li.amount)}</span></li>`).join("");
    const flags = (q.red_flags || []).map(stamp).join("") ||
      `<span class="stamp ok">no red flags</span>`;
    let vsMedian = "";
    if (benchmark && benchmark.cash_median && q.total) {
      const pct = Math.round(100 * (q.total - benchmark.cash_median) / benchmark.cash_median);
      vsMedian = `<div class="vs-median">${pct >= 0 ? "+" : ""}${pct}% vs market median ${fmt(benchmark.cash_median)}</div>`;
    }
    return `<div class="card quote-card">
      <div class="facility">${esc(fac)}</div>
      ${moved ? `<div class="moved">▾ price moved during call
        <span class="prev-total">${fmt(prev)}</span></div>` : ""}
      <ul class="ledger">${items}</ul>
      <div class="total"><span class="tl">${q.itemized ? "itemized total" : "stated total (not itemized)"}</span>
        <span>${fmt(q.total)}</span></div>
      ${vsMedian}
      <div>${flags}</div>
      ${q.notes ? `<p class="quote-notes">${esc(q.notes)}</p>` : ""}
    </div>`;
  });
  setHTML("quotes", cards.join(""));
}

function renderBenchmark(b) {
  const text = b && b.cash_median
    ? `market benchmark (${b.label || ""}): low ${fmt(b.cash_low)} · median ${fmt(b.cash_median)} · high ${fmt(b.cash_high)} · Medicare floor ${fmt(b.medicare_floor)}`
    : "";
  if ($("benchmark-band").textContent !== text) $("benchmark-band").textContent = text;
}

function renderStats(calls, quotes, benchmark) {
  const byFac = latestQuotesByFacility(quotes);
  const totals = Object.values(byFac)
    .map((qs) => qs[qs.length - 1].total).filter((t) => t > 0);
  const best = totals.length ? fmt(Math.min(...totals)) : "—";
  const median = benchmark && benchmark.cash_median ? fmt(benchmark.cash_median) : "—";
  const put = (id, v) => { if ($(id).textContent !== String(v)) $(id).textContent = v; };
  put("stat-calls", (calls || []).length);
  put("stat-quotes", quotes.length);
  put("stat-best", best);
  put("stat-median", median);
}

function renderOutcomes(outcomes) {
  if (!outcomes.length) return;
  $("outcomes").classList.remove("empty");
  setHTML("outcomes", outcomes.map((o) =>
    `<div><strong>${esc(o.facility_name)}</strong> —
     <span class="o-type">${esc(o.outcome_type)}</span>: ${esc(o.details || "")}
     ${(o.red_flags || []).map(stamp).join("")}</div>`).join(""));
}

/* ---------- calls strip + live transcript ---------- */

const isSettled = (s) => s && (s.startsWith("done") || s.startsWith("failed"));

let liveCid = null;
let liveOverride = false;      // manual show/hide beats auto-open
let lastAutoCid = null;        // a new active call re-arms auto-open
let liveTimer = null;

function renderCalls(calls) {
  const active = (calls || []).find((c) => !isSettled(c.status || ""));
  if (active && active.conversation_id !== lastAutoCid) {
    lastAutoCid = active.conversation_id;
    liveOverride = false;
  }
  if (!liveOverride && active && liveCid !== active.conversation_id) {
    liveCid = active.conversation_id;
    $("live-transcript").hidden = false;
    schedulePollLive(0);
  }
  setHTML("calls-list", (calls || []).map((c) => {
    const s = c.status || "…";
    const stCls = s.startsWith("failed") ? "st-failed" : s.startsWith("done") ? "st-done" : "st-active";
    return `<div class="call-row">☎ <span>${esc(c.facility_name || "?")}</span> —
      <span class="${stCls}">${esc(s)}</span>${c.negotiation_mode ? " · negotiation" : ""}
      <a href="#" data-cid="${esc(c.conversation_id)}">${
        liveCid === c.conversation_id ? "hide transcript" : "live transcript"}</a></div>`;
  }).join(""));
}

$("calls-list").addEventListener("click", (e) => {
  const a = e.target.closest("a[data-cid]");
  if (!a) return;
  e.preventDefault();
  liveOverride = true;
  toggleLive(a.dataset.cid);
});

function toggleLive(cid) {
  liveCid = liveCid === cid ? null : cid;
  $("live-transcript").hidden = !liveCid;
  if (liveCid) schedulePollLive(0);
}

function schedulePollLive(delay) {
  clearTimeout(liveTimer);
  liveTimer = setTimeout(pollLive, delay);
}

async function pollLive() {
  if (!liveCid) return;
  const cid = liveCid;
  try {
    const d = await (await fetch(`/api/calls/${cid}/live`)).json();
    if (cid !== liveCid) return;
    const activeCall = !isSettled(d.status);
    const changed = setHTML("live-transcript",
      `<div class="lt-head">${activeCall ? '<span class="lt-dot"></span>' : ""}
        <span>${esc(cid)} — ${esc(d.status)}${d.duration ? ` (${d.duration}s)` : ""}</span></div>` +
      d.turns.map((t) =>
        `<div class="lt-turn"><span class="who ${t.role === "agent" ? "agent" : "them"}">${
          t.role === "agent" ? "Caller" : "Receptionist"}:</span> ${esc(t.message)}</div>`
      ).join(""));
    if (changed) $("live-transcript").scrollTop = $("live-transcript").scrollHeight;
    if (activeCall) schedulePollLive(2000);
    // settled: stop polling — the final transcript stays on screen
  } catch (e) { schedulePollLive(5000); }
}

/* ---------- main data poll ---------- */

let lastCallsSig = null;

async function poll() {
  try {
    const data = await (await fetch("/api/quotes")).json();
    const calls = data.calls || [];
    const quotes = data.quotes || [];
    if (calls.length || quotes.length) { reveal("results-section"); reveal("report-section"); }
    renderBenchmark(data.benchmark);
    renderStats(calls, quotes, data.benchmark);
    renderQuotes(quotes, data.benchmark);
    renderOutcomes(data.outcomes || []);
    renderCalls(calls);
    window._calls = calls;
    maybeAutoReport(calls, quotes);
  } catch (e) { /* no confirmed spec yet — fine */ }
}
setInterval(poll, 4000);

/* ================= report ================= */

let reportSig = null;   // guards auto-generation against re-fires

function maybeAutoReport(calls, quotes) {
  if (!calls.length || !quotes.length) return;
  if (!calls.every((c) => isSettled(c.status || ""))) return;
  const sig = calls.map((c) => `${c.conversation_id}:${c.status}`).sort().join("|");
  if (sig === reportSig) return;
  reportSig = sig;
  generateReport();
}

async function generateReport() {
  reveal("report-section");
  $("report").textContent = "generating…";
  let r;
  try { r = await (await fetch("/api/report")).json(); }
  catch (e) { $("report").textContent = "report failed — try regenerate"; return; }
  $("report").classList.remove("empty");
  const rows = (r.ranked || []).map((q, i) =>
    `<li><strong>#${i + 1} ${esc(q.facility_name)}</strong> —
     <span class="price">${fmt(q.effective_total)}</span> effective
     ${q.price_moved ? `<span class="moved">· price moved${
       q.saved ? ` — saved ${fmt(q.saved)} (${esc(q.saved_pct)}%)` : ""}</span>` : ""}
     ${(q.red_flags || []).map(stamp).join("")}
     ${q.effective_note ? `<div class="hint">${esc(q.effective_note)}</div>` : ""}</li>`
  ).join("");
  const audio = (window._calls || []).filter((c) => c.conversation_id).map((c) =>
    `<div class="audio-row"><span class="audio-label">${esc(c.facility_name)} —
     ${esc(c.conversation_id)}${c.negotiation_mode ? " (negotiation)" : ""}</span>
     <audio controls preload="none"
       src="/api/calls/${encodeURIComponent(c.conversation_id)}/audio"></audio></div>`).join("");
  setHTML("report",
    `<pre id="report-text">${esc(r.recommendation)}</pre>
     <ol>${rows}</ol>
     <div class="rec-title mono-caps">call recordings</div>
     ${audio || '<div class="empty">none stored yet</div>'}`);
}
$("report-btn").onclick = generateReport;

/* ================= boot ================= */

async function loadConfig() {
  const cfg = await (await fetch("/api/config")).json();
  $("vertical-pill").textContent = cfg.display_name;
  cfg.quote_line_items.forEach((li) => { lineItemLabels[li.id] = li.label; });
  renderMarket(cfg.counterparty_market);
  setHTML("facility-list", (cfg.counterparty_market || [])
    .map((cp) => `<option value="${esc(cp.facility_name)}"></option>`).join(""));
  estimatorAgentId = cfg.agent_ids && cfg.agent_ids.estimator;
  if (!estimatorAgentId) setVoiceStatus("estimator agent not provisioned");
}

loadConfig().then(loadLatest).then(poll).then(loadInbound);
