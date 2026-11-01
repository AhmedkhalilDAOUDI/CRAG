const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const TYPE_COLORS = { Person: "--clay", Skill: "--olive", Technology: "--ink", Organization: "--ink-2", Role: "--olive", Concept: "--ink-2" };
const color = (t) => css(TYPE_COLORS[t] || "--ink-2");

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}

// Minimal, escape-first markdown: paragraphs, bullet lists, bold, and citation chips.
function render(md) {
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[(S|F)(\d+)\]/g, (_, k, n) => `<button type="button" class="cite ${k.toLowerCase()}" data-ref="${k}${n}">${k}${n}</button>`);
  const out = []; let list = null;
  for (const line of md.split("\n")) {
    const m = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
    if (m) { list = list || []; list.push(`<li>${inline(m[1])}</li>`); continue; }
    if (list) { out.push(`<ul>${list.join("")}</ul>`); list = null; }
    if (line.trim()) out.push(`<p>${inline(line.replace(/^#+\s*/, ""))}</p>`);
  }
  if (list) out.push(`<ul>${list.join("")}</ul>`);
  return out.join("");
}

function drawGraph(el, nodes, edges, { seeds = new Set(), path = new Set(), spread = 1, labelTop = Infinity } = {}) {
  if (!window.cytoscape) { el.innerHTML = '<p class="hint" style="padding:16px">Graph view unavailable offline.</p>'; return; }
  const ids = new Set(nodes.map((n) => n.key)), seen = new Set();
  // One drawn edge per node pair: repeated facts from several passages would pull clusters into knots.
  edges = edges.filter((e) => { const k = `${e.source}|${e.target}`; if (seen.has(k) && !path.has(k)) return false; seen.add(k); return true; });
  const cy = cytoscape({
    container: el,
    elements: [
      ...nodes.map((n, i) => ({ data: { id: n.key, label: i < labelTop || seeds.has(n.key) ? n.name : "", type: n.type, seed: seeds.has(n.key) ? 1 : 0 } })),
      ...edges.filter((e) => ids.has(e.source) && ids.has(e.target))
        .map((e, i) => ({ data: { id: `e${i}`, source: e.source, target: e.target, label: e.type, hot: path.has(`${e.source}|${e.target}`) ? 1 : 0 } })),
    ],
    style: [
      { selector: "node", style: { "background-color": (n) => color(n.data("type")), label: "data(label)", "font-family": "Public Sans", "font-size": 9, color: css("--ink"), "text-valign": "bottom", "text-margin-y": 4, width: 12, height: 12, "text-wrap": "ellipsis", "text-max-width": 110 } },
      { selector: "node[seed = 1]", style: { width: 20, height: 20, "border-width": 3, "border-color": css("--clay"), "background-color": css("--paper"), "font-weight": 600 } },
      { selector: "edge", style: { width: 1, "line-color": css("--line"), "curve-style": "bezier", "target-arrow-shape": "triangle", "target-arrow-color": css("--line"), "arrow-scale": 0.6 } },
      { selector: "edge[hot = 1]", style: { width: 3, "line-color": css("--clay"), "target-arrow-color": css("--clay"), label: "data(label)", "font-size": 8, color: css("--clay"), "text-rotation": "autorotate" } },
    ],
    layout: { name: "cose", animate: false, padding: 24, nodeRepulsion: 12000 * spread, idealEdgeLength: 70 * spread, componentSpacing: 60 * spread, gravity: 0.4 / spread, nodeOverlap: 12, numIter: 2500 },
    wheelSensitivity: 0.2,
  });
  return cy;
}

function renderExperts(experts) {
  if (!experts.length) return "";
  return `<div class="panel"><h2 class="h3">Ranked experts</h2>${experts.map((e) => {
    const s = e.signals;  // bar length = weighted contribution of each signal to the score (max 1)
    return `<div class="expert"><strong>${esc(e.name)}</strong><span>${e.score.toFixed(2)}</span>
      <div class="bar" title="graph ${s.graph}, coverage ${s.coverage}, semantic ${s.semantic}">
        <span class="g" style="width:${s.graph * 40}%"></span><span class="m" style="width:${s.coverage * 30}%"></span><span class="s" style="width:${s.semantic * 30}%"></span></div>
      <span class="small-print">${e.covers && e.covers.length ? "Linked to " + esc(e.covers.join(", ")) : "Ranked by document similarity"}</span></div>`;
  }).join("")}<p class="small-print">Bar: graph proximity (clay), coverage of the question's entities (olive), semantic similarity (grey).</p></div>`;
}

function renderRecs(recs) {
  if (!recs.length) return "";
  return `<div class="panel"><h2 class="h3">Recommended documents</h2>${recs.map((r) =>
    `<div class="similar"><div class="row"><span>${esc(r.title)}</span><span class="small-print">${r.score.toFixed(2)}</span></div></div>`).join("")}</div>`;
}

async function askQuestion(q) {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const btn = $("#ask-btn");
  btn.disabled = true; btn.textContent = "Thinking";
  $("#result").hidden = false;
  $("#answer").className = "answer loading";
  $("#answer").textContent = "Reading the graph and the documents…";
  for (const id of ["#experts", "#recs", "#sources", "#trace", "#meta"]) $(id).innerHTML = "";
  try {
    const r = await api("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, mode }) });
    $("#answer").className = "answer";
    $("#answer").innerHTML = render(r.answer);
    $("#meta").textContent = `${r.mode === "graph" ? "Graph-augmented" : "Passages only"} · ${r.intent} · ${r.latency_s}s · ${r.explanation.corrective_retries ? "query rewritten once" : "first retrieval accepted"}`;
    $("#experts").innerHTML = renderExperts(r.experts);
    $("#recs").innerHTML = renderRecs(r.recommendations);
    $("#sources").innerHTML = r.sources.map((s, i) =>
      `<li id="src-S${i + 1}"><b>S${i + 1}</b><span class="via">${s.via}</span> ${esc(s.text.slice(0, 260))}…</li>`).join("");
    $("#trace").innerHTML = r.trace.map((t) => `<li>${esc(t.step)}: ${esc(JSON.stringify(Object.fromEntries(Object.entries(t).filter(([k]) => !["step", "t"].includes(k)))))}</li>`).join("");
    const seeds = new Set((r.graph.nodes || []).filter((n) => n.hops === 0).map((n) => n.key));
    const path = new Set();
    const keyOf = Object.fromEntries((r.graph.nodes || []).map((n) => [n.name, n.key]));
    for (const f of r.explanation.reasoning_path || []) path.add(`${keyOf[f.source]}|${keyOf[f.target]}`);
    if (r.graph.nodes && r.graph.nodes.length) drawGraph($("#qgraph"), r.graph.nodes, r.graph.edges, { seeds, path });
    else $("#qgraph").innerHTML = '<p class="hint" style="padding:16px">Passages-only mode does not use the graph. Switch to graph-augmented to see it.</p>';
    $("#result").scrollIntoView({ block: "start" });
  } catch (e) {
    $("#answer").className = "answer error";
    $("#answer").textContent = `${e.message}. Check the server is running and try again.`;
  } finally {
    btn.disabled = false; btn.textContent = "Ask CRAG";
  }
}

$("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#q").value.trim(); if (q) askQuestion(q); });
$("#q").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#ask-form").requestSubmit(); } });
$("#suggest").addEventListener("click", (e) => { if (e.target.tagName === "BUTTON") { $("#q").value = e.target.textContent; $("#ask-form").requestSubmit(); } });
$("#answer").addEventListener("click", (e) => {
  const ref = e.target.dataset && e.target.dataset.ref;
  if (!ref || ref[0] !== "S") return;
  document.querySelectorAll(".sources li").forEach((li) => li.classList.remove("hl"));
  const li = document.getElementById(`src-${ref}`);
  if (li) { li.classList.add("hl"); li.scrollIntoView({ block: "nearest" }); }
});

async function loadExplore() {
  try {
    const [s, g] = await Promise.all([api("/api/stats"), api("/api/graph?limit=90")]);
    $("#stats").textContent = `${s.documents} documents, ${s.chunks} passages, ${s.entities} entities, ${s.relations} relations (${s.backend} backend)`;
    drawGraph($("#graph"), g.nodes, g.edges, { spread: 2.5, labelTop: 30 });  // nodes arrive sorted by degree
    $("#legend").innerHTML = Object.keys(TYPE_COLORS).map((t) => `<li><i style="background:${color(t)}"></i>${t}</li>`).join("");
  } catch (e) { $("#stats").textContent = `Could not load the graph: ${e.message}`; }
}

async function loadDocs() {
  try {
    const docs = await api("/api/documents");
    $("#doclist").innerHTML = docs.map((d) => `<li><button type="button" data-id="${esc(d.id)}" aria-pressed="false"><span>${esc(d.title)}</span><small>${d.ocr ? "OCR" : ""}</small></button></li>`).join("");
  } catch (e) { $("#doclist").innerHTML = `<li class="error">${esc(e.message)}</li>`; }
}

$("#doclist").addEventListener("click", async (e) => {
  const b = e.target.closest("button"); if (!b) return;
  document.querySelectorAll("#doclist button").forEach((x) => x.setAttribute("aria-pressed", x === b));
  $("#similar").innerHTML = '<p class="empty">Finding similar documents…</p>';
  try {
    const recs = await api(`/api/recommend?doc_id=${encodeURIComponent(b.dataset.id)}`);
    $("#similar").innerHTML = `<h3>Similar to ${esc(b.textContent.trim())}</h3>` + recs.map((r) =>
      `<div class="row"><span>${esc(r.title)}</span><span class="small-print">meaning ${r.semantic.toFixed(2)} · shared ${r.shared_entities.toFixed(2)}</span></div>`).join("");
  } catch (err) { $("#similar").innerHTML = `<p class="error">${esc(err.message)}</p>`; }
});

loadExplore();
loadDocs();
// Shareable questions: /?q=...&mode=vector opens the page and asks right away.
const params = new URLSearchParams(location.search);
if (["light", "dark"].includes(params.get("theme"))) document.documentElement.dataset.theme = params.get("theme");
if (params.get("q")) {
  $("#q").value = params.get("q");
  if (params.get("mode") === "vector") document.querySelector('input[value="vector"]').checked = true;
  askQuestion(params.get("q"));
}
