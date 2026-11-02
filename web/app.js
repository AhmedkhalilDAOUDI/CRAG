const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const TYPE_COLORS = { Person: "--text", Skill: "--olive", Technology: "--n-tech", Organization: "--n-org", Role: "--n-role", Concept: "--n-concept" };
const color = (t) => css(TYPE_COLORS[t] || "--n-concept");
const MODES = { graph: "Graph and meaning", hybrid: "Graph, meaning and keywords", vector: "Meaning only", lexical: "Keywords only" };
const VIEWS = { ask: "Ask", documents: "Documents", graph: "Graph" };
const ARROW = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
const TRASH = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6"/></svg>';
const FILE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>';

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}

// ---------- views: #ask, #documents, #graph
const drawn = {};
function showView() {
  const name = VIEWS[location.hash.slice(1)] ? location.hash.slice(1) : "ask";
  $$("[data-view]").forEach((v) => { v.hidden = v.dataset.view !== name; });
  $$("[data-view-link]").forEach((a) => { if (a.dataset.viewLink === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  $("#crumb").textContent = VIEWS[name];
  // Cytoscape needs a visible container to lay out, so each view draws on first show.
  if (name === "graph" && !drawn.graph) { drawn.graph = true; loadGraph(); }
  if (name === "documents" && !drawn.docs) { drawn.docs = true; loadDocs(); }
}
window.addEventListener("hashchange", showView);

// Sidebar counts and status, shared by every view.
const statsReady = api("/api/stats").catch(() => null);
statsReady.then((s) => {
  if (!s) return;
  $("#count-docs").textContent = s.documents;
  $("#count-entities").textContent = s.entities.toLocaleString();
  $("#topstats").textContent = `${s.documents} documents, ${s.chunks} passages`;
});
let readOnly = false;
api("/api/health").then((h) => { readOnly = h.read_only; $("#status").textContent = `${h.backend === "neo4j" ? "Neo4j" : "Memory"} backend${h.read_only ? ", read-only" : ""}`; })
  .catch(() => { $("#status").textContent = "Server unreachable"; });

// ---------- graph drawing
function drawGraph(el, nodes, edges, { seeds = new Set(), path = new Set(), spread = 1, labelTop = Infinity } = {}) {
  if (!window.cytoscape) { el.innerHTML = '<p class="empty-inline">The graph library did not load. Check the network connection.</p>'; return; }
  const ids = new Set(nodes.map((n) => n.key)), seen = new Set();
  // One drawn edge per node pair: repeated facts from several passages would pull clusters into knots.
  edges = edges.filter((e) => { const k = `${e.source}|${e.target}`; if (seen.has(k) && !path.has(k)) return false; seen.add(k); return true; });
  return cytoscape({
    container: el,
    elements: [
      ...nodes.map((n, i) => ({ data: { id: n.key, label: i < labelTop || seeds.has(n.key) ? n.name : "", type: n.type, seed: seeds.has(n.key) ? 1 : 0 } })),
      ...edges.filter((e) => ids.has(e.source) && ids.has(e.target))
        .map((e, i) => ({ data: { id: `e${i}`, source: e.source, target: e.target, label: e.type, hot: path.has(`${e.source}|${e.target}`) ? 1 : 0 } })),
    ],
    style: [
      { selector: "node", style: { "background-color": (n) => color(n.data("type")), label: "data(label)", "font-family": "Arial", "font-size": 9, color: css("--text-2"), "text-valign": "bottom", "text-margin-y": 4, width: 11, height: 11, "text-wrap": "ellipsis", "text-max-width": 110, "text-outline-color": "#1d1f1a", "text-outline-width": 2 } },
      { selector: "node[seed = 1]", style: { width: 18, height: 18, "border-width": 3, "border-color": css("--accent"), "background-color": "#1d1f1a", "font-weight": 600, color: css("--text") } },
      { selector: "edge", style: { width: 1, "line-color": css("--line"), "curve-style": "bezier", "target-arrow-shape": "triangle", "target-arrow-color": css("--line"), "arrow-scale": 0.6 } },
      { selector: "edge[hot = 1]", style: { width: 3, "line-color": css("--mark"), "target-arrow-color": css("--mark"), label: "data(label)", "font-size": 8, color: css("--mark"), "text-rotation": "autorotate", "text-outline-color": "#1d1f1a", "text-outline-width": 2 } },
    ],
    layout: { name: "cose", animate: false, padding: 24, nodeRepulsion: 12000 * spread, idealEdgeLength: 70 * spread, componentSpacing: 60 * spread, gravity: 0.4 / spread, nodeOverlap: 12, numIter: 2500 },
    wheelSensitivity: 0.2,
  });
}

// ---------- evidence: passage excerpts with the verified quotes marked
// Words only, any punctuation or spacing between them: the same rule as the server's quote check.
const words = (q) => (q.match(/[\p{L}\p{N}_]+/gu) || []).join("[^\\p{L}\\p{N}_]+");

function markQuotes(text, quotes) {
  const ranges = quotes.flatMap((q) => { const m = words(q) && new RegExp(words(q), "iu").exec(text); return m ? [[m.index, m.index + m[0].length]] : []; })
    .sort((a, b) => a[0] - b[0]).reduce((out, r) => { const last = out[out.length - 1]; if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]); else out.push(r); return out; }, []);
  const from = ranges.length ? Math.max(0, ranges[0][0] - 160) : 0;
  const to = ranges.length ? Math.min(text.length, Math.max(ranges[ranges.length - 1][1] + 160, from + 300)) : Math.min(text.length, 300);
  let html = "", at = from;
  for (const [a, b] of ranges) { html += esc(text.slice(at, a)) + `<mark>${esc(text.slice(a, b))}</mark>`; at = b; }
  html += esc(text.slice(at, to));
  return { html: (from > 0 ? "… " : "") + html + (to < text.length ? " …" : ""), cut: from > 0 || to < text.length, marked: ranges.length > 0 };
}

function renderSources(sources, claims) {
  const quotes = {};
  for (const c of claims) for (const [m, qs] of Object.entries(c.quotes || {})) (quotes[m] ||= []).push(...qs);
  return sources.map((s, i) => {
    const id = `S${i + 1}`, ex = markQuotes(s.text, quotes[id] || []);
    return `<li class="source${ex.marked ? " cited" : ""}" id="src-${id}">
      <span class="source-number">SOURCE ${i + 1}${s.page ? `, PAGE ${s.page}` : ""}</span>
      <strong>${esc(s.title)}</strong><small>Found by ${esc(s.via.replaceAll("+", ", "))}</small>
      <blockquote>${ex.html}</blockquote>
      ${ex.cut ? `<details><summary>Whole passage</summary><p>${esc(s.text)}</p></details>` : ""}</li>`;
  }).join("");
}

function renderClaims(r) {
  if (!r.claims.length) return `<p class="abstain">${esc(r.answer)}</p><p>Try rephrasing the question, or search with keywords if it names exact terms.</p>`;
  return `<ul class="claims">${r.claims.map((c, i) => `<li><button type="button" class="claim" data-claim="${i}" aria-pressed="false">${esc(c.text)}${
    c.cites.map((m) => `<span class="citation ${m[0] === "F" ? "f" : ""}">${m}</span>`).join("")}</button></li>`).join("")}</ul>`;
}

const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => /\d/.test(w) ? w.slice(-2) : w[0].toUpperCase()).join("");

function renderExperts(experts) {
  if (!experts.length) return "";
  return `<div class="panel"><h3>Ranked experts</h3><p class="small">Bar: graph links (olive), coverage of your question (terracotta), similar documents (grey).</p>${experts.map((e) => {
    const s = e.signals;  // segment length = weighted contribution of each signal to the score (max 1)
    return `<article class="expert"><div class="person-initials" aria-hidden="true">${esc(initials(e.name))}</div><div>
      <div class="row"><strong>${esc(e.name)}</strong><span class="score">${e.score.toFixed(2)}</span></div>
      <div class="bar-3" title="graph ${s.graph}, coverage ${s.coverage}, similar documents ${s.semantic}">
        <span class="g" style="width:${s.graph * 40}%"></span><span class="m" style="width:${s.coverage * 30}%"></span><span class="s" style="width:${s.semantic * 30}%"></span></div>
      <span class="small">${e.covers && e.covers.length ? "Linked to " + esc(e.covers.join(", ")) : "Ranked by document similarity only"}</span></div></article>`;
  }).join("")}</div>`;
}

function renderRecs(recs) {
  if (!recs.length) return "";
  return `<div class="panel"><h3>Recommended documents</h3>${recs.map((r) =>
    `<div class="rec"><span>${esc(r.title)}</span><span>${r.score.toFixed(2)}</span></div>`).join("")}</div>`;
}

let current = null;
async function askQuestion(q) {
  const mode = $("#mode").value, btn = $("#ask-btn");
  btn.disabled = true;
  $("#start").hidden = true;
  $("#result").hidden = false;
  $("#asked").textContent = q;
  $("#meta").textContent = MODES[mode].toUpperCase();
  $("#answer").innerHTML = '<p class="loading">Searching the documents and the graph, then checking every quote.</p>';
  for (const id of ["#experts", "#recs", "#sources", "#trace", "#latency", "#warnings", "#source-count"]) $(id).innerHTML = "";
  $("#qgraph").innerHTML = "";
  try {
    const r = current = await api("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, mode }) });
    const retried = ["graph", "hybrid"].includes(r.mode) && r.explanation.corrective_retries ? ", QUESTION REWRITTEN ONCE" : "";
    $("#meta").textContent = MODES[r.mode].toUpperCase() + retried;
    $("#latency").textContent = `${r.latency_s} S`;
    $("#warnings").innerHTML = r.warnings.map((w) => `<p class="warning">${esc(w)}</p>`).join("");
    $("#answer").innerHTML = renderClaims(r);
    $("#experts").innerHTML = renderExperts(r.experts);
    $("#recs").innerHTML = renderRecs(r.recommendations);
    $("#source-count").textContent = r.sources.length;
    $("#sources").innerHTML = renderSources(r.sources, r.claims);
    $("#trace").innerHTML = r.trace.map((t) => `<li>${esc(t.step)}: ${esc(JSON.stringify(Object.fromEntries(Object.entries(t).filter(([k]) => !["step", "t"].includes(k)))))}</li>`).join("");
    const seeds = new Set((r.graph.nodes || []).filter((n) => n.hops === 0).map((n) => n.key));
    const keyOf = Object.fromEntries((r.graph.nodes || []).map((n) => [n.name, n.key]));
    const path = new Set((r.explanation.reasoning_path || []).map((f) => `${keyOf[f.source]}|${keyOf[f.target]}`));
    if (r.graph.nodes && r.graph.nodes.length) drawGraph($("#qgraph"), r.graph.nodes, r.graph.edges, { seeds, path });
    else $("#qgraph").innerHTML = `<p class="empty-inline">"${esc(MODES[r.mode])}" does not use the graph. Choose a graph search to see it.</p>`;
  } catch (e) {
    $("#answer").innerHTML = `<p class="error">The question could not be answered: ${esc(e.message)}. Check that the server is running, then ask again.</p>`;
  } finally {
    btn.disabled = false;
  }
}

// Picking a claim dims the sources it does not cite and brings the first cited one into view.
$("#answer").addEventListener("click", (e) => {
  const b = e.target.closest(".claim"); if (!b || !current) return;
  const on = b.getAttribute("aria-pressed") !== "true";
  $$(".claim").forEach((x) => x.setAttribute("aria-pressed", x === b && on));
  const cited = new Set(on ? current.claims[b.dataset.claim].cites : []);
  $$(".source").forEach((li) => li.classList.toggle("dim", on && !cited.has(li.id.slice(4))));
  const first = $$(".source").find((li) => cited.has(li.id.slice(4)));
  if (first) first.scrollIntoView({ block: "nearest" });
});

$("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#q").value.trim(); if (q) askQuestion(q); });
$("#q").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#ask-form").requestSubmit(); } });
$("#suggest").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  $("#q").value = b.textContent.trim(); $("#ask-form").requestSubmit();
});

// ---------- graph and documents views
async function loadGraph() {
  try {
    const [s, g] = await Promise.all([statsReady, api("/api/graph?limit=90")]);
    if (s) $("#stats").innerHTML = [["documents", s.documents], ["passages", s.chunks], ["entities", s.entities], ["relations", s.relations]]
      .map(([k, v]) => `<span><b>${v.toLocaleString()}</b>${k}</span>`).join("") + `<span>stored in ${s.backend === "neo4j" ? "Neo4j" : "memory"}</span>`;
    drawGraph($("#biggraph"), g.nodes, g.edges, { spread: 2.5, labelTop: 30 });  // nodes arrive sorted by degree
    $("#legend").innerHTML = Object.keys(TYPE_COLORS).map((t) => `<li><i style="background:${color(t)}"></i>${t}</li>`).join("");
  } catch (e) { $("#stats").innerHTML = `<span class="error">The graph could not be loaded: ${esc(e.message)}.</span>`; }
}

let docs = [];
function renderDocs() {
  const f = $("#doc-filter").value.trim().toLowerCase();
  const shown = docs.filter((d) => d.title.toLowerCase().includes(f));
  $("#doc-count").textContent = `${shown.length} of ${docs.length}`;
  $("#doclist").innerHTML = shown.length
    ? shown.map((d) => `<li class="document-row"><button type="button" class="doc-open" data-id="${esc(d.id)}" aria-pressed="false"><span class="file-icon">${FILE}</span>
        <span class="document-name"><strong>${esc(d.title)}</strong><span>${esc(d.source || "")}${d.chars ? `, ${Math.round(d.chars / 1000)}k characters` : ""}${d.ocr ? ", scanned" : ""}</span></span>
        <span class="ready-state">Indexed</span></button>
        <button type="button" class="doc-remove" data-remove="${esc(d.id)}" aria-label="Remove ${esc(d.title)}" title="Remove document">${TRASH}</button></li>`).join("")
    : `<li class="empty-inline">${docs.length ? "No document matches that filter." : "No documents yet. Add some with scripts/ingest.py or POST /api/ingest."}</li>`;
}
async function loadDocs() {
  try { docs = await api("/api/documents"); renderDocs(); }
  catch (e) { $("#doclist").innerHTML = `<li class="error">The documents could not be loaded: ${esc(e.message)}.</li>`; }
}
$("#doc-filter").addEventListener("input", renderDocs);

$("#doclist").addEventListener("click", async (e) => {
  const rm = e.target.closest("[data-remove]");
  if (rm) return openDelete(docs.find((d) => d.id === rm.dataset.remove));
  const b = e.target.closest(".doc-open"); if (!b) return;
  $$("#doclist .doc-open").forEach((x) => x.setAttribute("aria-pressed", x === b));
  $("#similar").innerHTML = '<p class="loading">Finding the closest documents…</p>';
  try {
    const recs = await api(`/api/recommend?doc_id=${encodeURIComponent(b.dataset.id)}`);
    $("#similar").innerHTML = `<h2>Closest to ${esc(b.querySelector("strong").textContent)}</h2><p class="small">Score: 70% meaning, 30% shared entities.</p>` + recs.map((r) =>
      `<div class="rec"><span>${esc(r.title)}</span><span>${r.score.toFixed(2)}</span></div>`).join("");
  } catch (err) { $("#similar").innerHTML = `<p class="error">${esc(err.message)}</p>`; }
});

// ---------- upload and remove (need the server's admin token; refused on a read-only deployment)
// The token is kept only for this tab, so it is not retyped for every file.
const TOKEN_KEY = "crag-admin-token";
const savedToken = () => { try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; } };
const saveToken = (t) => { try { sessionStorage.setItem(TOKEN_KEY, t); } catch { /* private mode: ask again next time */ } };

async function refreshAfterChange() {
  const s = await api("/api/stats").catch(() => null);
  if (s) { $("#count-docs").textContent = s.documents; $("#count-entities").textContent = s.entities.toLocaleString(); $("#topstats").textContent = `${s.documents} documents, ${s.chunks} passages`; }
  drawn.graph = false;  // redraw the graph view next time it is opened
  if (drawn.docs) await loadDocs();
}

function prepareDialog(dlg, tokenInput, submit) {
  dlg.querySelector(".readonly-note").hidden = !readOnly;
  tokenInput.closest(".field").hidden = readOnly;
  tokenInput.value = savedToken();
  submit.disabled = readOnly;
  dlg.showModal();
}
$$("[data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));

let picked = [];
function showPicked() {
  $("#upload-list").innerHTML = picked.map((f, i) => `<li data-i="${i}"><span>${esc(f.name)}</span><span class="state">${f.size < 1048576 ? `${Math.max(1, Math.round(f.size / 1024))} KB` : `${(f.size / 1048576).toFixed(1)} MB`}</span></li>`).join("");
  $("#upload-submit").disabled = readOnly || !picked.length;
}
$("#upload-open").addEventListener("click", () => { picked = []; showPicked(); prepareDialog($("#upload-dialog"), $("#admin-token"), $("#upload-submit")); $("#upload-submit").disabled = true; });
$("#upload-files").addEventListener("change", (e) => { picked = [...e.target.files]; showPicked(); });
const dz = $("#dropzone");
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
dz.addEventListener("dragleave", () => dz.classList.remove("over"));
dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("over"); picked = [...e.dataTransfer.files]; showPicked(); });

$("#upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();  // keep the dialog open to show each file's result
  const token = $("#admin-token").value.trim(), btn = $("#upload-submit");
  if (!token) { $("#admin-token").focus(); return; }
  btn.disabled = true; btn.textContent = "Indexing…";
  let changed = false;
  for (const [i, f] of picked.entries()) {
    const state = $(`#upload-list li[data-i="${i}"] .state`);
    state.className = "state"; state.textContent = "Indexing…";
    const body = new FormData(); body.append("file", f);
    try {
      const r = await api("/api/ingest", { method: "POST", headers: { "X-Admin-Token": token }, body });
      saveToken(token); changed = true;
      state.className = "state ok";
      state.textContent = r.duplicate ? "Already indexed" : `Indexed: ${r.chunks} passages, ${r.relations} relations${r.replaced ? " (replaced old version)" : ""}`;
    } catch (err) {
      state.className = "state bad"; state.textContent = err.message;
      if (/token/i.test(err.message)) break;  // a wrong token fails every file the same way
    }
  }
  btn.textContent = "Upload and index"; btn.disabled = false;
  if (changed) refreshAfterChange();
});

let removing = null;
function openDelete(d) {
  if (!d) return;
  removing = d;
  $("#delete-text").textContent = `"${d.title}" will be removed with its passages, the relations extracted from it, and any entity no other document mentions. This cannot be undone.`;
  $("#delete-error").textContent = "";
  prepareDialog($("#delete-dialog"), $("#admin-token-2"), $("#delete-submit"));
}
$("#delete-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const token = $("#admin-token-2").value.trim(), btn = $("#delete-submit");
  if (!token) { $("#admin-token-2").focus(); return; }
  btn.disabled = true; btn.textContent = "Removing…";
  try {
    await api(`/api/documents/${encodeURIComponent(removing.id)}`, { method: "DELETE", headers: { "X-Admin-Token": token } });
    saveToken(token);
    $("#delete-dialog").close();
    $("#similar").innerHTML = '<p class="empty-inline">No document picked yet.</p>';
    await refreshAfterChange();
  } catch (err) { $("#delete-error").textContent = err.message; }
  finally { btn.disabled = false; btn.textContent = "Remove document"; }
});

// Shareable questions: /?q=...&mode=hybrid opens the page and asks right away.
const params = new URLSearchParams(location.search);
showView();
if (params.get("q")) {
  $("#q").value = params.get("q");
  if (MODES[params.get("mode")]) $("#mode").value = params.get("mode");
  askQuestion(params.get("q"));
}
