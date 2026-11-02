const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const TYPE_COLORS = { Person: "--ink", Skill: "--fact", Technology: "--n-tech", Organization: "--n-org", Role: "--n-role", Concept: "--n-concept" };
const color = (t) => css(TYPE_COLORS[t] || "--n-concept");
const MODES = { graph: "Graph and meaning", hybrid: "Graph, meaning and keywords", vector: "Meaning only", lexical: "Keywords only" };

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}

// ---------- views: #ask, #graph, #documents
const drawn = {};
function showView() {
  const name = ["ask", "graph", "documents"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "ask";
  $$("[data-view]").forEach((v) => { v.hidden = v.dataset.view !== name; });
  document.body.dataset.view = name;  // the Ask view's top bar sits over the dark hero
  $$("[data-view-link]").forEach((a) => { if (a.dataset.viewLink === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  // Cytoscape needs a visible container to lay out, so each view draws on first show.
  if (name === "graph" && !drawn.graph) { drawn.graph = true; loadGraph(); }
  if (name === "documents" && !drawn.docs) { drawn.docs = true; loadDocs(); }
}
window.addEventListener("hashchange", showView);

// ---------- graph drawing
function drawGraph(el, nodes, edges, { seeds = new Set(), path = new Set(), spread = 1, labelTop = Infinity } = {}) {
  if (!window.cytoscape) { el.innerHTML = '<p class="hint" style="padding:16px">The graph library did not load. Check the network connection.</p>'; return; }
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
      { selector: "node", style: { "background-color": (n) => color(n.data("type")), label: "data(label)", "font-family": "Schibsted Grotesk", "font-size": 9, color: css("--ink"), "text-valign": "bottom", "text-margin-y": 4, width: 11, height: 11, "text-wrap": "ellipsis", "text-max-width": 110 } },
      { selector: "node[seed = 1]", style: { width: 18, height: 18, "border-width": 3, "border-color": css("--ink"), "background-color": css("--sheet"), "font-weight": 600 } },
      { selector: "edge", style: { width: 1, "line-color": css("--line"), "curve-style": "bezier", "target-arrow-shape": "triangle", "target-arrow-color": css("--line"), "arrow-scale": 0.6 } },
      { selector: "edge[hot = 1]", style: { width: 3, "line-color": css("--fact"), "target-arrow-color": css("--fact"), label: "data(label)", "font-size": 8, color: css("--fact"), "text-rotation": "autorotate" } },
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
  const from = ranges.length ? Math.max(0, ranges[0][0] - 220) : 0;
  const to = ranges.length ? Math.min(text.length, Math.max(ranges[ranges.length - 1][1] + 220, from + 420)) : Math.min(text.length, 420);
  let html = "", at = from;
  for (const [a, b] of ranges) { html += esc(text.slice(at, a)) + `<mark>${esc(text.slice(a, b))}</mark>`; at = b; }
  html += esc(text.slice(at, to));
  return { html: (from > 0 ? "… " : "") + html + (to < text.length ? " …" : ""), cut: from > 0 || to < text.length };
}

function renderSources(sources, claims) {
  const quotes = {};
  for (const c of claims) for (const [m, qs] of Object.entries(c.quotes || {})) (quotes[m] ||= []).push(...qs);
  return sources.map((s, i) => {
    const id = `S${i + 1}`, ex = markQuotes(s.text, quotes[id] || []);
    return `<li class="source" id="src-${id}">
      <header><b>${id}</b><span>${esc(s.title)}</span>${s.page ? `<span>page ${s.page}</span>` : ""}<span>found by ${esc(s.via.replaceAll("+", ", "))}</span></header>
      <blockquote>${ex.html}</blockquote>
      ${ex.cut ? `<details><summary>Whole passage</summary><p>${esc(s.text)}</p></details>` : ""}</li>`;
  }).join("");
}

function renderClaims(r) {
  if (!r.claims.length) return `<p class="abstain">${esc(r.answer)}</p><p>Try rephrasing the question, or search with keywords if it names exact terms.</p>`;
  return `<ul class="claims">${r.claims.map((c, i) => `<li><button type="button" class="claim" data-claim="${i}" aria-pressed="false">${esc(c.text)}
    <span class="chips">${c.cites.map((m) => `<span class="chip ${m[0] === "F" ? "f" : ""}">${m}</span>`).join("")}</span></button></li>`).join("")}</ul>`;
}

function renderExperts(experts) {
  if (!experts.length) return "";
  return `<div class="panel"><h2>Ranked experts</h2><p class="hint">Bar: graph links (teal), coverage of your question (navy), similar documents (grey).</p>${experts.map((e) => {
    const s = e.signals;  // segment length = weighted contribution of each signal to the score (max 1)
    return `<div class="expert"><strong>${esc(e.name)}</strong><span class="score">${e.score.toFixed(2)}</span>
      <div class="bar-3" title="graph ${s.graph}, coverage ${s.coverage}, similar documents ${s.semantic}">
        <span class="g" style="width:${s.graph * 40}%"></span><span class="m" style="width:${s.coverage * 30}%"></span><span class="s" style="width:${s.semantic * 30}%"></span></div>
      <span class="small">${e.covers && e.covers.length ? "Linked to " + esc(e.covers.join(", ")) : "Ranked by document similarity only"}</span></div>`;
  }).join("")}</div>`;
}

function renderRecs(recs) {
  if (!recs.length) return "";
  return `<div class="panel"><h2>Recommended documents</h2>${recs.map((r) =>
    `<div class="rec"><span>${esc(r.title)}</span><span>${r.score.toFixed(2)}</span></div>`).join("")}</div>`;
}

let current = null;
async function askQuestion(q) {
  const mode = $("#mode").value, btn = $("#ask-btn");
  btn.disabled = true; btn.textContent = "Asking…";
  $("#result").hidden = false;
  $("#result").classList.add("busy");
  $("#answer").className = "answer loading";
  $("#answer").textContent = "Searching the documents and the graph, then checking every quote.";
  for (const id of ["#experts", "#recs", "#sources", "#trace", "#meta"]) $(id).innerHTML = "";
  try {
    const r = current = await api("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, mode }) });
    $("#answer").className = "answer";
    $("#answer").innerHTML = renderClaims(r);
    const retried = ["graph", "hybrid"].includes(r.mode) && r.explanation.corrective_retries ? ["Question rewritten once"] : [];
    $("#meta").innerHTML = [MODES[r.mode], `${r.latency_s} s`, ...retried].map((t) => `<span>${esc(t)}</span>`).join("")
      + r.warnings.map((w) => `<span class="warn">${esc(w)}</span>`).join("");
    $("#experts").innerHTML = renderExperts(r.experts);
    $("#recs").innerHTML = renderRecs(r.recommendations);
    $("#sources").innerHTML = renderSources(r.sources, r.claims);
    $("#trace").innerHTML = r.trace.map((t) => `<li>${esc(t.step)}: ${esc(JSON.stringify(Object.fromEntries(Object.entries(t).filter(([k]) => !["step", "t"].includes(k)))))}</li>`).join("");
    const seeds = new Set((r.graph.nodes || []).filter((n) => n.hops === 0).map((n) => n.key));
    const keyOf = Object.fromEntries((r.graph.nodes || []).map((n) => [n.name, n.key]));
    const path = new Set((r.explanation.reasoning_path || []).map((f) => `${keyOf[f.source]}|${keyOf[f.target]}`));
    if (r.graph.nodes && r.graph.nodes.length) drawGraph($("#qgraph"), r.graph.nodes, r.graph.edges, { seeds, path });
    else $("#qgraph").innerHTML = `<p class="hint" style="padding:16px">"${esc(MODES[r.mode])}" does not use the graph. Choose a graph search to see it.</p>`;
    $("#result").scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  } catch (e) {
    $("#answer").className = "answer error";
    $("#answer").textContent = `The question could not be answered: ${e.message}. Check that the server is running, then ask again.`;
  } finally {
    btn.disabled = false; btn.textContent = "Ask";
    $("#result").classList.remove("busy");
  }
}

// Picking a claim dims the passages it does not cite and brings the first cited one into view.
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
$("#suggest").addEventListener("click", (e) => { if (e.target.tagName === "BUTTON") { $("#q").value = e.target.textContent; $("#ask-form").requestSubmit(); } });

// ---------- graph and documents views
async function loadGraph() {
  try {
    const [s, g] = await Promise.all([api("/api/stats"), api("/api/graph?limit=90")]);
    $("#stats").textContent = `${s.documents} documents, ${s.chunks} passages, ${s.entities} entities and ${s.relations} relations, stored in ${s.backend === "neo4j" ? "Neo4j" : "memory"}.`;
    drawGraph($("#biggraph"), g.nodes, g.edges, { spread: 2.5, labelTop: 30 });  // nodes arrive sorted by degree
    $("#legend").innerHTML = Object.keys(TYPE_COLORS).map((t) => `<li><i style="background:${color(t)}"></i>${t}</li>`).join("");
  } catch (e) { $("#stats").textContent = `The graph could not be loaded: ${e.message}.`; }
}

async function loadDocs() {
  try {
    const docs = await api("/api/documents");
    $("#doclist").innerHTML = docs.length
      ? docs.map((d) => `<li><button type="button" data-id="${esc(d.id)}" aria-pressed="false"><span>${esc(d.title)}</span><small>${d.ocr ? "scanned" : ""}</small></button></li>`).join("")
      : '<li class="hint" style="padding:10px">No documents yet. Add some with scripts/ingest.py or POST /api/ingest.</li>';
  } catch (e) { $("#doclist").innerHTML = `<li class="error" style="padding:10px">The documents could not be loaded: ${esc(e.message)}.</li>`; }
}

$("#doclist").addEventListener("click", async (e) => {
  const b = e.target.closest("button"); if (!b) return;
  $$("#doclist button").forEach((x) => x.setAttribute("aria-pressed", x === b));
  $("#similar").innerHTML = '<p class="hint">Finding the closest documents…</p>';
  try {
    const recs = await api(`/api/recommend?doc_id=${encodeURIComponent(b.dataset.id)}`);
    $("#similar").innerHTML = `<h2>Closest to ${esc(b.querySelector("span").textContent)}</h2><p class="hint">Score: 70% meaning, 30% shared entities.</p>` + recs.map((r) =>
      `<div class="rec"><span>${esc(r.title)}</span><span>${r.score.toFixed(2)}</span></div>`).join("");
  } catch (err) { $("#similar").innerHTML = `<p class="error">${esc(err.message)}</p>`; }
});

// Shareable questions: /?q=...&mode=hybrid opens the page and asks right away.
const params = new URLSearchParams(location.search);
if (["light", "dark"].includes(params.get("theme"))) document.documentElement.dataset.theme = params.get("theme");
showView();
if (params.get("q")) {
  $("#q").value = params.get("q");
  if (MODES[params.get("mode")]) $("#mode").value = params.get("mode");
  askQuestion(params.get("q"));
}
