/* GoOrGrow frontend - plain JavaScript, talks to the FastAPI backend on the same address. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const money = (n, cur) => (n ? `${cur || ""} ${Math.round(n).toLocaleString()}`.trim() : "");
const splitList = (s) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

const state = { sid: null, files: [], added: [], fields: new Set(), workmode: "any", currency: "GBP", readiness: null, matches: null };
const LEVEL = { used_at_work: "used at work", used_in_project: "used in a project", mentioned: "listed" };
const STEPS = [
  "Reading your confirmed profile",
  "Collecting job listings",
  "Pulling out what each job asks for",
  "Filtering by field, place, level and salary",
  "Comparing your skills with every requirement",
  "Ranking your best matches",
];

async function api(method, path, body, form = false) {
  const opts = { method, headers: {} };
  if (form) opts.body = body;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((x) => x.msg).join("; ") : d || `Request failed (${res.status})`);
  }
  return data;
}

function busy(btn, on, label) {
  if (on) { btn.dataset.label = btn.textContent; btn.textContent = label; btn.disabled = true; }
  else { btn.textContent = btn.dataset.label || btn.textContent; btn.disabled = false; }
}

const STEP_NAMES = { 1: "Your documents", 2: "What you want", 3: "Finding your matches", 4: "Go or grow?" };
let currentView = null;

// Moves to another screen. Motion.transition plays the curtain (new step) or a slide (same step).
function show(id) {
  const v = $("#" + id), from = currentView && currentView !== v ? currentView : null;
  const step = +v.dataset.step, newStep = !from || +from.dataset.step !== step;
  $$(".view").forEach((x) => { if (x !== v && x !== from) x.hidden = true; });
  currentView = v;
  $$(".steps li").forEach((li) => {
    const n = +li.dataset.step;
    li.classList.toggle("on", n === step);
    li.classList.toggle("done", n < step);
  });
  Motion.progress && Motion.progress(step);
  const label = id === "v-results" ? null : STEP_NAMES[step];
  return Motion.transition(from, v, { label, newStep }).then(() => {
    const h = v.querySelector("h1, h2");
    if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); }
    if (id === "v-choice" && Motion.choiceIntro) Motion.choiceIntro();
  });
}

$$("[data-back]").forEach((b) => b.addEventListener("click", () => {
  if (b.dataset.back === "v-choice") { $("#split").className = "split"; Motion.choiceReset && Motion.choiceReset(); }
  show(b.dataset.back);
}));

/* ================= 1. upload ================= */
const drop = $("#drop"), fileInput = $("#files");
function setFiles(list) {
  for (const f of list) if (!state.files.some((x) => x.name === f.name)) state.files.push(f);
  $("#file-list").innerHTML = state.files.map((f) => `<li>${esc(f.name)}</li>`).join("");
  Motion.fileAdded && Motion.fileAdded($("#file-list li:last-child"));
}
fileInput.addEventListener("change", () => setFiles(fileInput.files));
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => setFiles(e.dataTransfer.files));

$("#btn-read").addEventListener("click", async (e) => {
  const btn = e.currentTarget, err = $("#err-upload");
  err.textContent = "";
  const links = $("#links").value.trim();
  if (!state.files.length && !links) { err.textContent = "Add your resume or at least one link first."; return; }
  busy(btn, true, "Reading...");
  try {
    const fd = new FormData();
    state.files.forEach((f) => fd.append("files", f));
    if (links) fd.append("links", links);
    const up = await api("POST", "/upload", fd, true);
    state.sid = up.session_id;
    const problems = up.sources.filter((s) => !s.ok || s.warnings.length);
    if (!up.sources.some((s) => s.ok)) throw new Error(problems.flatMap((s) => s.warnings).join(" ") || "We couldn't read any text.");
    const grad = +$("#grad").value || null;
    const profile = await api("POST", `/profile/${state.sid}/build`, grad ? { graduation_year: grad } : {});
    renderProfile(profile, problems);
    show("v-profile").then(() => Motion.stagger && Motion.stagger($$("#skills li"), { stagger: 0.03 }));
  } catch (ex) { err.textContent = ex.message; }
  busy(btn, false);
});

/* ================= 1b. profile ================= */
function renderProfile(p, uploadProblems = []) {
  const n = p.skills.length;
  $("#profile-lede").textContent =
    `${p.name ? p.name + ", we" : "We"} found ${n} skill${n === 1 ? "" : "s"}` +
    (p.graduation_year ? `, and a graduation year of ${p.graduation_year}.` : ".") +
    " Check them before we compare you with jobs.";
  const warns = [...uploadProblems.flatMap((s) => s.warnings.map((w) => `${s.source}: ${w}`)),
    ...(p.warnings || []).filter((w) => !w.startsWith("AI parsing not used"))];
  $("#profile-warn").hidden = !warns.length;
  $("#profile-warn").innerHTML = warns.map(esc).join("<br>");

  state.added = [];
  $("#skills").innerHTML = p.skills.map((s, i) => `
    <li class="skill ${s.verified ? "" : "off"}">
      <input type="checkbox" id="sk${i}" data-name="${esc(s.name)}" ${s.verified ? "checked" : ""}>
      <label for="sk${i}" style="font-weight:400;margin:0;cursor:pointer">
        <b>${esc(s.name)}</b>
        <q>${esc(s.evidence || "")}</q>
        ${s.verified ? "" : '<span class="hint">Not found in your documents. Tick it only if it\'s true.</span>'}
      </label>
      <span class="lvl">${LEVEL[s.level_hint] || ""}</span>
    </li>`).join("");
  $$("#skills input").forEach((cb) => cb.addEventListener("change", () => cb.closest(".skill").classList.toggle("off", !cb.checked)));

  const sec = (t, items, f) => items?.length ? `<h4>${t}</h4><ul>${items.map((x) => `<li>${esc(f(x))}</li>`).join("")}</ul>` : "";
  $("#profile-detail").innerHTML =
    sec("Education", p.education, (x) => x.evidence || x.summary || x.degree) +
    sec("Experience", p.experience, (x) => x.evidence || x.summary) +
    sec("Projects", p.projects, (x) => x.evidence || x.description || x.summary) +
    sec("Certifications", p.certifications, (x) => x.name || x.evidence) || "<p class='hint'>Nothing else found.</p>";
}

function addSkill() {
  const inp = $("#add-skill"), name = inp.value.trim();
  if (!name) return;
  state.added.push({ name, level_hint: "mentioned" });
  const li = document.createElement("li");
  li.className = "skill";
  li.innerHTML = `<input type="checkbox" checked disabled><span><b>${esc(name)}</b><q>Added by you</q></span><span class="lvl">added</span>`;
  $("#skills").appendChild(li);
  inp.value = "";
}
$("#btn-add-skill").addEventListener("click", addSkill);
$("#add-skill").addEventListener("keydown", (e) => { if (e.key === "Enter") addSkill(); });

$("#btn-confirm").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  $("#err-profile").textContent = "";
  busy(btn, true, "Saving...");
  try {
    const keep = $$("#skills input[data-name]").filter((c) => c.checked).map((c) => c.dataset.name);
    const grad = +$("#grad").value || null;
    await api("PUT", `/profile/${state.sid}/confirm`, { keep_skills: keep, add_skills: state.added, ...(grad ? { graduation_year: grad } : {}) });
    const sug = await api("GET", `/preferences/${state.sid}/suggestions`);
    renderPrefs(sug);
    show("v-prefs").then(() => Motion.stagger && Motion.stagger($$("#field-chips .chip"), { stagger: 0.025 }));
  } catch (ex) { $("#err-profile").textContent = ex.message; }
  busy(btn, false);
});

/* ================= 2. preferences ================= */
let countryCurrency = {};
function renderPrefs(s) {
  state.suggested = s.suggested_job_fields;
  state.fields = new Set(s.suggested_job_fields.slice(0, 2).map((f) => f.role));
  const chips = [
    ...s.suggested_job_fields.map((f) => ({ name: f.role, pct: f.match_percent })),
    ...s.all_job_fields.filter((r) => !s.suggested_job_fields.some((f) => f.role === r)).map((r) => ({ name: r })),
  ];
  drawFieldChips(chips);

  const cur = { gb: "GBP", in: "INR", us: "USD", ca: "CAD", au: "AUD", de: "EUR", fr: "EUR", nl: "EUR", ie: "EUR", sg: "SGD", nz: "NZD", za: "ZAR" };
  countryCurrency = cur;
  $("#country").innerHTML = Object.entries(s.countries).map(([k, v]) => `<option value="${k}" ${k === s.suggested_country ? "selected" : ""}>${esc(v)}</option>`).join("");
  setCurrency();
  if (!$("#cities").value) $("#cities").value = s.detected_locations.slice(0, 1).join(", ");
}
function drawFieldChips(chips) {
  state.fieldChips = chips;
  $("#field-chips").innerHTML = chips.map((c) =>
    `<button type="button" class="chip" aria-pressed="${state.fields.has(c.name)}" data-name="${esc(c.name)}">${esc(c.name)}${c.pct ? `<small>${c.pct}% fit</small>` : ""}</button>`).join("");
  $$("#field-chips .chip").forEach((b) => b.addEventListener("click", () => {
    const n = b.dataset.name;
    if (state.fields.has(n)) state.fields.delete(n);
    else if (state.fields.size < 5) state.fields.add(n);
    b.setAttribute("aria-pressed", state.fields.has(n));
    Motion.pop && Motion.pop(b);
    updateExploreHint();
  }));
  updateExploreHint();
}
// Tells the user which extra roles "Also show other roles that fit my skills" will add.
function updateExploreHint() {
  const extra = (state.suggested || []).filter((r) => !state.fields.has(r.role) && r.match_percent >= 30).slice(0, 2).map((r) => r.role);
  $("#explore-hint").textContent = extra.length ? `We'll add: ${extra.join(" and ")}` : "";
}
$("#explore").addEventListener("change", (e) => Motion.pop && Motion.pop(e.target.nextElementSibling));

$("#btn-field-add").addEventListener("click", () => {
  const n = $("#field-custom").value.trim();
  if (!n || state.fields.size >= 5) return;
  state.fields.add(n);
  drawFieldChips([{ name: n }, ...state.fieldChips.filter((c) => c.name !== n)]);
  $("#field-custom").value = "";
});
function setCurrency() {
  state.currency = countryCurrency[$("#country").value] || "";
  $("#cur1").textContent = $("#cur2").textContent = `${state.currency} a year`;
}
$("#country").addEventListener("change", setCurrency);
$$("#workmode button").forEach((b) => b.addEventListener("click", () => {
  $$("#workmode button").forEach((x) => x.setAttribute("aria-checked", x === b));
  state.workmode = b.dataset.v;
}));

$("#btn-match").addEventListener("click", async () => {
  const err = $("#err-prefs");
  err.textContent = "";
  if (!state.fields.size) { err.textContent = "Pick at least one job field."; return; }
  const body = {
    job_fields: [...state.fields],
    country: $("#country").value,
    locations: splitList($("#cities").value).slice(0, 5),
    work_mode: state.workmode,
    target_salary: +$("#sal-target").value || null,
    min_salary: +$("#sal-min").value || null,
    preferred_companies: splitList($("#co-like").value),
    avoid_companies: splitList($("#co-avoid").value),
    explore_related: $("#explore").checked,
  };
  try {
    await api("PUT", `/preferences/${state.sid}`, body);
  } catch (ex) { err.textContent = ex.message; return; }
  runAnalysis();
});

/* ================= loading ================= */
async function runAnalysis() {
  show("v-loading");
  const list = $("#scan-steps");
  list.innerHTML = STEPS.map((s) => `<li>${esc(s)}</li>`).join("");
  const items = $$("li", list);
  const work = (async () => {
    const m = await api("POST", `/match/${state.sid}`, {});
    const r = m.jobs.length ? await api("POST", `/readiness/${state.sid}`) : null;
    return { m, r };
  })();
  let result, failed;
  work.then((x) => (result = x)).catch((e) => (failed = e));
  // Walk through the real steps; the last one waits for the server to finish.
  await sleep(Motion.enabled ? 1300 : 0); // let the curtain finish first
  for (let i = 0; i < items.length; i++) {
    items[i].classList.add("now");
    await (Motion.enabled ? Motion.scanStep() : sleep(650));
    while (i === items.length - 1 && !result && !failed) await sleep(150);
    items[i].classList.remove("now");
    items[i].classList.add("done");
  }
  await sleep(300);
  if (failed) { show("v-prefs"); $("#err-prefs").textContent = failed.message; return; }
  if (!result.m.jobs.length) {
    show("v-prefs");
    $("#err-prefs").textContent = result.m.warnings.at(-1) || "No jobs matched. Try widening your choices.";
    return;
  }
  state.matches = result.m; state.readiness = result.r;
  state.fieldFilter = "all";
  renderResults();
  show("v-results").then(() => Motion.results && Motion.results());
}

/* ================= 3. results ================= */
function renderResults() {
  const m = state.matches, r = state.readiness, s = r.summary;
  $("#res-title").textContent = s.jobs_ready_now
    ? `You're ready for ${s.jobs_ready_now} of these jobs now`
    : "A few skills stand between you and these jobs";
  // The title already says how many jobs are ready, so the lede gives the rest of the message.
  $("#res-lede").textContent = s.message.replace(/^You're ready to apply to \d+ job\(s\) now(?: and could stretch for (\d+) more)?\. ?/,
    (_, n) => (n ? `You could also stretch for ${n} more. ` : ""));
  const notes = [...(m.warnings || [])];
  $("#res-notes").textContent = notes.join(" ");

  const flagList = (arr, el, fmt) => {
    $(el).innerHTML = arr.length ? arr.map(fmt).join("") : `<li class="empty">Nothing here</li>`;
  };
  flagList(r.flags.green.slice(0, 8), "#fl-green", (f) => `<li>${esc(f.skill)}<span>wanted by ${f.required_in + f.nice_in} of ${f.out_of_jobs} jobs</span></li>`);
  flagList(r.flags.white.filter((f) => f.code !== "not_in_demand").slice(0, 8), "#fl-white",
    (f) => `<li>${esc(f.skill)}<span>${f.code === "weak_evidence" ? "listed, but not shown in a project or job" : "nice to have"}</span></li>`);
  flagList(r.flags.red.slice(0, 8), "#fl-red", (f) => `<li>${esc(f.skill)}<span>required by ${f.required_in} of ${f.out_of_jobs} jobs</span></li>`);
  $("#salary").textContent = r.salary_check.message;

  // Adzuna's terms ask for "Jobs by Adzuna" wherever their listings are shown.
  $("#credit").hidden = m.source !== "adzuna";
  const counts = {};
  m.jobs.forEach((j) => (counts[j.field] = (counts[j.field] || 0) + 1));
  const fields = Object.keys(counts);
  $("#field-tabs").hidden = fields.length < 2;
  $("#field-tabs").innerHTML = [["all", "All fields", m.jobs.length], ...fields.map((f) => [f, f, counts[f]])]
    .map(([k, name, n]) => `<button class="tab" role="tab" data-f="${esc(k)}" aria-selected="${(state.fieldFilter || "all") === k}">${esc(name)}<small>${n}</small></button>`).join("");
  $$("#field-tabs .tab").forEach((t) => t.addEventListener("click", () => {
    state.fieldFilter = t.dataset.f;
    $$("#field-tabs .tab").forEach((x) => x.setAttribute("aria-selected", x === t));
    $$("#jobs .job").forEach((row) => (row.hidden = state.fieldFilter !== "all" && row.dataset.field !== state.fieldFilter));
    Motion.stagger && Motion.stagger($$("#jobs .job:not([hidden])"), { stagger: 0.05, ease: "power3.out" });
  }));
  const rj = Object.fromEntries(r.jobs.map((j) => [j.job_id, j]));
  const recText = { go: "Ready to apply", go_stretch: "Worth a stretch", grow: "Grow first" };
  $("#jobs").innerHTML = m.jobs.map((j) => {
    const rd = rj[j.job_id] || {};
    const pay = j.salary_min || j.salary_max ? `${money(j.salary_min, j.currency)}${j.salary_max && j.salary_max !== j.salary_min ? "–" + Math.round(j.salary_max).toLocaleString() : ""}` : "Salary not listed";
    return `<li class="job" data-field="${esc(j.field || "")}">
      <div>
        ${j.field ? `<span class="field-badge ${j.field_is_suggested ? "sugg" : ""}">${esc(j.field)}${j.field_is_suggested ? " · fits your skills" : ""}</span>` : ""}
        ${j.outside_filters ? `<span class="outside">${esc(j.outside_filters)}</span>` : ""}
        <h4>${esc(j.title)}</h4>
        <p class="meta">${esc(j.company || "")}, ${esc(j.location || "")} (${esc(j.work_mode)}). ${esc(pay)}</p>
        <ul class="reasons">${j.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
        ${j.url ? `<p><a href="${esc(j.url)}" target="_blank" rel="noopener">See the job ad</a></p>` : `<p class="hint">${esc(j.source || "")}</p>`}
      </div>
      <div class="meter">
        <span class="score-num" data-to="${j.match_score}">${Motion.enabled ? 0 : j.match_score}</span>/100 match
        <div class="bar"><i style="width:${Motion.enabled ? 0 : j.match_score}%"></i></div>
        <span class="fit ${j.fit}">${{ safe: "Safe", stretch: "Stretch", reach: "Reach" }[j.fit]}</span>
        <p class="rec">${recText[rd.recommendation] || ""}${rd.readiness_percent != null ? `, ${rd.readiness_percent}% ready` : ""}</p>
      </div>
    </li>`;
  }).join("");
}

$("#btn-to-choice").addEventListener("click", () => {
  const s = state.readiness.summary;
  const split = $("#split");
  split.className = "split";
  $$(".half .sugg").forEach((x) => (x.hidden = true));
  $(`#pick-${s.suggested_choice} .sugg`).hidden = false;
  $("#go-count").textContent = `${s.jobs_ready_now} job${s.jobs_ready_now === 1 ? "" : "s"} ready now, ${s.jobs_stretch} worth a stretch`;
  $("#grow-count").textContent = `${s.counts.red} missing skill${s.counts.red === 1 ? "" : "s"} to work on`;
  // Restart the sprout animation each time the screen opens.
  if (!Motion.enabled) { const sp = $(".sprout"); sp.replaceWith(sp.cloneNode(true)); }
  Motion.choiceReset && Motion.choiceReset();
  show("v-choice");
});

/* ================= 4. go / grow ================= */
async function choose(choice) {
  const split = $("#split");
  if (split.classList.contains("chose-go") || split.classList.contains("chose-grow") || split.classList.contains("chosen")) return;
  const req = api("POST", `/decision/${state.sid}`, { choice });
  if (Motion.enabled) { split.classList.add("chosen"); await Motion.choose(choice); }
  else { split.classList.add("chose-" + choice); await sleep(matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 950); }
  try {
    const d = await req;
    if (choice === "go") { renderGoOptions(d.options); show("v-go").then(() => Motion.stagger && Motion.stagger($$("#go-options li"), { stagger: 0.05 })); }
    else { renderPlan(d.plan); show("v-grow").then(() => Motion.stagger && Motion.stagger($$("#plan > li"), { stagger: 0.08, ease: "power3.out" })); }
  } catch (ex) { split.className = "split"; alert(ex.message); }
}
$("#pick-go").addEventListener("click", () => choose("go"));
$("#pick-grow").addEventListener("click", () => choose("grow"));

/* ---- GO ---- */
function renderGoOptions(opts) {
  $("#apps").innerHTML = "";
  const recText = { go: "Ready", go_stretch: "Stretch", grow: "Grow first" };
  $("#go-options").innerHTML = opts.map((o, i) => `
    <li><label>
      <input type="checkbox" value="${esc(o.job_id)}" ${o.recommendation === "go" && i < 3 ? "checked" : ""}>
      <span><b>${esc(o.title)}</b><span class="m">${esc(o.company || "")}, ${esc(o.location || "")}</span></span>
      <span class="rp">${recText[o.recommendation]}, ${o.readiness_percent}%</span>
    </label></li>`).join("");
  const upd = () => ($("#btn-prepare").disabled = !$$("#go-options input:checked").length);
  $$("#go-options input").forEach((c) => c.addEventListener("change", upd));
  upd();
}

$("#btn-prepare").addEventListener("click", async (e) => {
  const btn = e.currentTarget, ids = $$("#go-options input:checked").map((c) => c.value);
  $("#err-go").textContent = "";
  busy(btn, true, "Writing...");
  try {
    const d = await api("POST", `/apply/${state.sid}`, { job_ids: ids });
    $("#apps").innerHTML = d.applications.map(renderApp).join("");
    Motion.stagger && Motion.stagger($$("#apps .app"), { stagger: 0.12, ease: "power3.out" });
    $$(".btn-approve").forEach((b) => b.addEventListener("click", approve));
    $$(".btn-preview").forEach((b) => b.addEventListener("click", () => toggleDoc(b.closest(".app"))));
    $("#apps .app")?.scrollIntoView({ behavior: "smooth" });
  } catch (ex) { $("#err-go").textContent = ex.message; }
  busy(btn, false);
});

function groupBullets(bullets, ev) {
  let html = "", cur;
  bullets.forEach((b, i) => {
    if (i === 0 || b.group !== cur) {
      if (i) html += "</ul>";
      html += (b.group ? `<p class="grp">${esc(b.group)}</p>` : "") + `<ul class="bullets">`;
      cur = b.group;
    }
    html += `<li>${esc(b.text)}<br><span class="ev">From your documents: “${esc(b.evidence_ids.map((id) => ev[id]).filter(Boolean).join(" / "))}”</span></li>`;
  });
  return html + (bullets.length ? "</ul>" : "<p class='hint'>No resume points could be matched to this job.</p>");
}

function renderApp(a) {
  const ev = Object.fromEntries(a.evidence_trail.map((e) => [e.id, e.text]));
  return `<article class="app" data-job="${esc(a.job_id)}">
    <h3>${esc(a.title)}</h3>
    <p class="hint">${esc(a.company || "")}${a.readiness_percent != null ? `, you're ${a.readiness_percent}% ready` : ""}</p>

    <h4>Summary for the top of your resume</h4>
    <textarea class="ed-summary" style="min-height:130px">${esc(a.summary || "")}</textarea>

    <h4>Resume points, most relevant first</h4>
    ${groupBullets(a.resume_bullets, ev)}

    <h4>Cover note</h4>
    <textarea class="ed-cover">${esc(a.cover_note)}</textarea>

    ${a.portfolio_highlights.length ? `<h4>Show these projects first</h4><ul class="bullets">${a.portfolio_highlights.map((p) =>
      `<li><b>${esc(p.title)}</b>: ${esc(p.why_relevant)}<br><span class="ev">${esc(p.tip || "")}</span></li>`).join("")}</ul>` : ""}

    <h4>Words from the ad you can use</h4>
    <div class="kw">${a.keywords_to_use.map((k) => `<span>${esc(k)}</span>`).join("") || "<span>None found</span>"}</div>
    ${a.do_not_claim.length ? `<h4>Don't claim these, you don't have them yet</h4><div class="kw no">${a.do_not_claim.map((k) => `<span>${esc(k)}</span>`).join("")}</div>` : ""}

    ${a.blocked_items.length ? `<h4>Lines we removed</h4><ul class="blocked">${a.blocked_items.map((b) =>
      `<li>“${esc(b.text)}”: ${esc(b.reasons.join("; "))}</li>`).join("")}</ul>` : ""}

    <h4>Before you apply</h4>
    <ul class="checklist">${a.review_checklist.map((c, i) => `<li><label><input type="checkbox" class="ck"> ${esc(c)}</label></li>`).join("")}</ul>

    <div class="actions">
      <button class="btn ghost btn-preview" aria-expanded="false">Show my application</button>
      <button class="btn go-btn btn-approve">Approve this application</button>
    </div>
    <p class="approve-out" aria-live="polite"></p>
    <div class="doc-view" hidden></div>
  </article>`;
}

function docUrl(jobId) {
  return `/apply/${encodeURIComponent(state.sid)}/${encodeURIComponent(jobId)}/document`;
}

// Shows the finished resume + cover letter inside the page.
function toggleDoc(art, forceOpen = false) {
  const view = $(".doc-view", art), btn = $(".btn-preview", art);
  const open = forceOpen || view.hidden;
  if (open) {
    view.innerHTML = `<iframe title="Your application" src="${docUrl(art.dataset.job)}?t=${Date.now()}"></iframe>
      <div class="actions"><a class="btn ghost" href="${docUrl(art.dataset.job)}" target="_blank" rel="noopener">Open in a new tab to print or save as PDF</a></div>`;
    const frame = $("iframe", view);
    frame.addEventListener("load", () => { frame.style.height = frame.contentDocument.documentElement.scrollHeight + "px"; });
  }
  view.hidden = !open;
  btn.textContent = open ? "Hide my application" : "Show my application";
  btn.setAttribute("aria-expanded", open);
  if (open) view.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function approve(e) {
  const art = e.currentTarget.closest(".app"), out = $(".approve-out", art);
  if ($$(".ck", art).some((c) => !c.checked)) { out.innerHTML = `<span class="err">Tick every item in "Before you apply" first.</span>`; return; }
  try {
    const d = await api("PUT", `/apply/${state.sid}/${encodeURIComponent(art.dataset.job)}/approve`, {
      summary: $(".ed-summary", art).value, cover_note: $(".ed-cover", art).value,
    });
    out.innerHTML = `<span class="approved">Approved.</span> Your resume and cover letter are ready below.
      <div class="actions" style="margin-top:14px">
        <a class="btn go-btn" href="${docUrl(art.dataset.job)}" target="_blank" rel="noopener">Print or save as PDF</a>
        ${d.apply_link ? `<a class="btn ghost" href="${esc(d.apply_link)}" target="_blank" rel="noopener">Apply on the job ad</a>` : `<span class="hint">Demo listing, so there's no real ad to apply on.</span>`}
      </div>
      <p class="hint">Save it as a PDF, then upload that PDF when you apply.</p>` +
      (d.warnings.length ? `<p class="err">${esc(d.warnings.join(" "))}</p>` : "");
    // Show the approved version (with the candidate's edits) straight away.
    toggleDoc(art, true);
  } catch (ex) { out.innerHTML = `<span class="err">${esc(ex.message)}</span>`; }
}

/* ---- GROW ---- */
function renderPlan(plan) {
  $("#grow-lede").textContent = plan.headline + " " + plan.how_to_recheck;
  const tag = { learn: "Missing", add_proof: "Prove it", nice_to_have: "Nice to have" };
  $("#plan").innerHTML = plan.items.map((it) => `
    <li><div>
      <h4>${esc(it.skill)}<span class="tag ${it.gap_type}">${tag[it.gap_type]}</span></h4>
      <p class="why">${esc(it.why)}${it.needed_by_jobs.length ? `: ${esc(it.needed_by_jobs.slice(0, 3).join(", "))}` : ""}</p>
      <p class="act">${esc(it.action)}</p>
      <p class="eff">Time: ${esc(it.effort_estimate)}</p>
      ${it.courses.length ? `<p>${it.courses.map((c) => `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.title)}</a>`).join(", ")}</p>` : ""}
    </div></li>`).join("") || "<li><div><h4>Nothing to learn for these jobs</h4><p>You could go back and choose Go.</p></div></li>";
  $("#tips").hidden = !plan.ai_tips?.length;
  $("#tips").innerHTML = (plan.ai_tips || []).map((t) => `<li>${esc(t)}</li>`).join("");
  $("#recheck-out").innerHTML = "";
}

$("#btn-recheck").addEventListener("click", async (e) => {
  const btn = e.currentTarget, out = $("#recheck-out");
  const files = $("#re-files").files, links = $("#re-links").value.trim();
  out.innerHTML = "";
  busy(btn, true, "Checking...");
  try {
    if (files.length || links) {
      const fd = new FormData();
      [...files].forEach((f) => fd.append("files", f));
      if (links) fd.append("links", links);
      fd.append("session_id", state.sid);
      await api("POST", "/upload", fd, true);
    }
    const r = await api("POST", `/recheck/${state.sid}`);
    state.readiness = await api("GET", `/readiness/${state.sid}`);
    state.matches = await api("GET", `/match/${state.sid}`);
    out.innerHTML = `<div class="diff">
      ${r.now_green.length ? `<p><strong>Now on track:</strong> ${esc(r.now_green.join(", "))}</p>` : "<p>No new skills found yet. Make sure your new project is in the file or link you added.</p>"}
      <p>Jobs you're ready for: ${r.jobs_ready_before} before, <strong>${r.jobs_ready_now} now</strong>.</p>
      ${r.still_missing.length ? `<p>Still missing: ${esc(r.still_missing.join(", "))}</p>` : ""}
      <p>${esc(r.message)}</p>
      <button class="btn primary" id="btn-see">See my updated matches</button></div>`;
    $("#btn-see").addEventListener("click", () => { renderResults(); show("v-results").then(() => Motion.results && Motion.results()); });
  } catch (ex) { out.innerHTML = `<p class="err">${esc(ex.message)}</p>`; }
  busy(btn, false);
});

/* ================= start ================= */
api("GET", "/health").then((h) => {
  $("#mode").textContent = h.ai_mode === "demo" ? "Demo mode (no AI key)" : `AI: ${h.ai_mode}`;
}).catch(() => {});
show("v-upload");
Motion.heroIntro && Motion.heroIntro();
Motion.dropMagnet && Motion.dropMagnet($("#drop"));
