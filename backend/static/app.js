/**
 * SocraticAI - Frontend Application Logic (Vanilla JS)
 */

// State
let token = localStorage.getItem("socratic_token") || null;
let currentUser = null;
let activeSessionId = null;
let documentsList = [];

// DOM Elements
const systemStatusEl = document.getElementById("system-status");
const userLoggedOutEl = document.getElementById("user-logged-out");
const userLoggedInEl = document.getElementById("user-logged-in");
const userDisplayNameEl = document.getElementById("user-display-name");
const authModalEl = document.getElementById("auth-modal");
const formLoginEl = document.getElementById("form-login");
const formRegisterEl = document.getElementById("form-register");
const loginErrorEl = document.getElementById("login-error");
const registerErrorEl = document.getElementById("register-error");

// Tabs
const tabBtns = document.querySelectorAll(".tab-btn");
const tabContents = document.querySelectorAll(".tab-content");

// Chat Elements
const selectDocContextEl = document.getElementById("select-doc-context");
const inputTopicContextEl = document.getElementById("input-topic-context");
const btnCreateSessionEl = document.getElementById("btn-create-session");
const btnNewSessionEl = document.getElementById("btn-new-session");
const sessionsListEl = document.getElementById("sessions-list");
const activeSessionTitleEl = document.getElementById("active-session-title");
const activeSessionSubtitleEl = document.getElementById("active-session-subtitle");
const activeConceptTagEl = document.getElementById("active-concept-tag");
const chatStreamEl = document.getElementById("chat-stream");
const chatFormEl = document.getElementById("chat-form");
const chatInputEl = document.getElementById("chat-input");
const btnSendMessageEl = document.getElementById("btn-send-message");

// Docs Elements
const uploadDropzoneEl = document.getElementById("upload-dropzone");
const fileUploadInputEl = document.getElementById("file-upload-input");
const btnBrowseFileEl = document.getElementById("btn-browse-file");
const uploadStatusEl = document.getElementById("upload-status");
const docsGridEl = document.getElementById("docs-grid");
const btnRefreshDocsEl = document.getElementById("btn-refresh-docs");

// Mastery Elements
const kpiConceptsCountEl = document.getElementById("kpi-concepts-count");
const kpiMasteredCountEl = document.getElementById("kpi-mastered-count");
const kpiAvgMasteryEl = document.getElementById("kpi-avg-mastery");
const masteryTableBodyEl = document.getElementById("mastery-table-body");
const btnRefreshMasteryEl = document.getElementById("btn-refresh-mastery");

// Toast
const toastEl = document.getElementById("toast");

/* ==========================================================================
   API HELPER
   ========================================================================== */
async function apiCall(endpoint, options = {}) {
  const headers = options.headers || {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (!options.isFormData && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(endpoint, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    // Token expired or invalid
    clearAuth();
    showToast("Session expired. Please sign in again.", "error");
    throw new Error("Unauthorized");
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const errorMsg = data.detail || "Request failed";
    throw new Error(errorMsg);
  }
  return data;
}

function showToast(message, type = "info") {
  toastEl.textContent = message;
  toastEl.className = "toast";
  if (type === "error") toastEl.style.borderColor = "#f43f5e";
  else if (type === "success") toastEl.style.borderColor = "#10b981";
  else toastEl.style.borderColor = "#6366f1";

  toastEl.classList.remove("hidden");
  setTimeout(() => {
    toastEl.classList.add("hidden");
  }, 3500);
}

/* ==========================================================================
   AUTH LOGIC
   ========================================================================== */
function updateAuthUI() {
  if (token && currentUser) {
    userLoggedOutEl.classList.add("hidden");
    userLoggedInEl.classList.remove("hidden");
    userDisplayNameEl.textContent = currentUser.name || "Student";
  } else {
    userLoggedOutEl.classList.remove("hidden");
    userLoggedInEl.classList.add("hidden");
  }
}

function setAuth(newToken, user) {
  token = newToken;
  currentUser = user;
  localStorage.setItem("socratic_token", token);
  localStorage.setItem("socratic_user", JSON.stringify(user));
  updateAuthUI();
  loadDocuments();
  loadSessions();
  loadMastery();
}

function clearAuth() {
  token = null;
  currentUser = null;
  localStorage.removeItem("socratic_token");
  localStorage.removeItem("socratic_user");
  updateAuthUI();
}

async function verifyExistingAuth() {
  if (!token) return;
  try {
    const user = await apiCall("/auth/me");
    currentUser = user;
    updateAuthUI();
    loadDocuments();
    loadSessions();
    loadMastery();
  } catch (err) {
    clearAuth();
  }
}

/* ==========================================================================
   TAB NAVIGATION
   ========================================================================== */
function setupTabs() {
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      tabBtns.forEach((b) => b.classList.remove("active"));
      tabContents.forEach((c) => c.classList.remove("active"));

      btn.classList.add("active");
      document.getElementById(targetTab).classList.add("active");

      if (targetTab === "tab-docs") loadDocuments();
      if (targetTab === "tab-mastery") loadMastery();
    });
  });
}

function switchTab(tabId) {
  tabBtns.forEach((b) => {
    if (b.getAttribute("data-tab") === tabId) b.classList.add("active");
    else b.classList.remove("active");
  });
  tabContents.forEach((c) => {
    if (c.id === tabId) c.classList.add("active");
    else c.classList.remove("active");
  });
}

/* ==========================================================================
   AUTH MODAL & FORMS
   ========================================================================== */
function setupAuthEvents() {
  const btnOpenLogin = document.getElementById("btn-open-login");
  const btnOpenRegister = document.getElementById("btn-open-register");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const authTabLogin = document.getElementById("auth-tab-login");
  const authTabRegister = document.getElementById("auth-tab-register");
  const btnLogout = document.getElementById("btn-logout");
  const btnDemoLogin = document.getElementById("btn-demo-login");

  btnOpenLogin.addEventListener("click", () => {
    authModalEl.classList.remove("hidden");
    authTabLogin.click();
  });

  btnOpenRegister.addEventListener("click", () => {
    authModalEl.classList.remove("hidden");
    authTabRegister.click();
  });

  btnCloseModal.addEventListener("click", () => {
    authModalEl.classList.add("hidden");
  });

  authModalEl.addEventListener("click", (e) => {
    if (e.target === authModalEl) authModalEl.classList.add("hidden");
  });

  authTabLogin.addEventListener("click", () => {
    authTabLogin.classList.add("active");
    authTabRegister.classList.remove("active");
    formLoginEl.classList.remove("hidden");
    formRegisterEl.classList.add("hidden");
    loginErrorEl.classList.add("hidden");
  });

  authTabRegister.addEventListener("click", () => {
    authTabRegister.classList.add("active");
    authTabLogin.classList.remove("active");
    formRegisterEl.classList.remove("hidden");
    formLoginEl.classList.add("hidden");
    registerErrorEl.classList.add("hidden");
  });

  btnLogout.addEventListener("click", () => {
    clearAuth();
    showToast("Signed out successfully.");
    resetChat();
  });

  // Login submit
  formLoginEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginErrorEl.classList.add("hidden");
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;

    try {
      const data = await apiCall("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setAuth(data.access_token, { name: data.name, email });
      authModalEl.classList.add("hidden");
      showToast(`Welcome back, ${data.name}!`, "success");
    } catch (err) {
      loginErrorEl.textContent = err.message || "Invalid email or password";
      loginErrorEl.classList.remove("hidden");
    }
  });

  // Register submit
  formRegisterEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    registerErrorEl.classList.add("hidden");
    const name = document.getElementById("reg-name").value.trim();
    const email = document.getElementById("reg-email").value.trim();
    const password = document.getElementById("reg-password").value;

    try {
      const data = await apiCall("/auth/register", {
        method: "POST",
        body: JSON.stringify({ name, email, password }),
      });
      setAuth(data.access_token, { name: data.name, email });
      authModalEl.classList.add("hidden");
      showToast(`Account created! Welcome, ${data.name}!`, "success");
    } catch (err) {
      registerErrorEl.textContent = err.message || "Registration failed";
      registerErrorEl.classList.remove("hidden");
    }
  });

  // Demo 1-Click Login
  btnDemoLogin.addEventListener("click", async () => {
    loginErrorEl.classList.add("hidden");
    try {
      // Attempt login
      const data = await apiCall("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: "student@socratic.ai", password: "password123" }),
      });
      setAuth(data.access_token, { name: data.name, email: "student@socratic.ai" });
      authModalEl.classList.add("hidden");
      showToast(`Signed in as demo student!`, "success");
    } catch (err) {
      // If demo user doesn't exist yet, register it
      try {
        const reg = await apiCall("/auth/register", {
          method: "POST",
          body: JSON.stringify({
            name: "Demo Student",
            email: "student@socratic.ai",
            password: "password123",
          }),
        });
        setAuth(reg.access_token, { name: reg.name, email: "student@socratic.ai" });
        authModalEl.classList.add("hidden");
        showToast("Demo account created and signed in!", "success");
      } catch (regErr) {
        loginErrorEl.textContent = "Could not complete demo login: " + regErr.message;
        loginErrorEl.classList.remove("hidden");
      }
    }
  });
}

/* ==========================================================================
   DOCUMENTS (RAG)
   ========================================================================== */
async function loadDocuments() {
  if (!token) return;
  try {
    const docs = await apiCall("/documents/");
    documentsList = docs;
    renderDocuments(docs);
    updateDocContextSelect(docs);
  } catch (err) {
    console.error("Failed to load documents", err);
  }
}

function updateDocContextSelect(docs) {
  selectDocContextEl.innerHTML = '<option value="">(No specific document - General)</option>';
  docs.forEach((d) => {
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = `${d.filename} (${d.chunks_count} chunks)`;
    selectDocContextEl.appendChild(opt);
  });
}

function renderDocuments(docs) {
  if (!docs || docs.length === 0) {
    docsGridEl.innerHTML = `
      <div class="empty-hint" style="grid-column: 1 / -1;">
        No documents uploaded yet. Upload a PDF textbook to enhance Socratic questioning.
      </div>`;
    return;
  }

  docsGridEl.innerHTML = docs
    .map(
      (d) => `
    <div class="doc-card">
      <div>
        <div class="doc-card-title">&#128196; ${escapeHtml(d.filename)}</div>
        <div class="doc-card-meta" style="margin-top: 0.5rem;">
          <span class="meta-pill">&#9881; ${d.chunks_count} chunks</span>
          <span class="meta-pill" style="color: ${d.status === "ready" ? "var(--accent-green)" : "var(--accent-amber)"}">
            ${d.status.toUpperCase()}
          </span>
        </div>
        ${
          d.topics && d.topics.length > 0
            ? `<div class="doc-topics-chips" style="margin-top: 0.75rem;">
                ${d.topics.slice(0, 5).map((t) => `<span class="topic-chip">${escapeHtml(t)}</span>`).join("")}
              </div>`
            : ""
        }
      </div>
      <div class="doc-card-actions">
        <button class="btn btn-primary btn-sm full-width" onclick="studyDocument('${d.id}', '${escapeHtml(d.filename)}')">
          &#128172; Study This
        </button>
        <button class="btn btn-secondary btn-sm" onclick="deleteDocument('${d.id}')" title="Delete">
          &#128465;
        </button>
      </div>
    </div>
  `
    )
    .join("");
}

window.studyDocument = function (docId, filename) {
  switchTab("tab-chat");
  selectDocContextEl.value = docId;
  inputTopicContextEl.value = filename.replace(/\.pdf$/i, "");
  createSession(docId, inputTopicContextEl.value);
};

window.deleteDocument = async function (docId) {
  if (!confirm("Are you sure you want to delete this document?")) return;
  try {
    await apiCall(`/documents/${docId}`, { method: "DELETE" });
    showToast("Document deleted", "info");
    loadDocuments();
  } catch (err) {
    showToast("Failed to delete document: " + err.message, "error");
  }
};

function setupUploadEvents() {
  btnBrowseFileEl.addEventListener("click", () => fileUploadInputEl.click());

  uploadDropzoneEl.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadDropzoneEl.classList.add("dragover");
  });

  uploadDropzoneEl.addEventListener("dragleave", () => {
    uploadDropzoneEl.classList.remove("dragover");
  });

  uploadDropzoneEl.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadDropzoneEl.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  fileUploadInputEl.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  });

  btnRefreshDocsEl.addEventListener("click", loadDocuments);
}

async function handleFileUpload(file) {
  if (!token) {
    showToast("Please sign in first to upload documents.", "error");
    authModalEl.classList.remove("hidden");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showToast("Only PDF files are supported.", "error");
    return;
  }

  uploadStatusEl.className = "upload-status";
  uploadStatusEl.textContent = `Uploading "${file.name}" and extracting RAG knowledge...`;
  uploadStatusEl.classList.remove("hidden");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await apiCall("/documents/upload", {
      method: "POST",
      body: formData,
      isFormData: true,
    });
    uploadStatusEl.className = "upload-status success";
    uploadStatusEl.textContent = `Uploaded! Chunks are indexing in background.`;
    showToast("Document uploaded successfully!", "success");
    loadDocuments();
  } catch (err) {
    uploadStatusEl.className = "upload-status error";
    uploadStatusEl.textContent = `Upload failed: ${err.message}`;
  }
}

/* ==========================================================================
   CHAT & LEARNING SESSIONS
   ========================================================================== */
async function loadSessions() {
  if (!token) return;
  try {
    const sessions = await apiCall("/chat/sessions");
    renderSessionsList(sessions);
  } catch (err) {
    console.error("Failed to load sessions", err);
  }
}

function renderSessionsList(sessions) {
  if (!sessions || sessions.length === 0) {
    sessionsListEl.innerHTML = '<div class="empty-hint">No sessions yet. Click "+ New Session" to begin.</div>';
    return;
  }

  sessionsListEl.innerHTML = sessions
    .map(
      (s) => `
    <div class="session-item ${s.id === activeSessionId ? "active" : ""}" onclick="selectSession('${s.id}')">
      <div class="session-item-topic">&#128172; ${escapeHtml(s.topic || "General Discussion")}</div>
      <div class="session-item-date">${new Date(s.created_at).toLocaleDateString()} ${new Date(s.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
    </div>
  `
    )
    .join("");
}

window.selectSession = async function (sessionId) {
  if (!token) return;
  activeSessionId = sessionId;

  // Highlight in sidebar
  document.querySelectorAll(".session-item").forEach((el) => el.classList.remove("active"));
  const clicked = document.querySelector(`.session-item[onclick*="${sessionId}"]`);
  if (clicked) clicked.classList.add("active");

  try {
    const messages = await apiCall(`/chat/sessions/${sessionId}/messages`);
    activeSessionTitleEl.textContent = "Socratic Learning Session";
    activeSessionSubtitleEl.textContent = "Dialectical inquiry active. Answer questions to demonstrate your reasoning.";
    renderMessages(messages);
  } catch (err) {
    showToast("Could not load session messages", "error");
  }
};

async function createSession(documentId = null, topic = null) {
  if (!token) {
    showToast("Please sign in to start a learning session.", "error");
    authModalEl.classList.remove("hidden");
    return;
  }

  try {
    const res = await apiCall("/chat/session", {
      method: "POST",
      body: JSON.stringify({
        document_id: documentId || selectDocContextEl.value || null,
        topic: topic || inputTopicContextEl.value || "General Concept Inquiry",
      }),
    });

    activeSessionId = res.session_id;
    activeSessionTitleEl.textContent = topic || "New Socratic Session";
    activeSessionSubtitleEl.textContent = "AI Tutor initialized. Tell me what you know or ask to be questioned!";
    chatStreamEl.innerHTML = "";

    // Add greeting from AI
    appendMessage({
      role: "assistant",
      content: `Hello! I am your Socratic AI Tutor. We are exploring "${escapeHtml(topic || "your selected topic")}".\n\nTo begin: In your own words, what do you already understand about this topic, or what specific problem would you like to explore?`,
      agent_used: "socratic_guide",
      score: null,
      sources: [],
    });

    loadSessions();
    showToast("Session started!", "success");
  } catch (err) {
    showToast("Failed to create session: " + err.message, "error");
  }
}

function resetChat() {
  activeSessionId = null;
  activeSessionTitleEl.textContent = "Select or start a learning session";
  activeSessionSubtitleEl.textContent = "Engage in dialectical inquiry with AI agents";
  activeConceptTagEl.classList.add("hidden");
  chatStreamEl.innerHTML = `
    <div class="chat-welcome">
      <div class="welcome-icon">&#129302;</div>
      <h3>Welcome to SocraticAI</h3>
      <p>I won't just give you the answer. I will guide you with targeted questions, evaluate your conceptual clarity, and provide progressive hints to help you truly master the topic.</p>
    </div>
  `;
}

function renderMessages(messages) {
  chatStreamEl.innerHTML = "";
  if (!messages || messages.length === 0) {
    appendMessage({
      role: "assistant",
      content: "Hello! This session is open. Share your understanding or ask a foundational question to begin our inquiry.",
      agent_used: "socratic_guide",
    });
    return;
  }
  messages.forEach((m) => appendMessage(m));
  scrollChatToBottom();
}

function appendMessage(m) {
  const isUser = m.role === "user";
  const row = document.createElement("div");
  row.className = `message-row ${isUser ? "user" : "assistant"}`;

  let headerHtml = "";
  if (isUser) {
    headerHtml = `<div class="message-header"><span>You</span></div>`;
  } else {
    let agentBadge = "";
    if (m.agent_used && m.agent_used.includes("hint")) {
      agentBadge = `<span class="agent-badge badge-hint">&#128161; Hint Agent (L${m.hint_level || 1})</span>`;
    } else if (m.agent_used && m.agent_used.includes("evaluator")) {
      agentBadge = `<span class="agent-badge badge-evaluator">&#127919; Evaluator</span>`;
    } else {
      agentBadge = `<span class="agent-badge badge-socratic">&#129504; Socratic Guide</span>`;
    }
    headerHtml = `<div class="message-header">${agentBadge}</div>`;
  }

  let scoreHtml = "";
  if (!isUser && m.score !== null && m.score !== undefined) {
    let scoreClass = "score-mid";
    let statusText = "Good progress";
    if (m.score >= 80) {
      scoreClass = "score-high";
      statusText = "Mastery demonstrated!";
    } else if (m.score < 50) {
      scoreClass = "score-low";
      statusText = "Needs refinement";
    }
    scoreHtml = `
      <div class="message-score-card">
        <span>Evaluated Understanding: <strong>${statusText}</strong></span>
        <span class="score-tag ${scoreClass}">${m.score}%</span>
      </div>
    `;
  }

  let sourcesHtml = "";
  if (!isUser && m.sources && m.sources.length > 0) {
    const sourceId = "source-" + Math.random().toString(36).substr(2, 9);
    sourcesHtml = `
      <div class="sources-accordion">
        <button class="sources-btn" onclick="toggleSources('${sourceId}')">
          &#128214; View Textbook Citations (${m.sources.length}) &#9662;
        </button>
        <div id="${sourceId}" class="sources-list hidden">
          ${m.sources
            .map(
              (src, idx) => `
            <div class="source-chunk">
              <strong>[Citation ${idx + 1}]</strong> ${escapeHtml(typeof src === "string" ? src : src.text || JSON.stringify(src))}
            </div>
          `
            )
            .join("")}
        </div>
      </div>
    `;
  }

  row.innerHTML = `
    ${headerHtml}
    <div class="message-bubble">${escapeHtml(m.content)}</div>
    ${scoreHtml}
    ${sourcesHtml}
  `;

  chatStreamEl.appendChild(row);
  scrollChatToBottom();
}

window.toggleSources = function (id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle("hidden");
};

function scrollChatToBottom() {
  chatStreamEl.scrollTop = chatStreamEl.scrollHeight;
}

function setupChatEvents() {
  btnCreateSessionEl.addEventListener("click", () => {
    createSession(selectDocContextEl.value, inputTopicContextEl.value);
  });

  btnNewSessionEl.addEventListener("click", () => {
    inputTopicContextEl.value = "";
    createSession(selectDocContextEl.value, "General Concept Inquiry");
  });

  // Enter to send
  chatInputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatFormEl.dispatchEvent(new Event("submit"));
    }
  });

  // Chat submit
  chatFormEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = chatInputEl.value.trim();
    if (!message) return;

    if (!token) {
      showToast("Please sign in to chat.", "error");
      authModalEl.classList.remove("hidden");
      return;
    }

    if (!activeSessionId) {
      // Auto create session if not exists
      try {
        const res = await apiCall("/chat/session", {
          method: "POST",
          body: JSON.stringify({
            document_id: selectDocContextEl.value || null,
            topic: inputTopicContextEl.value || "General Concept Inquiry",
          }),
        });
        activeSessionId = res.session_id;
        loadSessions();
      } catch (err) {
        showToast("Error creating session: " + err.message, "error");
        return;
      }
    }

    // Append user message immediately
    appendMessage({ role: "user", content: message });
    chatInputEl.value = "";

    // Show AI thinking indicator
    const thinkingRow = document.createElement("div");
    thinkingRow.className = "message-row assistant";
    thinkingRow.id = "thinking-indicator";
    thinkingRow.innerHTML = `
      <div class="message-header"><span class="agent-badge badge-socratic">&#9881; Multi-Agent Reasoning...</span></div>
      <div class="message-bubble" style="color: var(--text-dim); font-style: italic;">Consulting textbook RAG and formulating inquiry...</div>
    `;
    chatStreamEl.appendChild(thinkingRow);
    scrollChatToBottom();
    btnSendMessageEl.disabled = true;

    try {
      const data = await apiCall("/chat/message", {
        method: "POST",
        body: JSON.stringify({
          session_id: activeSessionId,
          message: message,
        }),
      });

      // Remove thinking indicator
      const ind = document.getElementById("thinking-indicator");
      if (ind) ind.remove();

      // Show assistant response
      appendMessage({
        role: "assistant",
        content: data.response,
        agent_used: data.agent_used,
        score: data.evaluation_score,
        sources: data.sources,
      });

      // Update concept badge
      if (data.current_concept) {
        activeConceptTagEl.textContent = `Concept: ${data.current_concept}`;
        activeConceptTagEl.classList.remove("hidden");
      }

      // Reload mastery stats in background
      loadMastery();
    } catch (err) {
      const ind = document.getElementById("thinking-indicator");
      if (ind) ind.remove();
      showToast("Failed to get response: " + err.message, "error");
    } finally {
      btnSendMessageEl.disabled = false;
      chatInputEl.focus();
    }
  });

  // Quick Prompt Chips
  document.querySelectorAll(".chip[data-prompt]").forEach((chip) => {
    chip.addEventListener("click", () => {
      chatInputEl.value = chip.getAttribute("data-prompt");
      chatFormEl.dispatchEvent(new Event("submit"));
    });
  });
}

/* ==========================================================================
   MASTERY ANALYTICS
   ========================================================================== */
async function loadMastery() {
  if (!token) return;
  try {
    const states = await apiCall("/chat/knowledge-state");
    renderMastery(states);
  } catch (err) {
    console.error("Failed to load mastery states", err);
  }
}

function renderMastery(states) {
  if (!states || states.length === 0) {
    kpiConceptsCountEl.textContent = "0";
    kpiMasteredCountEl.textContent = "0";
    kpiAvgMasteryEl.textContent = "0%";
    masteryTableBodyEl.innerHTML = `
      <tr>
        <td colspan="6" class="text-center text-muted" style="padding: 2rem;">
          No concepts evaluated yet. Start a Socratic learning session to track your knowledge state!
        </td>
      </tr>
    `;
    return;
  }

  const total = states.length;
  const mastered = states.filter((s) => s.mastery_score >= 80).length;
  const avg = Math.round(states.reduce((acc, s) => acc + s.mastery_score, 0) / total);

  kpiConceptsCountEl.textContent = total;
  kpiMasteredCountEl.textContent = mastered;
  kpiAvgMasteryEl.textContent = `${avg}%`;

  masteryTableBodyEl.innerHTML = states
    .map((s) => {
      let color = "var(--accent-rose)";
      if (s.mastery_score >= 80) color = "var(--accent-green)";
      else if (s.mastery_score >= 50) color = "var(--accent-amber)";

      return `
      <tr>
        <td><strong>${escapeHtml(s.concept)}</strong></td>
        <td><strong style="color: ${color}">${s.mastery_score}%</strong></td>
        <td>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill" style="width: ${s.mastery_score}%; background-color: ${color};"></div>
          </div>
        </td>
        <td>${s.attempts}</td>
        <td>${new Date(s.last_reviewed).toLocaleDateString()}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="practiceConcept('${escapeHtml(s.concept)}')">
            &#128172; Practice
          </button>
        </td>
      </tr>
    `;
    })
    .join("");
}

window.practiceConcept = function (concept) {
  switchTab("tab-chat");
  inputTopicContextEl.value = concept;
  createSession(null, concept);
};

/* ==========================================================================
   UTILITIES
   ========================================================================== */
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/* ==========================================================================
   API KEY SETTINGS
   ========================================================================== */
function setupApiKeyEvents() {
  const btnOpenApiKey = document.getElementById("btn-open-api-key");
  const btnCloseKeyModal = document.getElementById("btn-close-key-modal");
  const apiKeyModal = document.getElementById("api-key-modal");
  const formApiKey = document.getElementById("form-api-key");
  const inputGeminiKey = document.getElementById("input-gemini-key");
  const apiKeyStatusMsg = document.getElementById("api-key-status-msg");

  if (btnOpenApiKey) {
    btnOpenApiKey.addEventListener("click", () => {
      apiKeyModal.classList.remove("hidden");
      checkApiKeyStatus();
    });
  }

  if (btnCloseKeyModal) {
    btnCloseKeyModal.addEventListener("click", () => {
      apiKeyModal.classList.add("hidden");
    });
  }

  if (apiKeyModal) {
    apiKeyModal.addEventListener("click", (e) => {
      if (e.target === apiKeyModal) apiKeyModal.classList.add("hidden");
    });
  }

  if (formApiKey) {
    formApiKey.addEventListener("submit", async (e) => {
      e.preventDefault();
      const key = inputGeminiKey.value.trim();
      if (!key) {
        showToast("Please enter an API key", "error");
        return;
      }

      try {
        const res = await apiCall("/api/settings/api-key", {
          method: "POST",
          body: JSON.stringify({ api_key: key }),
        });
        apiKeyStatusMsg.className = "upload-status success";
        apiKeyStatusMsg.textContent = res.message || "Connected to Gemini!";
        apiKeyStatusMsg.classList.remove("hidden");
        showToast("Gemini API key saved!", "success");
        checkApiKeyStatus();
        setTimeout(() => {
          apiKeyModal.classList.add("hidden");
          apiKeyStatusMsg.classList.add("hidden");
        }, 1500);
      } catch (err) {
        apiKeyStatusMsg.className = "upload-status error";
        apiKeyStatusMsg.textContent = err.message || "Failed to save API key";
        apiKeyStatusMsg.classList.remove("hidden");
      }
    });
  }
}

async function checkApiKeyStatus() {
  try {
    const res = await fetch("/api/settings").then((r) => r.json());
    const apiKeyStatusText = document.getElementById("api-key-status-text");
    const currentEngineMode = document.getElementById("current-engine-mode");

    if (res.has_api_key) {
      if (apiKeyStatusText) apiKeyStatusText.textContent = "Gemini: Active 🟢";
      if (currentEngineMode) {
        currentEngineMode.textContent = `Gemini 1.5 Flash (${res.masked_key})`;
        currentEngineMode.style.color = "var(--accent-green)";
      }
    } else {
      if (apiKeyStatusText) apiKeyStatusText.textContent = "Set Gemini Key";
      if (currentEngineMode) {
        currentEngineMode.textContent = "Local Socratic Engine (Offline Heuristics)";
        currentEngineMode.style.color = "#818cf8";
      }
    }
  } catch (e) {
    console.error("Could not check API key settings", e);
  }
}

/* ==========================================================================
   INITIALIZATION
   ========================================================================== */
window.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupAuthEvents();
  setupUploadEvents();
  setupChatEvents();
  setupApiKeyEvents();

  if (btnRefreshMasteryEl) {
    btnRefreshMasteryEl.addEventListener("click", loadMastery);
  }

  // Check existing token
  verifyExistingAuth();
  checkApiKeyStatus();

  // Test backend connectivity
  fetch("/health")
    .then((r) => r.json())
    .then((d) => {
      if (d.status === "healthy") {
        systemStatusEl.textContent = "Backend: Online";
      }
    })
    .catch(() => {
      systemStatusEl.textContent = "Backend: Offline";
      systemStatusEl.style.color = "var(--accent-rose)";
    });
});
