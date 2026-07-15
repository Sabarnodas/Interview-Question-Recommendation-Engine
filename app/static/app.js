"use strict";

const $ = (id) => document.getElementById(id);

const CATEGORY_LABELS = {
  required_technical_skill: "Required Technical Skill",
  project_experience: "Project Experience",
  missing_or_weak_skill: "Missing / Weak Skill",
  practical_problem_solving: "Practical Problem-Solving",
};

const CATEGORY_ICONS = {
  required_technical_skill: "⚙️",
  project_experience: "📁",
  missing_or_weak_skill: "🔎",
  practical_problem_solving: "🧠",
};

// In-memory state: the current plan plus per-question review state.
let state = {
  plan: null,
  questions: [], // { ...question, id, reviewState: 'pending'|'approved'|'rejected' }
  filter: "all",
};

// --------------------------------------------------------------------------- //
// Health check
// --------------------------------------------------------------------------- //
async function checkHealth() {
  const pill = $("status-pill");
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const name = data.label || data.provider || "LLM";
    if (data.key_configured) {
      pill.textContent = `● ${name} · ${data.model}`;
      pill.className = "status-pill ok";
      pill.title = `Provider: ${data.provider} · model: ${data.model}`;
    } else {
      pill.textContent = `● ${name}: no key`;
      pill.className = "status-pill bad";
      pill.title = `Set ${data.key_env} in the environment before generating. Free key: ${data.signup || ""}`;
    }
  } catch {
    pill.textContent = "● Backend unreachable";
    pill.className = "status-pill bad";
  }
}

// --------------------------------------------------------------------------- //
// Generate
// --------------------------------------------------------------------------- //
async function generate() {
  const resume = $("resume").value.trim();
  const jd = $("jd").value.trim();
  const num = parseInt($("num-questions").value, 10) || 8;

  hideError();
  if (!resume || !jd) {
    showError("Please provide both a resume and a job description.");
    return;
  }

  setView("loading");
  $("generate-btn").disabled = true;

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume, job_description: jd, num_questions: num }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${res.status}).`);
    }

    const plan = await res.json();
    loadPlan(plan);
    setView("plan");
  } catch (e) {
    setView(state.plan ? "plan" : "empty");
    showError(e.message);
  } finally {
    $("generate-btn").disabled = false;
  }
}

function loadPlan(plan) {
  state.plan = plan;
  state.questions = plan.questions.map((q, i) => ({
    ...q,
    id: i + 1,
    reviewState: "pending",
  }));
  renderSummary(plan);
  renderQuestions();
  $("result-actions").hidden = false;
}

// --------------------------------------------------------------------------- //
// Rendering
// --------------------------------------------------------------------------- //
function renderSummary(plan) {
  const s = $("strengths-list");
  const g = $("gaps-list");
  s.innerHTML = "";
  g.innerHTML = "";
  (plan.candidate_strengths || []).forEach((t) => s.appendChild(li(t)));
  (plan.skills_to_validate || []).forEach((t) => g.appendChild(li(t)));
}

function renderQuestions() {
  const container = $("questions-list");
  container.innerHTML = "";

  const visible = state.questions.filter(
    (q) => state.filter === "all" || q.difficulty === state.filter
  );

  if (visible.length === 0) {
    container.innerHTML = `<p class="muted" style="text-align:center;padding:20px">No ${state.filter} questions.</p>`;
  }

  visible.forEach((q, i) => container.appendChild(renderCard(q, i)));
  updateApprovalSummary();
  updateChipCounts();
}

function updateChipCounts() {
  const counts = { all: state.questions.length, Easy: 0, Medium: 0, Hard: 0 };
  state.questions.forEach((q) => {
    if (counts[q.difficulty] !== undefined) counts[q.difficulty]++;
  });
  document.querySelectorAll("#difficulty-filter .chip").forEach((chip) => {
    const f = chip.dataset.filter;
    const label = f === "all" ? "All" : f;
    chip.innerHTML = `${label} <span class="cnt">${counts[f] ?? 0}</span>`;
  });
}

function renderCard(q, index) {
  const card = document.createElement("div");
  card.className = "qcard";
  card.dataset.state = q.reviewState;
  card.dataset.category = q.category;
  card.style.animationDelay = `${Math.min(index, 8) * 0.05}s`;

  const stateTag =
    q.reviewState === "approved"
      ? `<span class="state-tag approved">✓ Approved</span>`
      : q.reviewState === "rejected"
      ? `<span class="state-tag rejected">✕ Rejected</span>`
      : "";

  const points = (q.expected_answer_points || [])
    .map((p) => `<li>${escapeHtml(p)}</li>`)
    .join("");

  const catIcon = CATEGORY_ICONS[q.category] || "•";

  card.innerHTML = `
    <div class="qcard-top">
      <span class="qnum">${q.id}</span>
      <span class="badge ${q.difficulty}">${q.difficulty}</span>
      <span class="cat-tag">${catIcon} ${CATEGORY_LABELS[q.category] || q.category}</span>
      ${stateTag}
    </div>
    <p class="qtext" data-field="question">${escapeHtml(q.question)}</p>
    <div class="qsection">
      <div class="qsection-label">Expected Answer Points</div>
      <ul class="points-list">${points}</ul>
    </div>
    <div class="qsection">
      <div class="qsection-label">Why this question</div>
      <div class="reason">${escapeHtml(q.reason)}</div>
    </div>
    <div class="qcard-actions">
      <button class="act-btn edit">✎ Edit</button>
      <button class="act-btn approve ${q.reviewState === "approved" ? "active" : ""}">✓ Approve</button>
      <button class="act-btn reject ${q.reviewState === "rejected" ? "active" : ""}">✕ Reject</button>
    </div>
  `;

  const qtext = card.querySelector(".qtext");
  const editBtn = card.querySelector(".edit");
  editBtn.addEventListener("click", () => toggleEdit(q, qtext, editBtn));
  card.querySelector(".approve").addEventListener("click", () => setReview(q, "approved"));
  card.querySelector(".reject").addEventListener("click", () => setReview(q, "rejected"));

  return card;
}

function toggleEdit(q, el, btn) {
  const editing = el.getAttribute("contenteditable") === "true";
  if (editing) {
    q.question = el.textContent.trim();
    el.setAttribute("contenteditable", "false");
    btn.textContent = "✎ Edit";
  } else {
    el.setAttribute("contenteditable", "true");
    el.focus();
    btn.textContent = "✓ Save";
    placeCaretAtEnd(el);
  }
}

function setReview(q, newState) {
  q.reviewState = q.reviewState === newState ? "pending" : newState;
  renderQuestions();
}

function updateApprovalSummary() {
  const approved = state.questions.filter((q) => q.reviewState === "approved").length;
  const rejected = state.questions.filter((q) => q.reviewState === "rejected").length;
  $("approval-summary").textContent = `${approved} approved · ${rejected} rejected · ${state.questions.length} total`;
}

// --------------------------------------------------------------------------- //
// Export
// --------------------------------------------------------------------------- //
function approvedForExport() {
  // If nothing has been approved yet, export everything not explicitly rejected.
  const anyApproved = state.questions.some((q) => q.reviewState === "approved");
  return state.questions.filter((q) =>
    anyApproved ? q.reviewState === "approved" : q.reviewState !== "rejected"
  );
}

function buildMarkdown() {
  const plan = state.plan;
  const qs = approvedForExport();
  let md = `# Interview Plan\n\n`;
  md += `## Candidate Strengths\n`;
  (plan.candidate_strengths || []).forEach((t) => (md += `- ${t}\n`));
  md += `\n## Skills to Validate\n`;
  (plan.skills_to_validate || []).forEach((t) => (md += `- ${t}\n`));
  md += `\n## Recommended Questions\n`;
  qs.forEach((q, i) => {
    md += `\n### Question ${i + 1} — ${q.difficulty}\n`;
    md += `_${CATEGORY_LABELS[q.category] || q.category}_\n\n`;
    md += `${q.question}\n\n`;
    md += `**Expected Answer Points**\n`;
    (q.expected_answer_points || []).forEach((p) => (md += `- ${p}\n`));
    md += `\n**Reason:** ${q.reason}\n`;
  });
  return md;
}

function copyApproved() {
  navigator.clipboard.writeText(buildMarkdown()).then(() => {
    const btn = $("copy-btn");
    const original = btn.textContent;
    btn.textContent = "Copied!";
    setTimeout(() => (btn.textContent = original), 1400);
  });
}

function exportMarkdown() {
  const blob = new Blob([buildMarkdown()], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "interview-plan.md";
  a.click();
  URL.revokeObjectURL(url);
}

// --------------------------------------------------------------------------- //
// PDF upload
// --------------------------------------------------------------------------- //
async function handlePdf(file) {
  hideError();
  const btn = $("pdf-btn");
  const original = btn.textContent;
  btn.textContent = "Reading…";
  try {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/extract-pdf", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not read PDF.");
    $("resume").value = data.text;
  } catch (e) {
    showError(e.message);
  } finally {
    btn.textContent = original;
  }
}

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //
function setView(view) {
  $("empty-state").hidden = view !== "empty";
  $("loading-state").hidden = view !== "loading";
  $("plan").hidden = view !== "plan";
}

function showError(msg) {
  const box = $("error-box");
  box.textContent = msg;
  box.hidden = false;
}
function hideError() {
  $("error-box").hidden = true;
}

function li(text) {
  const el = document.createElement("li");
  el.textContent = text;
  return el;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

function placeCaretAtEnd(el) {
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
}

function loadSample() {
  $("resume").value =
    "Python, Django, PostgreSQL, REST APIs. Two years of backend development experience building CRUD APIs and relational data models for a SaaS product.";
  $("jd").value =
    "Backend Engineer. Required: Python, Django, PostgreSQL, Docker, Redis, and background/asynchronous processing using Celery. Experience scaling APIs and optimizing database queries is a plus.";
}

// --------------------------------------------------------------------------- //
// Wire up
// --------------------------------------------------------------------------- //
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  $("generate-btn").addEventListener("click", generate);
  $("sample-btn").addEventListener("click", loadSample);
  $("copy-btn").addEventListener("click", copyApproved);
  $("export-btn").addEventListener("click", exportMarkdown);

  $("pdf-btn").addEventListener("click", () => $("pdf-input").click());
  $("pdf-input").addEventListener("change", (e) => {
    if (e.target.files[0]) handlePdf(e.target.files[0]);
    e.target.value = "";
  });

  document.querySelectorAll("#difficulty-filter .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#difficulty-filter .chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.filter = chip.dataset.filter;
      renderQuestions();
    });
  });
});
