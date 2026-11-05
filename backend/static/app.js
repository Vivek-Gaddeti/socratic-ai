/* SocraticAI frontend (vanilla JS, no build step). */

const state = {
  token: null,
  user: null,
  settings: null,
  docs: [],
  sessions: [],
  session: null, // the open session (curriculum, proficiency, messages)
  sending: false,
  pollTimer: null,
};
const THRESHOLD_DEFAULT = 85;
const SERVER_DOWN_MESSAGE = "Can't reach the SocraticAI server. Start it with \"python main.py\" in the backend folder, then reload this page.";
const $ = (id) => document.getElementById(id);

try { state.token = localStorage.getItem("socratic_token"); } catch (e) { /* storage blocked */ }

/* ───────────── helpers ───────────── */
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(path, { ...options, headers });
  } catch {
    // fetch() only throws when the server can't be reached at all.
    throw new Error(SERVER_DOWN_MESSAGE);
  }
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    signOut(false);
    throw new Error("Please sign in again.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed");
  return data;
}

function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), 3800);
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

/** Small, safe Markdown renderer: escapes HTML first, then adds formatting. */
function renderMarkdown(src) {
  const inline = (s) => s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/(^|[^\w])_([^_\s][^_]*?)_(?=[^\w]|$)/g, "$1<em>$2</em>");
  const lines = escapeHtml(src).split(/\r?\n/);
  let html = "", para = [], list = null, code = null;
  const flushPara = () => { if (para.length) { html += `<p>${inline(para.join("<br>"))}</p>`; para = []; } };
  const closeList = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (code) { html += `<pre><code>${code.join("\n")}</code></pre>`; code = null; }
      else { flushPara(); closeList(); code = []; }
      continue;
    }
    if (code) { code.push(line); continue; }
    let m;
    if ((m = line.match(/^\s*[-*•]\s+(.*)$/)) || (m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      const type = /^\s*\d/.test(line) ? "ol" : "ul";
      flushPara();
      if (list !== type) { closeList(); html += `<${type}>`; list = type; }
      html += `<li>${inline(m[1])}</li>`;
    } else if ((m = line.match(/^#{1,4}\s+(.*)$/))) {
      flushPara(); closeList(); html += `<h4>${inline(m[1])}</h4>`;
    } else if ((m = line.match(/^&gt;\s?(.*)$/))) {
      flushPara(); closeList(); html += `<blockquote>${inline(m[1])}</blockquote>`;
    } else if (!line.trim()) {
      flushPara(); closeList();
    } else {
      closeList(); para.push(line);
    }
  }
  if (code) html += `<pre><code>${code.join("\n")}</code></pre>`;
  flushPara(); closeList();
  return html;
}

function relTime(iso) {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

const threshold = () => state.session?.mastery_threshold || state.settings?.mastery_threshold || THRESHOLD_DEFAULT;
const scoreClass = (s) => (s >= threshold() ? "good" : s >= 50 ? "mid" : "bad");
const scoreColor = (s) => (s >= threshold() ? "var(--good)" : s >= 50 ? "var(--warn)" : "var(--bad)");

function meter(value, { thresholdLine = true } = {}) {
  const v = Math.max(0, Math.min(100, value || 0));
  return `<div class="meter" role="img" aria-label="${v.toFixed(0)} out of 100">
    <span style="width:${v}%;background:${scoreColor(v)}"></span>
    ${thresholdLine ? `<i class="threshold" style="left:${threshold()}%"></i>` : ""}
  </div>`;
}

/* ───────────── theme ───────────── */
function toggleTheme() {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("socratic_theme", root.dataset.theme); } catch (e) { /* ignore */ }
}

/* ───────────── auth ───────────── */
function showAuth() {
  $("view-app").classList.add("hidden");
  $("view-auth").classList.remove("hidden");
}

async function showApp() {
  $("view-auth").classList.add("hidden");
  $("view-app").classList.remove("hidden");
  $("user-name").textContent = state.user.name || "Student";
  $("user-email").textContent = state.user.email || "";
  $("user-avatar").textContent = (state.user.name || "S").trim()[0].toUpperCase();
  setView("tutor");
  renderChat();
  await Promise.all([loadDocs(), loadSessions()]);
  renderChat();
}

function setAuth(token, user) {
  state.token = token;
  state.user = user;
  try { localStorage.setItem("socratic_token", token); } catch (e) { /* ignore */ }
  showApp();
}

function signOut(showMessage = true) {
  state.token = null; state.user = null; state.session = null;
  try { localStorage.removeItem("socratic_token"); } catch (e) { /* ignore */ }
  clearInterval(state.pollTimer);
  showAuth();
  if (showMessage) toast("Signed out");
}

async function login(email, password) {
  const data = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  setAuth(data.access_token, { name: data.name, email });
  return data;
}

function setupAuth() {
  const tabLogin = $("auth-tab-login"), tabReg = $("auth-tab-register");
  tabLogin.onclick = () => { tabLogin.classList.add("active"); tabReg.classList.remove("active"); $("form-login").classList.remove("hidden"); $("form-register").classList.add("hidden"); };
  tabReg.onclick = () => { tabReg.classList.add("active"); tabLogin.classList.remove("active"); $("form-register").classList.remove("hidden"); $("form-login").classList.add("hidden"); };

  $("form-login").onsubmit = async (e) => {
    e.preventDefault();
    $("login-error").classList.add("hidden");
    try { await login($("login-email").value.trim(), $("login-password").value); }
    catch (err) { $("login-error").textContent = err.message; $("login-error").classList.remove("hidden"); }
  };

  $("form-register").onsubmit = async (e) => {
    e.preventDefault();
    $("register-error").classList.add("hidden");
    const name = $("reg-name").value.trim(), email = $("reg-email").value.trim();
    try {
      const data = await api("/auth/register", { method: "POST", body: JSON.stringify({ name, email, password: $("reg-password").value }) });
      setAuth(data.access_token, { name: data.name, email });
      toast(`Welcome, ${data.name}!`, "success");
    } catch (err) { $("register-error").textContent = err.message; $("register-error").classList.remove("hidden"); }
  };

  $("btn-demo-login").onclick = async () => {
    const email = "student@socratic.ai", password = "password123";
    try { await login(email, password); }
    catch {
      try {
        const data = await api("/auth/register", { method: "POST", body: JSON.stringify({ name: "Demo Student", email, password }) });
        setAuth(data.access_token, { name: data.name, email });
      } catch (err) { toast("Demo login failed: " + err.message, "error"); }
    }
  };
  $("btn-logout").onclick = () => signOut();
}

/* ───────────── navigation ───────────── */
function setView(name) {
  for (const v of ["tutor", "library", "progress"]) $(`view-${v}`).classList.toggle("hidden", v !== name);
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  closeSidebar();
  if (name === "library") loadDocs();
  if (name === "progress") loadProgress();
}
function openSidebar() { $("sidebar").classList.add("open"); $("scrim").classList.remove("hidden"); }
function closeSidebar() { $("sidebar").classList.remove("open"); $("scrim").classList.add("hidden"); $("session-panel").classList.remove("open"); }

/* ───────────── settings ───────────── */
async function loadSettings() {
  try {
    state.settings = await fetch("/api/settings").then((r) => r.json());
    const on = state.settings.has_api_key;
    $("engine-dot").className = `engine-dot ${on ? "on" : "off"}`;
    $("engine-label").textContent = on ? "Gemini 2.5 Flash" : "Offline mode";
    $("threshold-value").textContent = state.settings.mastery_threshold;
  } catch { $("engine-label").textContent = "Server offline"; }
}

function openSettings() {
  const s = state.settings || {};
  $("settings-kv").innerHTML = `
    <dt>Mode</dt><dd>${escapeHtml(s.mode || "unknown")}</dd>
    <dt>Chat model</dt><dd>${escapeHtml(s.chat_model || "offline templates")}</dd>
    <dt>Embeddings</dt><dd>${escapeHtml(s.embedding_model || "")}</dd>
    <dt>Vector store</dt><dd>FAISS IndexFlatIP (cosine)</dd>
    <dt>Mastery threshold</dt><dd>${s.mastery_threshold ?? THRESHOLD_DEFAULT}%</dd>`;
  $("input-key").value = "";
  $("settings-msg").classList.add("hidden");
  $("dlg-settings").showModal();
}

async function saveKey() {
  const key = $("input-key").value.trim();
  if (!key) return;
  try {
    await api("/api/settings/api-key", { method: "POST", body: JSON.stringify({ api_key: key }) });
    await loadSettings();
    toast("Gemini key saved", "success");
  } catch (err) { toast(err.message, "error"); }
}

/* ───────────── library ───────────── */
async function loadDocs() {
  try {
    state.docs = await api("/documents/");
    renderDocs();
    if (!state.session) renderChat();
    const processing = state.docs.some((d) => d.status === "processing");
    clearInterval(state.pollTimer);
    if (processing) state.pollTimer = setInterval(loadDocs, 2500);
  } catch (err) { console.error(err); }
}

function renderDocs() {
  const grid = $("doc-grid");
  if (!state.docs.length) {
    grid.innerHTML = `<div class="empty card" style="grid-column:1/-1">No documents yet. Upload a textbook chapter or lecture notes to get started.</div>`;
    return;
  }
  grid.innerHTML = state.docs.map((d) => {
    const status = d.status === "ready"
      ? `<span class="badge good">Ready</span>`
      : d.status === "processing"
        ? `<span class="badge warn"><span class="spinner"></span> Indexing…</span>`
        : `<span class="badge bad">Error</span>`;
    const emb = d.embedder ? (d.embedder.startsWith("gemini") ? "Gemini embeddings" : "Offline embeddings") : "";
    return `<article class="card doc-card">
      <div class="doc-title">📄 ${escapeHtml(d.filename)}</div>
      <div class="badges">${status}
        ${d.pages_count ? `<span class="badge">${d.pages_count} pages</span>` : ""}
        ${d.chunks_count ? `<span class="badge">${d.chunks_count} chunks</span>` : ""}
        ${emb ? `<span class="badge">${emb}</span>` : ""}
      </div>
      ${d.error ? `<p class="small" style="color:var(--bad)">${escapeHtml(d.error)}</p>` : ""}
      ${d.topics.length ? `<div><div class="small muted" style="margin-bottom:.3rem">Curriculum</div><ol class="doc-topics">${d.topics.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ol></div>` : ""}
      <div class="doc-actions">
        <button class="btn btn-primary btn-sm" data-study="${d.id}" ${d.status !== "ready" ? "disabled" : ""}>Study this</button>
        <button class="btn btn-ghost btn-sm" data-reindex="${d.id}" title="Rebuild the FAISS index and curriculum" ${d.status === "processing" ? "disabled" : ""}>↻ Re-index</button>
        <button class="btn btn-danger btn-sm" data-delete="${d.id}" title="Delete document" aria-label="Delete document">🗑</button>
      </div>
    </article>`;
  }).join("");
}

async function uploadFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) { toast("Please choose a PDF file", "error"); return; }
  const form = new FormData();
  form.append("file", file);
  toast(`Uploading ${file.name}…`);
  try {
    await api("/documents/upload", { method: "POST", body: form });
    toast("Uploaded. Building the index and curriculum…", "success");
    setView("library"); // show the card while it indexes
  } catch (err) { toast("Upload failed: " + err.message, "error"); }
}

function setupLibrary() {
  const dz = $("dropzone"), input = $("file-input");
  input.onchange = () => { uploadFile(input.files[0]); input.value = ""; };
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove("over"); uploadFile(e.dataTransfer.files[0]); };

  $("doc-grid").onclick = async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    if (btn.dataset.study) { setView("tutor"); startSession(btn.dataset.study, null); }
    if (btn.dataset.reindex) {
      try { await api(`/documents/${btn.dataset.reindex}/reindex`, { method: "POST" }); toast("Re-indexing…"); loadDocs(); }
      catch (err) { toast(err.message, "error"); }
    }
    if (btn.dataset.delete) {
      if (!confirm("Delete this document and its index? Your progress history stays.")) return;
      try { await api(`/documents/${btn.dataset.delete}`, { method: "DELETE" }); toast("Document deleted"); loadDocs(); }
      catch (err) { toast(err.message, "error"); }
    }
  };
}

/* ───────────── sessions ───────────── */
async function loadSessions() {
  try { state.sessions = await api("/chat/sessions"); renderSessionList(); }
  catch (err) { console.error(err); }
}

function renderSessionList() {
  const list = $("session-list");
  if (!state.sessions.length) { list.innerHTML = `<div class="sidebar-empty">No sessions yet.</div>`; return; }
  list.innerHTML = state.sessions.map((s) => {
    const pct = s.topics_total ? (s.topics_done / s.topics_total) * 100 : 0;
    const meta = s.topics_total > 1
      ? `${s.topics_done}/${s.topics_total} topics${s.current_topic ? " · " + escapeHtml(s.current_topic) : " · complete"}`
      : relTime(s.created_at);
    return `<div class="session-item ${state.session?.id === s.id ? "active" : ""}" data-session="${s.id}" role="button" tabindex="0">
      <span class="session-name">${escapeHtml(s.title)}</span>
      <button class="icon-btn session-del" data-del-session="${s.id}" aria-label="Delete session" title="Delete session">✕</button>
      <span class="session-meta">${meta}</span>
      ${s.topics_total > 1 ? `<div class="mini-progress"><span style="width:${pct}%"></span></div>` : ""}
    </div>`;
  }).join("");
}

async function openSession(id) {
  try {
    state.session = await api(`/chat/sessions/${id}`);
    setView("tutor");
    renderSessionList();
    renderChat();
  } catch (err) { toast(err.message, "error"); }
}

async function startSession(documentId, topic) {
  try {
    const s = await api("/chat/session", { method: "POST", body: JSON.stringify({ document_id: documentId || null, topic: topic || null }) });
    state.session = { ...s, messages: s.messages || [] };
    await loadSessions();
    renderChat();
    $("chat-input").focus();
  } catch (err) { toast(err.message, "error"); }
}

async function deleteSession(id) {
  if (!confirm("Delete this session's conversation? Your topic progress is kept.")) return;
  try {
    await api(`/chat/sessions/${id}`, { method: "DELETE" });
    if (state.session?.id === id) state.session = null;
    await loadSessions();
    renderChat();
  } catch (err) { toast(err.message, "error"); }
}

function openNewSessionDialog(preselectDoc) {
  const ready = state.docs.filter((d) => d.status === "ready");
  const choices = ready.map((d, i) => `
    <label class="choice"><input type="radio" name="session-doc" value="${d.id}" ${(preselectDoc ? d.id === preselectDoc : i === 0) ? "checked" : ""}>
      <span><strong>${escapeHtml(d.filename)}</strong><small>${d.topics.length} topics · ${d.chunks_count} chunks</small></span></label>`).join("");
  $("session-doc-choices").innerHTML = choices + `
    <label class="choice"><input type="radio" name="session-doc" value="" ${ready.length ? "" : "checked"}>
      <span><strong>Open topic</strong><small>Any subject; searches all your documents</small></span></label>`;
  $("session-doc-choices").onchange = syncSessionDialog;
  syncSessionDialog();
  $("dlg-session").showModal();
}

function syncSessionDialog() {
  const docId = document.querySelector('input[name="session-doc"]:checked')?.value || "";
  const doc = state.docs.find((d) => d.id === docId);
  $("session-topic-field").classList.toggle("hidden", !doc);
  $("session-free-topic-field").classList.toggle("hidden", !!doc);
  if (doc) {
    $("session-topic").innerHTML = `<option value="">Continue where I left off</option>` +
      doc.topics.map((t) => `<option>${escapeHtml(t)}</option>`).join("");
  }
}

/* ───────────── tutor / chat ───────────── */
function renderChat() {
  const s = state.session;
  const stream = $("chat-stream");
  stream.innerHTML = "";
  renderPanel();
  if (!s) {
    $("chat-title").textContent = "Start a learning session";
    $("chat-sub").textContent = "Pick a document and the tutor will take you through it topic by topic.";
    $("current-topic-chip").classList.add("hidden");
    const ready = state.docs.filter((d) => d.status === "ready");
    stream.innerHTML = `<div class="welcome">
      <h2>What would you like to master today?</h2>
      <p class="muted">The tutor won't just give you answers. It asks questions grounded in your textbook, scores each answer, and moves you on only when you've understood.</p>
      <div class="welcome-steps">
        <div class="card welcome-step"><span class="step-num">1</span><b>Upload a PDF</b>It's indexed in FAISS and split into topics.</div>
        <div class="card welcome-step"><span class="step-num">2</span><b>Answer questions</b>Each answer is scored from 0 to 100.</div>
        <div class="card welcome-step"><span class="step-num">3</span><b>Reach ${threshold()}%</b>Then you move on to the next topic.</div>
      </div>
      <div class="welcome-docs">
        ${ready.map((d) => `<button class="btn btn-primary btn-sm" data-start-doc="${d.id}">Study ${escapeHtml(d.filename)}</button>`).join("")}
        <button class="btn ${ready.length ? "btn-ghost" : "btn-primary"} btn-sm" data-upload="1">⇪ ${ready.length ? "Upload another PDF" : "Upload your first PDF"}</button>
        <button class="btn btn-ghost btn-sm" data-new-session="1">Open topic…</button></div>
    </div>`;
    return;
  }

  $("chat-title").textContent = s.title;
  const total = s.curriculum.length;
  $("chat-sub").textContent = s.document_name
    ? `${Math.min(s.current_topic_index, total)} of ${total} topics mastered`
    : "Open discussion";
  const chip = $("current-topic-chip");
  chip.textContent = s.completed ? "✓ All topics mastered" : `Now: ${s.current_topic}`;
  chip.classList.remove("hidden");

  for (const m of s.messages || []) appendMessage(m, false);
  // Only the tutor's opening question so far: offer quick ways to begin.
  if ((s.messages || []).length <= 1 && !s.completed) {
    const topic = s.current_topic || s.title;
    stream.insertAdjacentHTML("beforeend", `<div class="welcome-docs" id="starter-chips">
      <button class="btn btn-ghost btn-sm" data-prompt="Explain the basics of ${escapeHtml(topic)} from the textbook, then quiz me.">Explain the basics first</button>
      <button class="btn btn-ghost btn-sm" data-prompt="I think I already know ${escapeHtml(topic)}. Test me with a hard question.">Test me</button></div>`);
  }
  const lastAssistant = [...(s.messages || [])].reverse().find((m) => m.role === "assistant");
  renderTrace(lastAssistant?.agent_trace);
  scrollToBottom();
}

function agentLabel(agent) {
  if (!agent) return { cls: "tag-socrates", text: "Tutor" };
  if (agent.startsWith("hint")) {
    const level = (agent.match(/l(\d)$/) || [])[1] || 1;
    return { cls: "tag-hint", text: `Hint agent · level ${level}` };
  }
  return { cls: "tag-socrates", text: agent.endsWith("local") ? "Tutor (offline)" : "Tutor" };
}

function messageHtml(m) {
  if (m.role === "user") {
    return `<div class="msg user"><div class="msg-avatar">${escapeHtml((state.user?.name || "Y")[0].toUpperCase())}</div>
      <div class="msg-body"><div class="bubble">${escapeHtml(m.content)}</div></div></div>`;
  }
  const label = agentLabel(m.agent_used);
  const isHint = m.agent_used?.startsWith("hint");
  let extra = "";
  if (m.score !== null && m.score !== undefined && m.score >= 0) {
    const passed = m.score >= threshold();
    const fb = m.evaluation_feedback || {};
    extra += `<div class="score-card">
      <span class="score-num ${scoreClass(m.score)}">${Math.round(m.score)}</span>
      ${meter(m.score)}
      <span class="score-label">${passed ? "Mastered" : `needs ${threshold()} to advance`}</span>
      ${fb.got_right || fb.missing ? `<div class="score-feedback">${fb.got_right ? `<b>Right:</b> ${escapeHtml(fb.got_right)} ` : ""}${fb.missing ? `<b>Missing:</b> ${escapeHtml(fb.missing)}` : ""}</div>` : ""}
    </div>`;
  }
  if (m.sources?.length) {
    const id = "src" + Math.random().toString(36).slice(2, 8);
    extra += `<div class="sources" id="${id}"><span class="small muted">Sources:</span>${m.sources.map((src, i) =>
      `<button class="source-chip" data-src="${id}-${i}" aria-expanded="false">p. ${src.page} · ${Number(src.score).toFixed(2)}</button>`).join("")}
      ${m.sources.map((src, i) => `<div class="source-text hidden" id="${id}-${i}"><strong>Page ${src.page}${src.filename ? " · " + escapeHtml(src.filename) : ""}</strong>\n${escapeHtml(src.text)}</div>`).join("")}
    </div>`;
  }
  return `<div class="msg assistant ${isHint ? "hint" : ""}"><div class="msg-avatar">${isHint ? "💡" : "Σ"}</div>
    <div class="msg-body"><div class="msg-head"><span class="agent-tag ${label.cls}">${label.text}</span>${m.topic ? `<span>· ${escapeHtml(m.topic)}</span>` : ""}</div>
    <div class="bubble">${renderMarkdown(m.content)}</div>${extra}</div></div>`;
}

function appendMessage(m, scroll = true) {
  const stream = $("chat-stream");
  $("starter-chips")?.remove();
  stream.insertAdjacentHTML("beforeend", messageHtml(m));
  if (m.role === "assistant" && m.score >= threshold() && m.topic) {
    stream.insertAdjacentHTML("beforeend", `<div class="event">✓ Mastered “${escapeHtml(m.topic)}”</div>`);
  }
  if (scroll) scrollToBottom();
}

function scrollToBottom() { const s = $("chat-stream"); s.scrollTop = s.scrollHeight; }

function showTyping() {
  const steps = ["Retrieving passages", "Scoring your answer", "Writing a reply"];
  $("chat-stream").insertAdjacentHTML("beforeend", `<div class="typing" id="typing">
    <div class="msg-avatar">Σ</div><span class="dots"><span></span><span></span><span></span></span>
    <span class="typing-steps">${steps.map((s, i) => `<span class="typing-step ${i === 0 ? "on" : ""}">${s}</span>${i < 2 ? "<span>→</span>" : ""}`).join("")}</span></div>`);
  scrollToBottom();
  let i = 0;
  const timer = setInterval(() => {
    i = Math.min(i + 1, steps.length - 1);
    document.querySelectorAll("#typing .typing-step").forEach((el, j) => el.classList.toggle("on", j === i));
  }, 1400);
  return () => { clearInterval(timer); $("typing")?.remove(); };
}

async function sendMessage(text) {
  const message = (text ?? $("chat-input").value).trim();
  if (!message || state.sending) return;
  if (!state.session) { openNewSessionDialog(); toast("Start a session first"); return; }
  state.sending = true;
  $("btn-send").disabled = true;
  $("chat-input").value = "";
  autosize();
  appendMessage({ role: "user", content: message });
  const stopTyping = showTyping();
  try {
    const data = await api("/chat/message", { method: "POST", body: JSON.stringify({ session_id: state.session.id, message }) });
    stopTyping();
    const reply = {
      role: "assistant", content: data.response, agent_used: data.agent_used, score: data.evaluation_score,
      evaluation_feedback: data.evaluation_feedback, sources: data.sources, topic: data.topic, agent_trace: data.agent_trace,
      hint_level: data.hint_level,
    };
    state.session.messages = [...(state.session.messages || []), { role: "user", content: message }, reply];
    Object.assign(state.session, data.session, { messages: state.session.messages });
    appendMessage(reply);
    if (data.advanced && data.session.completed) toast("You've mastered every topic in this document!", "success");
    else if (data.advanced) toast(`Next topic: ${data.session.current_topic}`, "success");
    renderPanel();
    renderTrace(data.agent_trace);
    const quotaHit = (data.agent_trace || []).some((t) => /quota/i.test(t.detail));
    if (quotaHit && !state.quotaWarned) {
      state.quotaWarned = true;
      toast("Gemini's free daily limit is used up, so replies are in offline mode until it resets (midnight US Pacific time).", "error");
    }
    $("chat-sub").textContent = data.session.document_name
      ? `${Math.min(data.session.current_topic_index, data.session.curriculum.length)} of ${data.session.curriculum.length} topics mastered` : "Open discussion";
    $("current-topic-chip").textContent = data.session.completed ? "✓ All topics mastered" : `Now: ${data.session.current_topic}`;
    loadSessions();
  } catch (err) {
    stopTyping();
    toast("Couldn't get a reply: " + err.message, "error");
  } finally {
    state.sending = false;
    $("btn-send").disabled = false;
    $("chat-input").focus();
  }
}

function autosize() {
  const t = $("chat-input");
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight, 200) + "px";
}

/* ───────────── session panel ───────────── */
function renderPanel() {
  const s = state.session;
  const list = $("curriculum");
  if (!s) {
    list.innerHTML = `<li class="muted small">Start a session to see its topics here.</li>`;
    $("curriculum-count").textContent = "";
    renderTrace(null);
    return;
  }
  const prof = Object.fromEntries((s.proficiency || []).map((p) => [p.concept, p]));
  const done = s.curriculum.filter((t, i) => i < s.current_topic_index || prof[t]?.mastered).length;
  $("curriculum-count").textContent = `${done}/${s.curriculum.length}`;
  list.innerHTML = s.curriculum.map((t, i) => {
    const p = prof[t] || {};
    const isDone = i < s.current_topic_index || p.mastered;
    const isCurrent = i === s.current_topic_index;
    const cls = isDone ? "done" : isCurrent ? "current" : "";
    return `<li class="topic ${cls}"><span class="topic-mark"></span>
      <span class="topic-name">${escapeHtml(t)}</span>
      <span class="topic-score" title="Best score">${p.attempts ? Math.round(p.best) : "–"}</span>
      ${meter(p.best || 0)}</li>`;
  }).join("");
}

const AGENT_COLORS = { knowledge: "var(--c-knowledge)", evaluator: "var(--c-evaluator)", socrates: "var(--c-socrates)", hint: "var(--c-hint)" };
const AGENT_NAMES = { knowledge: "Knowledge agent", evaluator: "Evaluator agent", socrates: "Tutor agent", hint: "Hint agent" };

function renderTrace(trace) {
  const el = $("last-turn");
  if (!trace?.length) { el.className = "muted small"; el.textContent = "The agents' steps for each reply appear here."; return; }
  el.className = "";
  el.innerHTML = `<ol class="trace">${trace.map((t) => `<li><span class="trace-dot" style="background:${AGENT_COLORS[t.agent] || "var(--muted)"}"></span>
    <div><b>${AGENT_NAMES[t.agent] || escapeHtml(t.agent)}</b>${escapeHtml(t.detail)}</div></li>`).join("")}</ol>`;
}

/* ───────────── progress ───────────── */
async function loadProgress() {
  try {
    const data = await api("/chat/proficiency");
    renderProgress(data);
  } catch (err) { toast(err.message, "error"); }
}

function renderProgress(data) {
  const all = data.documents.flatMap((d) => d.topics);
  const practiced = all.filter((t) => t.attempts > 0);
  const mastered = all.filter((t) => t.mastered).length;
  const avg = practiced.length ? practiced.reduce((a, t) => a + t.mastery, 0) / practiced.length : 0;
  const due = all.filter((t) => t.review_due && t.attempts > 0).length;
  $("kpis").innerHTML = [
    ["Topics mastered", `${mastered}`],
    ["Topics practised", `${practiced.length}`],
    ["Average proficiency", `${Math.round(avg)}%`],
    ["Due for review", `${due}`],
  ].map(([label, value]) => `<div class="card kpi"><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div></div>`).join("");

  if (!data.documents.length) {
    $("proficiency").innerHTML = `<div class="card empty">No progress yet. Upload a document and start a session.</div>`;
    return;
  }
  $("proficiency").innerHTML = data.documents.map((d) => `
    <section class="card prof-doc">
      <div class="prof-head">
        <h2 style="font-size:1rem">${escapeHtml(d.document_name)}</h2>
        <span class="small muted">${d.mastered_count}/${d.topics.length} mastered</span>
      </div>
      <div class="vector" title="Proficiency vector: one value per topic, in curriculum order">proficiency vector = [${d.vector.map((v) => Math.round(v)).join(", ")}]</div>
      <div class="prof-rows">${d.topics.map((t) => `
        <div class="prof-row">
          <span class="prof-name">${t.mastered ? "✓ " : ""}${escapeHtml(t.concept)}</span>
          ${meter(t.mastery)}
          <span class="prof-val" style="color:${t.attempts ? scoreColor(t.mastery) : "var(--muted)"}">${t.attempts ? Math.round(t.mastery) : "–"}</span>
          <span class="prof-meta">${t.attempts ? `best ${Math.round(t.best)} · ${t.attempts} ${t.attempts === 1 ? "try" : "tries"} · ${relTime(t.last_reviewed)}` : "not started"}
            ${t.review_due && t.attempts ? ` <button class="btn btn-ghost btn-sm" data-review-doc="${d.document_id || ""}" data-review-topic="${escapeHtml(t.concept)}">Review</button>` : ""}</span>
        </div>`).join("")}
      </div>
    </section>`).join("");
}

/* ───────────── wiring ───────────── */
function setupEvents() {
  // Any button with data-upload opens the PDF file picker.
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-upload]")) return;
    if ($("dlg-session").open) $("dlg-session").close("cancel");
    closeSidebar();
    $("file-input").click();
  });
  document.querySelectorAll(".nav-item").forEach((b) => (b.onclick = () => setView(b.dataset.view)));
  $("btn-new-session").onclick = () => { closeSidebar(); openNewSessionDialog(); };
  $("btn-settings").onclick = openSettings;
  $("btn-theme").onclick = toggleTheme;
  $("btn-open-sidebar").onclick = openSidebar;
  $("btn-close-sidebar").onclick = closeSidebar;
  $("scrim").onclick = closeSidebar;
  $("btn-toggle-panel").onclick = () => $("session-panel").classList.toggle("open");

  $("session-list").onclick = (e) => {
    const del = e.target.closest("[data-del-session]");
    if (del) { e.stopPropagation(); deleteSession(del.dataset.delSession); return; }
    const item = e.target.closest("[data-session]");
    if (item) openSession(item.dataset.session);
  };
  $("session-list").onkeydown = (e) => {
    const item = e.target.closest("[data-session]");
    if (item && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openSession(item.dataset.session); }
  };

  $("chat-stream").onclick = (e) => {
    const t = e.target.closest("button");
    if (!t) return;
    if (t.dataset.startDoc) startSession(t.dataset.startDoc, null);
    if (t.dataset.goto) setView(t.dataset.goto);
    if (t.dataset.newSession) openNewSessionDialog();
    if (t.dataset.prompt) sendMessage(t.dataset.prompt);
    if (t.dataset.src) {
      const box = $(t.dataset.src);
      const open = box.classList.toggle("hidden") === false;
      t.setAttribute("aria-expanded", String(open));
    }
  };

  $("proficiency").onclick = (e) => {
    const b = e.target.closest("[data-review-topic]");
    if (b) { setView("tutor"); startSession(b.dataset.reviewDoc || null, b.dataset.reviewTopic); }
  };

  $("composer").onsubmit = (e) => { e.preventDefault(); sendMessage(); };
  $("chat-input").addEventListener("input", autosize);
  $("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage(); }
  });
  $("btn-hint").onclick = () => sendMessage("I'm stuck. Can I get a hint?");

  $("dlg-session").addEventListener("close", () => {
    if ($("dlg-session").returnValue !== "default") return;
    const docId = document.querySelector('input[name="session-doc"]:checked')?.value || null;
    const topic = docId ? $("session-topic").value : $("session-free-topic").value.trim();
    setView("tutor");
    startSession(docId, topic || null);
  });
  $("dlg-settings").addEventListener("close", () => { if ($("dlg-settings").returnValue === "default") saveKey(); });
}

async function init() {
  if (location.protocol === "file:") {
    // Opened index.html straight from disk: there's no server behind it.
    document.body.innerHTML = `<div class="welcome" style="min-height:100vh;padding:24px 16px">
      <h2>Open SocraticAI through its server</h2>
      <p class="muted">This page was opened as a file, so it can't talk to the backend.
      Run <code>python main.py</code> in the <code>backend</code> folder, then go to
      <a href="http://127.0.0.1:8000">http://127.0.0.1:8000</a>.</p></div>`;
    return;
  }
  setupAuth();
  setupLibrary();
  setupEvents();
  loadSettings();
  if (!state.token) { showAuth(); return; }
  try {
    state.user = await api("/auth/me");
    showApp();
  } catch (err) {
    showAuth();
    if (err.message === SERVER_DOWN_MESSAGE) toast(err.message, "error");
  }
}

document.addEventListener("DOMContentLoaded", init);
