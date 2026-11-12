"use strict";

const SEVERITY_ORDER = { critical: 0, major: 1, minor: 2 };
const state = {
  mode: "diff",
  status: null,
  samples: [],
  sample: null,        // sample whose diff is currently in the textarea
  evalLoaded: false,
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON body */ }
  if (!res.ok) {
    let detail = data && data.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("\n");
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

/* ---------------- Tabs & mode ---------------- */

function showTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  if (name === "eval" && !state.evalLoaded) loadEval();
  if (name === "history") loadHistory();
}

function setMode(mode) {
  state.mode = mode;
  $$(".seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  $(".mode-diff").classList.toggle("hidden", mode !== "diff");
  $(".mode-url").classList.toggle("hidden", mode !== "url");
}

/* ---------------- Status & samples ---------------- */

async function loadStatus() {
  try {
    const s = await api("/api/status");
    state.status = s;
    $("#status").innerHTML = `
      <span class="pill">Model <code>${esc(s.model)}</code></span>
      <span class="pill"><span class="dot ${s.anthropic_configured ? "on" : "off"}"></span>Anthropic</span>
      <span class="pill"><span class="dot ${s.github_configured ? "on" : "off"}"></span>GitHub</span>`;
  } catch {
    $("#status").innerHTML = `<span class="pill"><span class="dot off"></span>API unreachable</span>`;
  }
}

async function loadSamples() {
  try {
    state.samples = await api("/api/samples");
  } catch {
    return;
  }
  const select = $("#sample");
  const groups = [
    ["Planted bug", (s) => s.label === "buggy" && !s.repo_path],
    ["Clean (should stay quiet)", (s) => s.label === "clean" && !s.repo_path],
    ["Needs repo context: planted bug", (s) => s.label === "buggy" && s.repo_path],
    ["Needs repo context: clean", (s) => s.label === "clean" && s.repo_path],
  ];
  for (const [title, match] of groups) {
    const og = document.createElement("optgroup");
    og.label = title;
    for (const s of state.samples.filter(match)) {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.expected ? `${prettyId(s.id)} · ${s.expected.bug_type}` : prettyId(s.id);
      og.appendChild(opt);
    }
    select.appendChild(og);
  }
}

function prettyId(id) {
  return id.replace(/^(ctx_)?(buggy|clean)_/, "").replace(/_/g, " ");
}

function useSample(id) {
  const sample = state.samples.find((s) => s.id === id);
  state.sample = sample || null;
  if (!sample) return;
  $("#diff").value = sample.diff;
  // Context samples come with a fixture checkout; prefill it so retrieval runs.
  $("#repoPath").value = sample.repo_path || "";
  if (sample.repo_path) $(".advanced").open = true;
}

/* ---------------- Review ---------------- */

let runTimer = null;

function setRunning(on, isUrl) {
  const btn = $("#runBtn");
  btn.disabled = on;
  clearInterval(runTimer);
  if (!on) { $("#runState").innerHTML = ""; return; }
  const steps = [
    ...(isUrl ? ["Fetching PR diff from GitHub…"] : []),
    ...($("#repoPath").value.trim() ? ["Retrieving callers, imports and tests…"] : []),
    "Asking Claude for structured findings…",
    "Validating findings against the schema…",
  ];
  let i = 0;
  const render = () => {
    $("#runState").innerHTML = `<span class="spinner"></span>${esc(steps[Math.min(i, steps.length - 1)])}`;
    i++;
  };
  render();
  runTimer = setInterval(render, 2200);
}

function showError(msg) {
  const el = $("#error");
  el.textContent = msg;
  el.classList.toggle("hidden", !msg);
}

async function runReview() {
  showError("");
  const payload = {};
  if (state.mode === "url") {
    const url = $("#prUrl").value.trim();
    if (!url) return showError("Enter a GitHub pull request URL.");
    payload.pr_url = url;
  } else {
    const diff = $("#diff").value;
    if (!diff.trim()) return showError("Paste a diff or pick a sample first.");
    payload.diff = diff;
  }
  const repo = $("#repoPath").value.trim();
  if (repo) payload.repo_path = repo;

  const expected = state.mode === "diff" && state.sample && state.sample.diff === payload.diff
    ? state.sample.expected : null;

  setRunning(true, state.mode === "url");
  try {
    const run = await api("/api/review", { method: "POST", body: JSON.stringify(payload) });
    renderResults(run, { expected });
  } catch (err) {
    showError(err.message);
  } finally {
    setRunning(false);
  }
}

function sortFindings(findings) {
  return [...findings].sort((a, b) =>
    (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9) ||
    a.file.localeCompare(b.file) || (a.line ?? 0) - (b.line ?? 0));
}

function countBy(findings, key) {
  const out = {};
  for (const f of findings) out[f[key]] = (out[f[key]] || 0) + 1;
  return out;
}

function renderResults(run, opts = {}) {
  const findings = sortFindings(run.findings || []);
  findings.forEach((f, i) => { f._id = `f${i}`; });
  const sev = countBy(findings, "severity");
  const gh = run.github_review;
  const isPr = /github\.com\/[^/]+\/[^/]+\/pull\/\d+/.test(run.source || "");

  const files = parseDiff(run.diff || "");
  const placement = placeFindings(files, findings);
  const catchInfo = opts.expected ? plantedOutcome(opts.expected, findings) : null;

  const statsHtml = `
    <div class="stats">
      ${stat("Findings", findings.length, findings.length ? severitySummary(sev) : "clean")}
      ${stat("Latency", `${run.latency_s ?? "–"}s`, "LLM call")}
      ${stat("Files in diff", files.length, `${files.reduce((n, f) => n + f.adds, 0)} added lines`)}
      ${gh ? stat("Inline-ready", gh.inline_comments.length, `${gh.summary_only.length} summary-only`) : ""}
      ${run.retrieval ? stat("Retrieved context", Object.values(run.retrieval).reduce((a, b) => a + b, 0), retrievalSummary(run.retrieval)) : ""}
      ${catchInfo ? stat("Planted bug", catchInfo.caught ? "Caught" : "Missed", `${esc(opts.expected.bug_type)} · lines ${opts.expected.lines.join(", ")}`) : ""}
    </div>`;

  const sourceHtml = isPr
    ? `<a href="${esc(run.source)}" target="_blank" rel="noopener">${esc(run.source)}</a>`
    : esc(run.source || "pasted diff");

  const listHtml = findings.length
    ? `<div class="finding-list">${findings.map(findingItem).join("")}</div>`
    : `<div class="empty-ok">No issues found in this diff.</div>`;

  const ghHtml = gh ? githubCard(gh, run, isPr) : "";

  $("#results").innerHTML = `
    <p class="source-line">Reviewed ${sourceHtml} with <code>${esc(run.model)}</code>${run.timestamp ? ` · ${esc(fmtTime(run.timestamp))}` : ""}</p>
    ${statsHtml}
    <div class="results-grid">
      <div>
        ${opts.expected ? `<p class="muted small"><span class="badge planted">planted</span> marks the hand-planted bug lines (ground truth).</p>` : ""}
        ${files.map((f) => renderFile(f, placement, opts.expected)).join("") || `<div class="card muted">Could not parse any files from this diff.</div>`}
        ${placement.orphans.length ? `<div class="card"><h2>Other findings</h2><div class="file-notes" style="padding:10px 0 0;border:0">${placement.orphans.map(noteBox).join("")}</div></div>` : ""}
      </div>
      <aside class="side">
        <div class="card">
          <div class="card-head"><h2>Findings</h2><span class="muted small">click to jump</span></div>
          ${listHtml}
        </div>
        ${ghHtml}
      </aside>
    </div>`;
  $("#results").classList.remove("hidden");

  $$(".finding-item", $("#results")).forEach((btn) =>
    btn.addEventListener("click", () => jumpTo(btn.dataset.target)));
  const postBtn = $("#postBtn");
  if (postBtn) postBtn.addEventListener("click", () => postToGitHub(run, postBtn));
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function stat(label, value, sub) {
  return `<div class="stat"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div><div class="sub">${sub}</div></div>`;
}

function severitySummary(sev) {
  return ["critical", "major", "minor"].filter((k) => sev[k]).map((k) => `${sev[k]} ${k}`).join(" · ");
}

function retrievalSummary(r) {
  return Object.entries(r).map(([k, v]) => `${v} ${k}${v === 1 ? "" : "s"}`).join(" · ") || "none found";
}

function plantedOutcome(expected, findings) {
  const tol = 3;
  const caught = findings.some((f) => sameFile(f.file, expected.file) && f.line != null &&
    expected.lines.some((l) => Math.abs(l - f.line) <= tol));
  return { caught };
}

function findingItem(f) {
  return `<button class="finding-item" data-target="${f._id}">
    <div class="meta">
      <span class="badge ${esc(f.severity)}">${esc(f.severity)}</span>
      <span class="badge cat">${esc(f.category)}</span>
      <span class="loc">${esc(f.file)}${f.line != null ? `:${f.line}` : ""}</span>
    </div>
    <p>${esc(f.issue)}</p>
  </button>`;
}

function noteBox(f) {
  return `<div class="note-box ${esc(f.severity)}" id="${f._id}">
    <div class="meta">
      <span class="badge ${esc(f.severity)}">${esc(f.severity)}</span>
      <span class="badge cat">${esc(f.category)}</span>
      ${f.line != null ? `<span class="muted small">line ${f.line}</span>` : ""}
    </div>
    <p>${esc(f.issue)}</p>
  </div>`;
}

function jumpTo(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const details = el.closest("details");
  if (details) details.open = true;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  const row = el.closest("tr")?.previousElementSibling;
  for (const target of [el, row]) {
    if (!target) continue;
    target.classList.remove("flash");
    void target.offsetWidth;
    target.classList.add("flash");
  }
}

/* ---------------- Diff parsing & rendering ---------------- */

function stripPath(p) {
  p = p.trim().split("\t")[0];
  if (p === "/dev/null") return null;
  return p.replace(/^[ab]\//, "");
}

function sameFile(a, b) {
  if (!a || !b) return false;
  return a === b || a.endsWith(`/${b}`) || b.endsWith(`/${a}`);
}

function parseDiff(text) {
  const files = [];
  let cur = null;
  let oldN = 0, newN = 0, oldLeft = 0, newLeft = 0;
  const newFile = () => { cur = { path: null, oldPath: null, rows: [], adds: 0, dels: 0 }; files.push(cur); };

  for (const raw of text.replace(/\r\n/g, "\n").split("\n")) {
    const inHunk = cur && (oldLeft > 0 || newLeft > 0);
    if (inHunk) {
      const ch = raw[0];
      if (ch === "+") { cur.rows.push({ t: "add", n: newN++, text: raw.slice(1) }); cur.adds++; newLeft--; continue; }
      if (ch === "-") { cur.rows.push({ t: "del", o: oldN++, text: raw.slice(1) }); cur.dels++; oldLeft--; continue; }
      if (ch === "\\") continue;
      if (ch === " " || raw === "") { cur.rows.push({ t: "ctx", o: oldN++, n: newN++, text: raw.slice(1) }); oldLeft--; newLeft--; continue; }
      oldLeft = newLeft = 0; // malformed hunk: fall through to header parsing
    }
    if (raw.startsWith("\\")) continue;
    if (raw.startsWith("diff --git")) { newFile(); continue; }
    if (raw.startsWith("--- ")) {
      if (!cur || cur.rows.length || cur.oldPath !== null) newFile();
      cur.oldPath = stripPath(raw.slice(4)) ?? "";
      continue;
    }
    if (raw.startsWith("+++ ")) {
      if (!cur) newFile();
      cur.path = stripPath(raw.slice(4));
      continue;
    }
    const m = raw.match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$/);
    if (m) {
      if (!cur) newFile();
      oldN = +m[1]; newN = +m[3];
      oldLeft = m[2] === undefined ? 1 : +m[2];
      newLeft = m[4] === undefined ? 1 : +m[4];
      cur.rows.push({ t: "hunk", text: raw });
      continue;
    }
    if (cur && !cur.path) {
      const g = raw.match(/^rename to (.+)$/);
      if (g) cur.path = g[1];
    }
  }
  for (const f of files) {
    if (!f.path) f.path = f.oldPath || "(unknown file)";
    if (f.oldPath === "") f.isNew = true;
  }
  return files.filter((f) => f.rows.length || f.path !== "(unknown file)");
}

function placeFindings(files, findings) {
  const byRow = new Map();     // `${fileIdx}:${line}` -> findings
  const byFile = new Map();    // fileIdx -> file-level findings
  const orphans = [];
  for (const f of findings) {
    const idx = files.findIndex((file) => sameFile(file.path, f.file));
    if (idx === -1) { orphans.push(f); continue; }
    const hasLine = f.line != null && files[idx].rows.some((r) => r.n === f.line);
    if (hasLine) {
      const key = `${idx}:${f.line}`;
      if (!byRow.has(key)) byRow.set(key, []);
      byRow.get(key).push(f);
    } else {
      if (!byFile.has(idx)) byFile.set(idx, []);
      byFile.get(idx).push(f);
    }
  }
  return { byRow, byFile, orphans, files };
}

function renderFile(file, placement, expected) {
  const idx = placement.files.indexOf(file);
  const planted = expected && sameFile(file.path, expected.file) ? new Set(expected.lines) : null;
  const fileNotes = placement.byFile.get(idx) || [];
  const count = fileNotes.length + [...placement.byRow.entries()]
    .filter(([k]) => k.startsWith(`${idx}:`)).reduce((n, [, v]) => n + v.length, 0);

  const rows = file.rows.map((r) => {
    if (r.t === "hunk") return `<tr class="hunk"><td class="num"></td><td class="num"></td><td colspan="2">${esc(r.text)}</td></tr>`;
    const cls = [r.t, planted && r.n != null && planted.has(r.n) ? "planted" : ""].join(" ");
    const sign = r.t === "add" ? "+" : r.t === "del" ? "-" : " ";
    let html = `<tr class="${cls}"><td class="num">${r.o ?? ""}</td><td class="num">${r.n ?? ""}</td><td class="sign">${sign}</td><td>${esc(r.text) || " "}</td></tr>`;
    if (r.n != null) {
      const notes = placement.byRow.get(`${idx}:${r.n}`);
      if (notes) html += `<tr class="note"><td colspan="4">${notes.map(noteBox).join("")}</td></tr>`;
    }
    return html;
  }).join("");

  // In large PRs, start files without findings collapsed so the eye lands on issues.
  const open = count > 0 || placement.files.length <= 3 || (planted && planted.size);
  return `<details class="diff-file"${open ? " open" : ""}>
    <summary class="diff-file-head">
      <span><span class="chev">›</span>${esc(file.path)}${file.isNew ? ' <span class="muted">(new)</span>' : ""}</span>
      <span class="muted">+${file.adds} −${file.dels}${count ? ` · ${count} finding${count === 1 ? "" : "s"}` : ""}</span>
    </summary>
    ${fileNotes.length ? `<div class="file-notes">${fileNotes.map(noteBox).join("")}</div>` : ""}
    <div class="diff-scroll"><table class="diff">${rows}</table></div>
  </details>`;
}

/* ---------------- GitHub posting ---------------- */

function githubCard(gh, run, isPr) {
  const canPost = isPr && state.status?.github_configured;
  const reason = !isPr ? "Review a GitHub PR URL to enable posting." :
    !state.status?.github_configured ? "Set GITHUB_TOKEN to enable posting." : "";
  return `<div class="card">
    <div class="card-head"><h2>GitHub review preview</h2></div>
    <div class="gh-row"><span>Inline comments on changed lines</span><b>${gh.inline_comments.length}</b></div>
    <div class="gh-row"><span>Demoted to summary (off-diff lines)</span><b>${gh.summary_only.length}</b></div>
    <div class="gh-body">${esc(gh.body)}</div>
    <div class="gh-actions">
      <button id="postBtn" class="secondary" ${canPost ? "" : "disabled"}>Post to GitHub</button>
      <span id="postState" class="muted small">${esc(reason)}</span>
    </div>
  </div>`;
}

async function postToGitHub(run, btn) {
  const gh = run.github_review;
  const ok = window.confirm(
    `Post a review with ${gh.inline_comments.length} inline comment(s) to\n${run.source}?\n\nThis is visible to everyone with access to the PR.`);
  if (!ok) return;
  btn.disabled = true;
  $("#postState").textContent = "Posting…";
  try {
    const res = await api("/api/post", {
      method: "POST",
      body: JSON.stringify({ pr_url: run.source, body: gh.body, inline_comments: gh.inline_comments }),
    });
    $("#postState").outerHTML = `<span class="posted">Posted. <a href="${esc(res.url)}" target="_blank" rel="noopener">Open PR ↗</a></span>`;
  } catch (err) {
    btn.disabled = false;
    $("#postState").textContent = err.message;
  }
}

/* ---------------- Evaluation ---------------- */

async function loadEval() {
  const body = $("#evalBody");
  let r;
  try {
    r = await api("/api/eval");
  } catch (err) {
    body.innerHTML = `<div class="card muted">${esc(err.message)}</div>`;
    return;
  }
  let cmp = null;
  try { cmp = await api("/api/eval/comparison"); } catch { /* optional */ }
  state.evalLoaded = true;

  const m = r.metrics;
  const sd = r.metrics_std || {};
  const trials = r.trials || 1;
  const pct = (x) => `${Math.round(x * 100)}%`;
  const num = (x) => (Number.isInteger(x) ? String(x) : x.toFixed(1));
  const spread = (k) => (trials > 1 && sd[k] != null ? ` <span class="pm">± ${Math.round(sd[k] * 100)}</span>` : "");
  const buggy = r.cases.filter((c) => c.label === "buggy").length;
  const clean = r.cases.length - buggy;
  const far = m.false_alarm_rate ?? (m.fp + m.tn ? m.fp / (m.fp + m.tn) : 0);

  const bugTypes = Object.entries(r.recall_by_bug_type || {}).map(([type, v]) => `
    <div class="bar-row"><span>${esc(type)}</span>
      <div class="bar"><span style="width:${v.total ? (v.caught / v.total) * 100 : 0}%"></span></div>
      <span class="muted">${v.caught}/${v.total}</span></div>`).join("");

  const caseRows = (r.cases || []).map((c, i) => `
    <tr class="clickable" data-case="${i}">
      <td><b>${esc(prettyId(c.case_id))}</b></td>
      <td>${esc(c.label)}</td>
      <td>${esc(c.bug_type || "—")}</td>
      <td><span class="outcome ${esc(c.outcome)}">${esc(outcomeLabel(c.outcome))}</span></td>
      ${trials > 1 ? `<td><span class="trial-dots">${(c.outcomes || []).map((o) => `<span class="tdot ${esc(o)}" title="${esc(outcomeLabel(o))}"></span>`).join("")}</span></td>` : ""}
      <td>${c.matched_line ?? "—"}</td>
      <td>${num(c.num_findings)}</td>
    </tr>
    <tr class="hidden" data-detail="${i}"><td colspan="${trials > 1 ? 7 : 6}">
      ${c.findings?.length ? `<ul class="case-findings">${c.findings.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : `<span class="muted small">No findings.</span>`}
      ${state.samples.some((s) => s.id === c.case_id) ? `<button class="secondary" data-open="${esc(c.case_id)}" style="margin-top:8px">Re-run this case live</button>` : ""}
    </td></tr>`).join("");

  body.innerHTML = `
    <p class="source-line">Generated ${esc(fmtTime(r.generated_at))} · model <code>${esc(r.model)}</code>${r.prompt ? ` · prompt <code>${esc(r.prompt)}</code>` : ""} · retrieval ${r.retrieval ? "on" : "off"}${r.min_severity ? ` · severity floor ${esc(r.min_severity)}` : ""} · ±${r.tolerance}-line match${trials > 1 ? ` · <b>${trials} trials</b>, mean ± std` : ""} · regenerate with <code>python -m evals.run</code></p>
    <div class="metric-grid">
      <div class="metric"><div class="label">Recall</div><div class="value">${pct(m.recall)}${spread("recall")}</div><div class="sub">${num(m.tp)} of ${buggy} planted bugs caught</div></div>
      <div class="metric"><div class="label">Precision</div><div class="value">${pct(m.precision)}${spread("precision")}</div><div class="sub">${num(m.tp)} of ${num(m.tp + m.fp)} flagged cases were real bugs</div></div>
      <div class="metric"><div class="label">F1</div><div class="value">${m.f1.toFixed(2)}${trials > 1 && sd.f1 != null ? ` <span class="pm">± ${sd.f1.toFixed(2)}</span>` : ""}</div><div class="sub">harmonic mean</div></div>
      <div class="metric"><div class="label">False-alarm rate</div><div class="value">${pct(far)}${spread("false_alarm_rate")}</div><div class="sub">${num(m.fp)} of ${clean} clean cases flagged</div></div>
      <div class="metric"><div class="label">Dataset</div><div class="value">${r.cases.length}</div><div class="sub">${buggy} planted-bug · ${clean} clean</div></div>
    </div>
    ${cmp ? comparisonCard(cmp) : ""}
    <div class="eval-grid">
      <div class="card">
        <div class="card-head"><h2>Confusion matrix</h2><span class="muted small">per case${trials > 1 ? ", mean of trials" : ""}</span></div>
        <div class="confusion">
          <span></span><span class="h">Flagged</span><span class="h">Silent</span>
          <span class="h">Planted bug</span>
          <div class="cell good"><b>${num(m.tp)}</b>true positive</div>
          <div class="cell ${m.fn ? "bad" : "good"}"><b>${num(m.fn)}</b>missed</div>
          <span class="h">Clean</span>
          <div class="cell ${m.fp ? "bad" : "good"}"><b>${num(m.fp)}</b>false alarm</div>
          <div class="cell good"><b>${num(m.tn)}</b>correctly quiet</div>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Recall by bug type</h2>${trials > 1 ? `<span class="muted small">summed over trials</span>` : ""}</div>
        ${bugTypes || '<p class="muted">No buggy cases.</p>'}
      </div>
    </div>
    <div class="card">
      <div class="card-head"><h2>Per-case results</h2><span class="muted small">click a row for the model's findings</span></div>
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>Case</th><th>Label</th><th>Bug type</th><th>Outcome</th>${trials > 1 ? "<th>Trials</th>" : ""}<th>Match line</th><th>Findings</th></tr></thead>
        <tbody>${caseRows}</tbody>
      </table></div>
    </div>`;

  $$("tr[data-case]", body).forEach((tr) => tr.addEventListener("click", () =>
    $(`tr[data-detail="${tr.dataset.case}"]`, body).classList.toggle("hidden")));
  $$("button[data-open]", body).forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    openSample(b.dataset.open, true);
  }));
}

function comparisonCard(cmp) {
  // [scope, metric, header, higherIsBetter]
  const cols = [
    ["overall", "precision", "Precision", true],
    ["overall", "recall", "Recall", true],
    ["overall", "f1", "F1", true],
    ["overall", "false_alarm_rate", "False alarms", false],
    ["context", "recall", "Context recall", true],
    ["context", "false_alarm_rate", "Context false alarms", false],
  ];
  const best = cols.map(([scope, key, , higher]) => {
    const vals = cmp.configs.map((c) => c[scope]?.metrics?.[key]).filter((v) => v != null);
    return vals.length ? (higher ? Math.max(...vals) : Math.min(...vals)) : null;
  });
  const cell = (row, [scope, key], i) => {
    const data = row[scope];
    if (!data) return "<td>—</td>";
    const v = data.metrics[key];
    const s = data.metrics_std?.[key];
    return `<td class="${v === best[i] ? "best" : ""}">${v.toFixed(2)}${cmp.trials > 1 && s != null ? ` <span class="pm">±${s.toFixed(2)}</span>` : ""}</td>`;
  };
  return `<div class="card">
    <div class="card-head"><h2>A/B: prompt, retrieval and severity floor</h2>
      <span class="muted small">${cmp.trials} trial${cmp.trials === 1 ? "" : "s"} per config · ${cmp.cases} cases · context subset ${cmp.context_cases} · <code>python -m evals.compare</code></span></div>
    <div class="tbl-wrap"><table class="tbl cmp">
      <thead><tr><th>Config</th><th>Prompt</th><th>Retrieval</th><th>Floor</th>${cols.map((c) => `<th>${c[2]}</th>`).join("")}</tr></thead>
      <tbody>${cmp.configs.map((row) => `<tr>
        <td><b>${esc(row.name)}</b></td><td>${esc(row.prompt)}</td><td>${row.retrieval ? "on" : "off"}</td><td>${esc(row.min_severity)}</td>
        ${cols.map((c, i) => cell(row, c, i)).join("")}</tr>`).join("")}</tbody>
    </table></div>
    <p class="muted small" style="margin:10px 0 0">Context columns cover only cases whose bug (or safety) is visible solely in callers elsewhere in the fixture repo, which is where structural retrieval can help. Best value per column is highlighted.</p>
  </div>`;
}

function outcomeLabel(o) {
  return { TP: "caught", FN: "missed", FP: "false alarm", TN: "quiet" }[o] || o;
}

function openSample(id, run = false) {
  setMode("diff");
  $("#sample").value = id;
  useSample(id);
  showTab("review");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (run) runReview();
}

/* ---------------- History ---------------- */

async function loadHistory() {
  const body = $("#historyBody");
  let runs;
  try {
    runs = await api("/api/runs");
  } catch (err) {
    body.innerHTML = `<p class="muted">${esc(err.message)}</p>`;
    return;
  }
  if (!runs.length) {
    body.innerHTML = `<p class="muted">No runs yet. Review something on the Review tab.</p>`;
    return;
  }
  body.innerHTML = `<div class="tbl-wrap"><table class="tbl">
    <thead><tr><th>When</th><th>Source</th><th>Findings</th><th>Latency</th><th>Model</th></tr></thead>
    <tbody>${runs.map((r) => `
      <tr class="clickable" data-run="${r.id}">
        <td style="white-space:nowrap">${esc(fmtTime(r.timestamp))}</td>
        <td style="word-break:break-all">${esc(r.source)}</td>
        <td><span class="sev-dots">${["critical", "major", "minor"].filter((k) => r.severities[k]).map((k) => `<span class="badge ${k}">${r.severities[k]} ${k}</span>`).join("") || '<span class="muted">none</span>'}</span></td>
        <td>${r.latency_s ?? "—"}s</td>
        <td><code>${esc(r.model)}</code></td>
      </tr>`).join("")}</tbody></table></div>`;
  $$("tr[data-run]", body).forEach((tr) => tr.addEventListener("click", async () => {
    try {
      const run = await api(`/api/runs/${tr.dataset.run}`);
      showTab("review");
      showError("");
      renderResults(run);
    } catch (err) {
      showError(err.message);
    }
  }));
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/* ---------------- Wire up ---------------- */

$$(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));
$$(".seg-btn").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
$("#sample").addEventListener("change", (e) => useSample(e.target.value));
$("#runBtn").addEventListener("click", runReview);
$("#diff").addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") runReview();
});
$("#prUrl").addEventListener("keydown", (e) => { if (e.key === "Enter") runReview(); });

loadStatus();
loadSamples();
