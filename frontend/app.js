const $ = (id) => document.getElementById(id);

const fmt = (n) => "$" + Number(n).toLocaleString("en-US",
  {maximumFractionDigits: 0});

// Escape dynamic strings before innerHTML interpolation — transcript turns
// and quote notes are transcribed from live phone audio, i.e. untrusted.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

// Re-render a region only when its HTML actually changed. Rebuilding
// innerHTML on every poll replays entry animations and drops scroll/focus
// state — this cache is what stops the ledger flickering.
const _htmlCache = {};
function setHTML(id, html) {
  if (_htmlCache[id] === html) return false;
  _htmlCache[id] = html;
  $(id).innerHTML = html;
  return true;
}

let specId = null;
let specConfirmed = false;
let lineItemLabels = {};
let estimatorId = null;

// ---------- config ----------

async function loadConfig() {
  const cfg = await (await fetch("/api/config")).json();
  $("vertical-pill").textContent = cfg.display_name;
  cfg.quote_line_items.forEach(li => lineItemLabels[li.id] = li.label);
  estimatorId = cfg.agent_ids && cfg.agent_ids.estimator;
  if (!estimatorId)
    $("voice-status").textContent = "estimator not provisioned — run setup_agents";
}

// ---------- voice session (ElevenLabs JS client SDK) ----------

let Conversation = null;
let conv = null;
let vizMode = "idle";      // idle | connecting | listening | speaking
let rafId = null;

async function loadSDK() {
  try {
    ({ Conversation } =
      await import("https://cdn.jsdelivr.net/npm/@elevenlabs/client/+esm"));
  } catch (e) {
    // No SDK (offline CDN?) — fall back to the official floating widget so
    // voice intake still works, just without the centered visualizer.
    Conversation = null;
    if (estimatorId) {
      const w = document.createElement("elevenlabs-convai");
      w.setAttribute("agent-id", estimatorId);
      document.body.appendChild(w);
      const s = document.createElement("script");
      s.src = "https://unpkg.com/@elevenlabs/convai-widget-embed";
      s.async = true;
      document.body.appendChild(s);
      $("voice-status").textContent = "voice widget loaded (bottom right)";
    }
  }
}

function feed(who, text) {
  const el = $("voice-feed");
  el.insertAdjacentHTML("beforeend",
    `<div class="turn"><span class="who who-${who === "user" ? "you" : "agent"}">${
      who === "user" ? "You" : "Estimator"}</span>${esc(text)}</div>`);
  el.scrollTop = el.scrollHeight;
}

function setVoiceState(mode, label) {
  vizMode = mode;
  $("voice-status").textContent = label;
  $("talk-btn").classList.toggle("live", mode !== "idle");
}

async function startVoice() {
  if (!estimatorId) return;
  if (!Conversation) return;   // widget fallback handles voice instead
  setVoiceState("connecting", "connecting…");
  try {
    await navigator.mediaDevices.getUserMedia({audio: true});
    const prevSpec = specId;
    conv = await Conversation.startSession({
      agentId: estimatorId,
      onConnect: () => setVoiceState("listening", "listening — describe your scan"),
      onModeChange: (m) => {
        const mode = (m && m.mode) || m;
        setVoiceState(mode === "speaking" ? "speaking" : "listening",
          mode === "speaking" ? "estimator speaking…" : "listening…");
      },
      onMessage: (msg) => {
        const text = (msg && msg.message) || "";
        const src = (msg && msg.source) === "user" ? "user" : "agent";
        if (text) feed(src, text);
      },
      onError: (e) => setVoiceState("idle", "error: " + e),
      onDisconnect: () => {
        conv = null;
        setVoiceState("idle", "interview ended — building your spec…");
        waitForSpec(prevSpec);
      },
    });
  } catch (e) {
    conv = null;
    setVoiceState("idle", "mic error: " + e);
  }
}

async function stopVoice() {
  if (conv) { try { await conv.endSession(); } catch (e) {} }
  conv = null;
}

$("talk-btn").onclick = () => (conv ? stopVoice() : startVoice());

// circular visualizer around the talk button
function drawViz() {
  const cv = $("viz"), ctx = cv.getContext("2d");
  const W = cv.width, C = W / 2, bars = 96, inner = 128;
  const grad = ctx.createLinearGradient(0, W, W, 0);
  grad.addColorStop(0, "#fc4c02");
  grad.addColorStop(.5, "#ef2cc1");
  grad.addColorStop(1, "#bdbbff");
  const tick = () => {
    ctx.clearRect(0, 0, W, W);
    let data = null;
    if (conv) {
      try {
        data = vizMode === "speaking"
          ? conv.getOutputByteFrequencyData()
          : conv.getInputByteFrequencyData();
      } catch (e) {}
    }
    ctx.strokeStyle = grad;
    ctx.lineWidth = 5;
    ctx.lineCap = "round";
    const t = performance.now() / 1000;
    for (let i = 0; i < bars; i++) {
      const a = (i / bars) * Math.PI * 2 - Math.PI / 2;
      let len;
      if (data && data.length) {
        const v = data[Math.floor(i / bars * data.length * .7)] / 255;
        len = 6 + v * 74;
      } else {
        len = 8 + Math.sin(t * 1.6 + i * .35) * 4;   // idle breathing
      }
      ctx.globalAlpha = data ? .95 : .5;
      ctx.beginPath();
      ctx.moveTo(C + Math.cos(a) * inner, C + Math.sin(a) * inner);
      ctx.lineTo(C + Math.cos(a) * (inner + len),
                 C + Math.sin(a) * (inner + len));
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    rafId = requestAnimationFrame(tick);
  };
  tick();
}

// ---------- spec sheet ----------

function renderSpec(spec) {
  $("spec-panel").classList.remove("hidden");
  $("spec-json").value = JSON.stringify(spec, null, 2);
  const kv = Object.entries(spec).map(([k, v]) =>
    `<div class="spec-kv"><div class="k">${esc(k.replaceAll("_", " "))}</div>
     <div class="v">${esc(typeof v === "object" ? JSON.stringify(v) : v)}</div></div>`);
  setHTML("spec-view", kv.join(""));
}

function setSpecStatus(text) { $("spec-status").textContent = text; }

async function autoConfirm() {
  if (!specId || specConfirmed) return;
  await fetch(`/api/specs/${specId}/confirm`, {method: "POST"});
  specConfirmed = true;
  setSpecStatus(`spec ${specId} · confirmed — calling the market…`);
  $("results").classList.remove("hidden");
  poll();
}

// After a voice interview the Estimator submits the spec through a server
// tool, which can land a beat after the websocket closes — so retry briefly.
async function waitForSpec(prevSpec, attempt = 0) {
  const data = await (await fetch("/api/specs/latest")).json();
  if (data.spec && data.id !== prevSpec) {
    specId = data.id;
    specConfirmed = !!data.confirmed;
    renderSpec(data.spec);
    setSpecStatus(`spec ${specId} · captured from interview`);
    $("spec-panel").scrollIntoView({behavior: "smooth"});
    await autoConfirm();
    return;
  }
  if (attempt < 6) setTimeout(() => waitForSpec(prevSpec, attempt + 1), 2000);
  else setVoiceState("idle", "no spec submitted — tap to try again");
}

async function loadLatest() {
  try {
    const data = await (await fetch("/api/specs/latest")).json();
    if (!data.spec) return;
    specId = data.id;
    specConfirmed = !!data.confirmed;
    renderSpec(data.spec);
    setSpecStatus(`spec ${specId} · ${data.confirmed ? "confirmed" : "draft"}`);
    if (specConfirmed) $("results").classList.remove("hidden");
  } catch (e) { /* backend not ready */ }
}

$("confirm-btn").onclick = async () => {
  let spec;
  try { spec = JSON.parse($("spec-json").value); }
  catch { return alert("Spec is not valid JSON"); }
  if (!specId) {
    const res = await (await fetch("/api/specs", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({spec})})).json();
    specId = res.spec_id;
  } else {
    await fetch(`/api/specs/${specId}`, {method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({spec})});
  }
  renderSpec(spec);
  specConfirmed = false;
  await autoConfirm();
};

// ---------- document upload ----------

$("upload-btn").onclick = () => $("doc-file").click();

$("doc-file").onchange = async () => {
  const f = $("doc-file").files[0];
  if (!f) return;
  $("module-hint").textContent = "parsing document…";
  try {
    const fd = new FormData(); fd.append("file", f);
    const res = await (await fetch("/api/parse-document",
      {method: "POST", body: fd})).json();
    specId = res.spec_id;
    specConfirmed = false;
    renderSpec(res.spec);
    setSpecStatus(`spec ${specId} · parsed from document`);
    $("module-hint").textContent = "document merged into spec ✓";
    $("spec-panel").scrollIntoView({behavior: "smooth"});
    await autoConfirm();
  } catch (e) {
    $("module-hint").textContent = "parse failed — try another file";
  }
};

// ---------- live market round ----------

function stamp(flag) {
  const cls = flag.severity === "high" ? "" : " low";
  return `<span class="stamp${cls}" title="${esc(flag.explanation)}">⚑ ${esc(flag.label)}</span>`;
}

function latestPerFacility(quotes) {
  const byFac = {};
  quotes.forEach(q => (byFac[q.facility_name] ||= []).push(q));
  return byFac;
}

function renderStats(data) {
  const calls = data.calls || [], quotes = data.quotes || [];
  $("stat-calls").textContent = calls.length;
  $("stat-quotes").textContent = quotes.length;
  const totals = Object.values(latestPerFacility(quotes))
    .map(qs => qs[qs.length - 1].total).filter(Boolean);
  $("stat-best").textContent = totals.length ? fmt(Math.min(...totals)) : "—";
  $("stat-median").textContent =
    data.benchmark && data.benchmark.cash_median
      ? fmt(data.benchmark.cash_median) : "—";
}

function renderQuotes(quotes, benchmark) {
  const cards = Object.entries(latestPerFacility(quotes)).map(([fac, qs]) => {
    const q = qs[qs.length - 1];
    const moved = new Set(qs.map(x => x.total)).size > 1;
    const prev = moved ? qs[qs.length - 2].total : null;
    const items = (q.line_items || []).map(li =>
      `<li><span>${esc(li.label || lineItemLabels[li.id] || li.id)}</span>` +
      `<span class="dots"></span><span>${fmt(li.amount)}</span></li>`).join("");
    const flags = (q.red_flags || []).map(stamp).join("") ||
      `<span class="stamp ok">no red flags</span>`;
    let vsMedian = "";
    if (benchmark && benchmark.cash_median && q.total) {
      const pct = Math.round(100 * (q.total - benchmark.cash_median) / benchmark.cash_median);
      vsMedian = `<div class="vs-median">
        ${pct >= 0 ? "+" : ""}${pct}% vs market median ${fmt(benchmark.cash_median)}</div>`;
    }
    return `<div class="card quote-card">
      <div class="facility">${esc(fac)}</div>
      ${moved ? `<div class="moved">▾ price moved during call
        <span class="prev-total">${fmt(prev)}</span></div>` : ""}
      <ul class="ledger">${items}</ul>
      <div class="total"><span class="label">${q.itemized ? "itemized total" : "stated total (not itemized)"}</span>
        <span>${fmt(q.total)}</span></div>
      ${vsMedian}
      <div>${flags}</div>
      ${q.notes ? `<p class="quote-notes">${esc(q.notes)}</p>` : ""}
    </div>`;
  });
  setHTML("quotes", cards.join("") || "");
}

function renderBenchmark(b) {
  const text = b && b.cash_median
    ? `market benchmark (${b.label || ""}): low ${fmt(b.cash_low)} · median ${fmt(b.cash_median)} · high ${fmt(b.cash_high)} · Medicare floor ${fmt(b.medicare_floor)}`
    : "";
  if ($("benchmark-band").textContent !== text)
    $("benchmark-band").textContent = text;
}

// ---------- live transcript ----------
// Auto-opens for whichever call is currently active and polls every 2s;
// the manual show/hide links still work and win over auto-opening.

let liveCid = null;
let liveManual = false;
let livePollToken = 0;
let knownCallCount = 0;

const isActive = (c) => c.conversation_id &&
  !String(c.status || "").startsWith("done") &&
  !String(c.status || "").startsWith("failed");

function renderCalls(calls) {
  if (calls && calls.length) $("calls-list").classList.remove("empty");
  const html = (calls || []).map(c => {
    const s = c.status || "…";
    const cls = s.startsWith("failed") ? "status-failed"
      : s.startsWith("done") ? "status-done" : "status-live";
    return `<div>☎ ${esc(c.facility_name || "?")} — <span class="${cls}">${esc(s)}</span>` +
      `${c.negotiation_mode ? " · negotiation" : ""}
       <a href="#results" onclick="toggleLive('${c.conversation_id}');return false">
         ${liveCid === c.conversation_id ? "hide transcript" : "transcript"}</a></div>`;
  }).join("");
  if (html) setHTML("calls-list", html);
}

function autoLive(calls) {
  if ((calls || []).length > knownCallCount) {
    knownCallCount = calls.length;
    liveManual = false;          // a new call re-arms auto-open
  }
  if (liveManual) return;
  const active = (calls || []).find(isActive);
  if (active && liveCid !== active.conversation_id) {
    liveCid = active.conversation_id;
    $("live-transcript").style.display = "block";
    pollLive();
  }
}

function toggleLive(cid) {
  liveManual = true;                       // user took over
  liveCid = liveCid === cid ? null : cid;
  $("live-transcript").style.display = liveCid ? "block" : "none";
  renderCalls(window._calls || []);
  if (liveCid) pollLive();
}
window.toggleLive = toggleLive;

async function pollLive() {
  const token = ++livePollToken;           // newest chain wins; older ones die
  const tick = async () => {
    if (token !== livePollToken || !liveCid) return;
    let delay = 2000;
    try {
      const d = await (await fetch(`/api/calls/${liveCid}/live`)).json();
      const running = d.status !== "done" && d.status !== "failed";
      const html =
        `<div class="live-meta">${running ? '<span class="live-dot"></span>' : ""}
          ${liveCid} — ${esc(d.status)}${d.duration ? ` (${d.duration}s)` : ""}</div>` +
        d.turns.map(t =>
          `<div class="turn"><span class="${
            t.role === "agent" ? "who-agent" : "who-them"}">${
            t.role === "agent" ? "Caller" : "Receptionist"}</span>${esc(t.message)}</div>`
        ).join("");
      if (setHTML("live-transcript", html))
        $("live-transcript").scrollTop = $("live-transcript").scrollHeight;
      if (!running) return;                // final transcript stays on screen
    } catch (e) { delay = 5000; }
    setTimeout(tick, delay);
  };
  tick();
}

function renderOutcomes(outcomes) {
  if (!outcomes.length) return;
  $("outcomes").classList.remove("empty");
  setHTML("outcomes", outcomes.map(o =>
    `<div><strong>${esc(o.facility_name)}</strong> —
     <span class="mono">${esc(o.outcome_type)}</span>: ${esc(o.details)}
     ${(o.red_flags || []).map(stamp).join("")}</div>`).join(""));
}

// ---------- auto-generated report ----------

let lastReportSig = null;

function maybeAutoReport(data) {
  const calls = data.calls || [];
  const settled = calls.length > 0 && calls.every(c =>
    String(c.status || "").startsWith("done") ||
    String(c.status || "").startsWith("failed"));
  if (!settled || !(data.quotes || []).length) return;
  const sig = JSON.stringify(calls.map(c => c.conversation_id + c.status)) +
    (data.quotes || []).length;
  if (sig === lastReportSig) return;
  lastReportSig = sig;
  generateReport(true);
}

async function generateReport(auto) {
  $("report-status").textContent = auto
    ? "all calls finished — generating…" : "generating…";
  try {
    const r = await (await fetch("/api/report")).json();
    $("report").classList.remove("empty");
    const rows = r.ranked.map((q, i) =>
      `<li><strong>#${i + 1} ${esc(q.facility_name)}</strong> —
       <span class="mono">${fmt(q.effective_total)}</span> effective
       ${q.price_moved ? `<span class="moved">· price moved${
         q.saved ? ` — saved ${fmt(q.saved)} (${q.saved_pct}%)` : ""}</span>` : ""}
       ${(q.red_flags || []).map(stamp).join("")}
       ${q.effective_note ? `<div class="quote-notes">${esc(q.effective_note)}</div>` : ""}</li>`
    ).join("");
    const audio = (window._calls || []).filter(c => c.conversation_id).map(c =>
      `<div><span class="audio-label">${esc(c.facility_name)} —
       ${c.conversation_id}${c.negotiation_mode ? " (negotiation)" : ""}</span>
       <audio controls preload="none"
         src="/api/calls/${c.conversation_id}/audio"></audio></div>`).join("");
    $("report").innerHTML =
      `<pre id="report-text">${esc(r.recommendation)}</pre>
       <ol>${rows}</ol>
       <p class="recordings-title">Call recordings</p>
       ${audio || '<div class="empty">none stored yet</div>'}`;
    $("report-status").textContent = "";
  } catch (e) {
    $("report-status").textContent = "report failed — retry with Regenerate";
    lastReportSig = null;
  }
}

$("report-btn").onclick = () => generateReport(false);

// ---------- main poll ----------

async function poll() {
  try {
    const data = await (await fetch("/api/quotes")).json();
    const busy = (data.calls || []).length || (data.quotes || []).length ||
      (data.outcomes || []).length;
    if (busy) $("results").classList.remove("hidden");
    renderStats(data);
    renderBenchmark(data.benchmark);
    renderQuotes(data.quotes, data.benchmark);
    renderOutcomes(data.outcomes);
    renderCalls(data.calls);
    window._calls = data.calls || [];
    autoLive(window._calls);
    maybeAutoReport(data);
  } catch (e) { /* no confirmed spec yet — fine */ }
}
setInterval(poll, 4000);

// ---------- boot ----------

loadConfig().then(loadSDK).then(loadLatest).then(poll);
drawViz();
