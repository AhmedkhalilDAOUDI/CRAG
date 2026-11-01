"""Builds the seven supervisor-meeting decks and the final defence presentation from real project data."""
import json
from collections import Counter
from pathlib import Path

from slides import Deck

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIG = HERE / "fig"
AUTHOR = "Daoudi Ahmed Khalil · MDSE · EHTP · 2025/2026"
SUP = "Supervisor: Dr. Abdelali El Bouchti"


def data():
    g = json.loads((ROOT / "data" / "index" / "graph.json").read_text())
    res = json.loads((ROOT / "data" / "eval" / "results.json").read_text())
    per_doc = Counter(c["doc_id"] for c in g["chunks"].values())
    types = Counter(e["type"] for e in g["entities"].values())
    rels = Counter(e["type"] for e in g["edges"])
    deg = Counter()
    for e in g["edges"]:
        deg[e["source"]] += 1
        deg[e["target"]] += 1
    return {"g": g, "res": res, "s": res["summary"], "per_doc": per_doc, "types": types, "rels": rels, "deg": deg,
            "n_docs": len(g["docs"]), "n_chunks": len(g["chunks"]), "n_ent": len(g["entities"]), "n_rel": len(g["edges"]),
            "ocr_docs": [d for d in g["docs"].values() if d.get("ocr")]}


def meeting(n, title, sub, week):
    d = Deck(f"Meeting {n} · CRAG · {AUTHOR}")
    d.cover(f"Meeting {n}: {title}", sub,
            [f"CRAG: Knowledge Graph + LLM platform · week {week}", AUTHOR, SUP],
            notes="Open by saying what was planned for this meeting and what is ready to show.")
    return d


def recap(d, done, today):
    d.two_col("Where we are", "Done so far", done, "Today", today,
              why="Each meeting shows one finished increment, so progress is visible and feedback lands before the next step.",
              notes="Thirty seconds: remind what was agreed last time, then announce today's content.")


def m1(D):
    d = meeting(1, "Subject, state of the art and plan", "Understanding the brief and the research behind it", 2)
    recap(d, ["Brief analysed", "22 research papers collected and read", "Work plan drafted"],
          ["What the platform must do", "Why classic RAG is not enough", "Graph-based RAG in the literature", "Plan and next steps"])
    d.points("The brief in one slide", [
        "Build an intelligent knowledge-management platform: a knowledge graph enriched by an LLM",
        "Collect company knowledge automatically, including scanned documents (OCR)",
        "Build the graph and identify relations between concepts",
        "Answer complex questions in natural language and explain answers from the graph",
        "Identify experts, recommend similar documents, visualise relations",
        "Technologies required: LLM, RAG, LangGraph, GraphRAG, OCR, Neo4j, Docker"],
        why="Every feature of CRAG maps to one line of this brief; nothing is added that the brief does not ask for.")
    d.table("Objectives", ["Id", "Objective", "How it will be met"], [
        ["O1", "Extract knowledge from documents", "pypdf + Tesseract OCR"],
        ["O2-O3", "Build the graph, find relations", "LLM extraction to JSON triples"],
        ["O4", "Answer complex questions", "LangGraph workflow, graph + vector retrieval"],
        ["O5", "Explain answers", "Cited graph facts form a reasoning path"],
        ["O6", "Identify experts", "Graph + coverage + semantic scoring"],
        ["O7", "Recommend documents", "Embedding similarity + shared entities"],
        ["O8", "Visualise relations", "Cytoscape.js graph in the web UI"],
        ["O9-O10", "Beat classic RAG; production-ready", "Benchmark vs baseline; Docker, tests, deploy"]],
        col_w=[1.2, 4.2, 6.5], size=13)
    d.points("What RAG is, and its limit", [
        "LLMs know nothing about private documents and can hallucinate",
        "RAG (Lewis et al., 2020): retrieve relevant passages, then generate the answer from them, with citations",
        "Limit: each passage is scored alone against the question",
        "  'Who knows both X and Y?' is similar to no single passage",
        "  Questions about people and relations need links between facts"],
        why="This limit is the research question of the project: does a knowledge graph fix it, and by how much?")
    d.points("Knowledge graphs and GraphRAG", [
        "Knowledge graph: entities (nodes) joined by typed relations (edges); each fact is a triple",
        "Multi-hop: follow edges (skill → person → project) to reach facts no passage states together",
        "GraphRAG (Edge et al., 2024): the LLM builds the graph, then retrieval uses it",
        "Lighter variants link the question to entities and expand: LightRAG, HippoRAG",
        "Corrective RAG (Yan et al., 2024): grade the evidence, retry when weak"],
        why="CRAG will combine these: entity linking and expansion, fused with vector search, plus a corrective step.")
    d.chart("Research papers collected, by theme", ["RAG foundations", "KG and GraphRAG", "Corrective / agentic", "Embeddings and models", "Evaluation"],
            {"papers": [4, 9, 4, 4, 1]}, kind="pie",
            side_text=["22 papers from arXiv, checked by title", "Indexed in RESEARCH PAPERS/README.md", "Core five: Lewis 2020, Edge 2024, Pan 2024, Hogan 2021, Yan 2024"],
            why="The state-of-the-art chapter of the report is built on these papers.")
    d.image("Planning", FIG / "gantt.png", "Seven phases over about 17 weeks; dotted lines are our meetings",
            why="Each meeting closes one phase, so the work can be validated step by step.")
    d.points("Next steps and questions", [
        "Next meeting: architecture, data model and technology choices",
        "Question: no company documents are available; validate on a public test corpus only?",
        "Question: priority between expert finding and question answering?"],
        notes="Ask the supervisor these questions explicitly and write down the answers.")
    d.save(D / "Meeting_1_Subject_and_State_of_the_Art.pptx")


def m2(D, x):
    d = meeting(2, "Architecture and design", "How CRAG is organised, and why", 4)
    recap(d, ["Brief, objectives, state of the art", "Plan validated"],
          ["Requirements", "Architecture: two pipelines, one store", "Graph data model", "Technology and model choices"])
    d.table("Requirements", ["Functional", "Non-functional"], [
        ["Ingest PDF, text, images (OCR)", "Answers in a few seconds"],
        ["Extract entities and relations", "One failure never stops a run"],
        ["Answer with citations", "Secrets outside the code"],
        ["Explain with a graph path", "Same code: laptop, Docker, serverless"],
        ["Rank experts, recommend documents", "Automated tests without network"],
        ["Compare with classic RAG", "Every claim cited"]], col_w=[5.95, 5.95], size=14)
    d.image("Architecture: two pipelines around one knowledge store", FIG / "workflow.png",
            why="Ingestion is slow and done once; questions are fast and frequent. Separating them keeps answers quick.")
    d.image("Graph data model", FIG / "data_model.png", max_h=3.9,
            why="Passages and graph live in one database, so a passage can be followed to the entities it mentions and back.")
    d.table("Technology choices", ["Need", "Choice", "Reason"], [
        ["Chat model", "Nemotron 3.5 Lightning 30B-A3B", "Fast MoE (~3B active), clean JSON"],
        ["Embeddings", "Nemotron 3.5 Embed 1B (2,048-d)", "Query/passage modes"],
        ["Graph + vectors", "Neo4j 5", "Cypher + native vector index"],
        ["Workflow", "LangGraph", "Explicit steps, loops, trace"],
        ["OCR", "Tesseract 5", "Local, open source"],
        ["API / UI", "FastAPI, HTML + Cytoscape.js", "Validation, simple front end"],
        ["Deploy", "Docker Compose, Vercel", "Reproducible + public demo"]], col_w=[2.4, 4.6, 4.9], size=13)
    d.table("Choosing the models: what we tested", ["Model", "Type", "Result on the API"], [
        ["meta/llama-3.3-70b-instruct", "Chat", "Retired (HTTP 410)"],
        ["nvidia/nemotron-3-super-120b", "Chat", "Not available to this key (404)"],
        ["nvidia/nemotron-3.5-lightning-30b-a3b", "Chat", "OK, 0.66 s, valid JSON  →  chosen"],
        ["nvidia/nv-embedqa-e5-v5", "Embedding", "Retired (HTTP 410)"],
        ["nvidia/nemotron-3.5-embed-1b", "Embedding", "OK, 2,048 dimensions  →  chosen"]], col_w=[5.0, 2.0, 4.9], size=14,
            why="Testing before coding avoided building on models that no longer exist.")
    d.points("Next steps", ["Implement ingestion: reading, OCR, chunking, extraction", "Prepare a test corpus (no company data available)",
                            "Next meeting: the ingestion pipeline running on real files"])
    d.save(D / "Meeting_2_Architecture_and_Design.pptx")


def m3(D, x):
    d = meeting(3, "The ingestion pipeline", "From files to entities and relations", 6)
    recap(d, ["Architecture and data model", "Models selected and tested"],
          ["Reading and OCR", "Chunking", "LLM extraction and its validation", "First graph statistics"])
    d.points("Pipeline steps", [
        "Read: pypdf text layer; if under 20 characters per page, render (pypdfium2) and OCR (Tesseract)",
        "Clean: collapse whitespace and blank lines",
        "Chunk: sentences packed into ≤ 1,200 characters, 200 characters of overlap",
        "Extract: one LLM call per chunk → entities (10 types) and relations as JSON",
        "Resolve: normalised names merge spelling variants",
        "Embed and store: chunks and entities as 2,048-d vectors"],
        why="Each step is small and testable; only extraction and embedding call the model.")
    d.points("Test corpus (validation only)", [
        f"{x['n_docs']} documents: 36 born-digital PDFs + 2 scanned images, 6 professional domains",
        "Public, anonymised profiles: rich in people, skills, roles, tools and projects",
        f"OCR: both scanned documents read automatically ({', '.join(str(dd['chars']) for dd in x['ocr_docs'])} characters)",
        "Used only to test and evaluate; not company data, not part of the report"],
        why="Profiles contain exactly the knowledge expert finding needs, so they are a fair stand-in for company documents.")
    hist = Counter(min(v, 14) for v in x["per_doc"].values())
    cats = [str(k) if k < 14 else "14+" for k in sorted(hist)]
    d.chart("Chunks per document", cats, {"documents": [hist[k] for k in sorted(hist)]}, number_format="0",
            side_text=[f"{x['n_chunks']} chunks in total", f"Mean {x['n_chunks'] / x['n_docs']:.1f} per document",
                       "Chunk ≈ 250-300 tokens: precise embedding, precise citation"],
            why="Small, overlapping chunks make retrieval precise without cutting facts in half.")
    d.points("Extraction prompt (summary)", [
        "Role: you build an enterprise knowledge graph",
        "Allowed entity types: Person, Organization, Skill, Technology, Concept, Project, Procedure, Role, Certification, Location",
        "Relations: UPPER_SNAKE_CASE verbs (HAS_SKILL, WORKED_AT, USES...); both ends must be listed entities",
        "Canonical names; at most 15 entities; ignore placeholders",
        "Temperature 0, reasoning off, 4 chunks in parallel"],
        why="A strict schema makes the output parse-able and the graph consistent.")
    d.two_col("A problem found and fixed", "What happened", [
        "The test documents are anonymised: 'Company Name', 'City'",
        "The model extracted these placeholders despite the instruction",
        "'Company Name' became a hub linked to every employee"],
        "The fix", ["Validation in code: placeholder stop-list", "Also: unknown types → Concept; dangling relations dropped",
                    "Lesson: never trust model output without checks"],
        why="Without the fix, graph expansion would return everyone for every question.")
    items = sorted(x["types"].items(), key=lambda kv: -kv[1])
    d.chart("Entities extracted, by type", [k for k, _ in items], {"entities": [v for _, v in items]}, number_format="0",
            why=f"{x['n_ent']} entities and {x['n_rel']} relations from {x['n_docs']} documents: skills, concepts and technologies dominate, as expected.")
    top = x["rels"].most_common(10)
    d.chart("Most frequent relation types", [k for k, _ in top][::-1], {"relations": [v for _, v in top][::-1]}, kind="hbar",
            number_format="0", why="A few verbs (HAS_SKILL, WORKED_AT...) carry most facts; this is what expert finding relies on.")
    d.points("Next steps", ["Store the graph in Neo4j and in a portable snapshot", "Implement graph-augmented retrieval",
                            "Next meeting: the knowledge graph and how questions use it"])
    d.save(D / "Meeting_3_Ingestion_Pipeline.pptx")


def m4(D, x):
    d = meeting(4, "The knowledge graph and retrieval", "Storing the graph and using it to find evidence", 9)
    recap(d, ["Ingestion pipeline running", f"Graph: {x['n_ent']} entities, {x['n_rel']} relations"],
          ["Two storage backends", "Vector search", "Entity linking and 2-hop expansion", "Rank fusion"])
    d.two_col("Two backends, one interface", "Neo4j (production)", [
        "Property graph queried with Cypher", "HNSW vector indexes on chunks and entities", "Constraints + MERGE: idempotent writes",
        "Runs in Docker"], "Memory snapshot (demo, tests)", [
        "NetworkX graph + NumPy vectors", "Two files: graph.json, vectors.npz (float16)", "Serverless-friendly, tests in 1 second",
        "Copied into Neo4j in about 40 s, no LLM calls"],
        why="Extraction is the expensive step; it is done once and reused by both backends.")
    hubs = [(x["g"]["entities"][k]["name"], v) for k, v in x["deg"].most_common(12)]
    d.chart("Most connected entities (degree)", [h[0][:28] for h in hubs][::-1], {"relations": [h[1] for h in hubs][::-1]},
            kind="hbar", number_format="0",
            why="Employees and common skills are the hubs; expansion is capped at 60 entities so hubs do not flood the context.")
    d.points("Retrieval: five steps", [
        "1. Vector ranking: embed the question, take the 18 nearest chunks",
        "2. Entity linking: exact names + nearest entity vectors (cosine ≥ 0.35) → seeds",
        "3. Expansion: everything within 2 hops of the seeds → facts",
        "4. Graph ranking: chunks mentioning the seeds and their neighbours",
        "5. Fusion: Reciprocal Rank Fusion → 6 chunks + 25 facts"],
        why="Two independent views of relevance: meaning (vectors) and structure (graph).")
    d.chart("Reciprocal Rank Fusion: a worked example", ["Chunk A (1st in vectors only)", "Chunk B (3rd in both lists)"],
            {"RRF score": [1 / 61, 2 / 63]}, number_format="0.0000",
            side_text=["RRF = Σ 1 / (60 + rank)", "A: 1/61 = 0.0164", "B: 1/63 + 1/63 = 0.0317", "Agreement between lists wins"],
            why="RRF uses ranks only, so cosine scores and mention counts never need to be calibrated against each other.")
    d.points("Why 2 hops", ["1 hop misses chains like skill → person → other skill",
                            "3 hops in a dense graph reaches almost everything: noise",
                            "2 hops, capped at 60 entities, closest first"])
    d.points("Next steps", ["Wrap retrieval in a LangGraph workflow with a corrective loop",
                            "Add expert ranking, recommendations and explanations",
                            "Next meeting: the full question-answering workflow"])
    d.save(D / "Meeting_4_Knowledge_Graph_and_Retrieval.pptx")


def m5(D, x):
    d = meeting(5, "The question-answering workflow", "LangGraph, experts, recommendations, explanations", 11)
    recap(d, ["Graph stored in Neo4j and snapshot", "Hybrid retrieval with RRF"],
          ["The LangGraph state machine", "Corrective loop", "Expert ranking", "Recommendations and explanations"])
    d.points("The workflow as a state machine", [
        "analyze → retrieve → grade → (retry once) → experts | recommend | generate → explain",
        "analyze: the LLM returns the intent (qa, experts, recommend) and key entities",
        "grade: the LLM judges if the evidence suffices; if not, rewrites the query",
        "generate: answer citing passages [S#] and graph facts [F#]",
        "explain: cited facts become the reasoning path (no extra model call)",
        "vector mode = classic RAG baseline: same models, graph steps off"],
        why="A fixed workflow is predictable in cost and easy to evaluate; the trace shows every step.")
    d.chart("Expert score = 0.4 graph + 0.3 coverage + 0.3 semantic", ["Person P", "Person Q"],
            {"graph (×0.4)": [0.4, 0.08], "coverage (×0.3)": [0.15, 0.3], "semantic (×0.3)": [0.24, 0.27]},
            side_text=["P: 0.40 + 0.15 + 0.24 = 0.79", "Q: 0.08 + 0.30 + 0.27 = 0.65",
                       "Coverage = how many of the question's entities the person is linked to"],
            why="Combining the graph view with the document view is the classic expert-finding idea (Balog et al., 2006).")
    d.two_col("Improvements made after the first tests", "Observed", [
        "Expert answers cited no graph fact",
        "'Who knows X and Y?' missed a person with both",
        "Extraction keeps ≤ 15 entities per chunk: long skill lists lose some"],
        "Changed", ["Evidence passed as citable [F#] markers", "Coverage of distinct question entities in the score",
                    "Lexical fallback: entity names found in the person's passages"],
        why="Each fix came from inspecting real outputs, not from guessing.")
    d.image("The answer view", FIG / "ui_answer.png", max_h=4.2,
            why="Citations, ranked experts with their score breakdown, the reasoning graph and the sources, on one screen.")
    d.points("Recommendations", ["Score = 0.7 × semantic similarity + 0.3 × Jaccard of shared entities",
                                 "From a question, or from a document ('find similar')",
                                 "Jaccard({SQL, Python, ETL}, {SQL, ETL, Tableau}) = 2/4 = 0.5"])
    d.points("Next steps", ["REST API, security, web interface", "Docker packaging and public deployment",
                            "Next meeting: the platform as a product"])
    d.save(D / "Meeting_5_Question_Answering_Workflow.pptx")


def m6(D, x):
    d = meeting(6, "Interface, API, security and deployment", "Making CRAG a usable, production-ready product", 13)
    recap(d, ["Full workflow: answers, experts, recommendations, explanations"],
          ["Web interface", "REST API", "Security and tests", "Docker, GitHub and public deployment"])
    d.image("Web interface: the knowledge graph", FIG / "ui_graph.png", max_h=4.1,
            why="Users see the most connected entities; each answer also shows its own neighbourhood and cited path.")
    d.table("REST API", ["Method", "Route", "Purpose"], [
        ["GET", "/api/health, /api/stats", "Status and graph size"],
        ["POST", "/api/ask", "Answer (mode graph or vector) with sources, facts, trace"],
        ["GET", "/api/experts?topic=", "Ranked experts"],
        ["GET", "/api/recommend?doc_id=", "Similar documents"],
        ["GET", "/api/graph, /api/documents", "Graph view, document list"],
        ["POST", "/api/ingest", "Upload (administrator token)"]], col_w=[1.4, 4.0, 6.5], size=14)
    d.table("Security measures", ["Risk", "Measure"], [
        ["Leaked secrets", "Environment variables; .env never committed"],
        ["Unauthorised uploads", "Admin token; read-only mode in public"],
        ["Malicious files", "Type allow-list, 20 MB cap, temp directory"],
        ["Abuse and cost", "20 model requests / minute / IP"],
        ["Script injection", "All document and model text escaped"],
        ["Container privileges", "Non-root user, health check"]], col_w=[3.6, 8.3], size=14)
    d.chart("Automated tests", ["Ingestion", "Store", "Rank fusion", "Workflow", "API"],
            {"tests": [4, 3, 1, 2, 1]}, number_format="0",
            side_text=["11 tests, all passing", "Fake models: offline, deterministic, ~1 s", "Neo4j backend checked on the real graph"],
            why="Tests that need no network can run on every change.")
    d.points("Deployment", ["Production: docker compose up → Neo4j + API on port 8080",
                            "Public demo: Vercel serverless, read-only snapshot",
                            "Code, diagrams and documentation on GitHub", "API key only in encrypted host settings"],
             why="The same code runs in all three places; only environment variables change.")
    d.points("Next steps", ["Benchmark CRAG against classic RAG", "Write the report and prepare the defence",
                            "Next meeting: evaluation results"])
    d.save(D / "Meeting_6_Interface_API_Deployment.pptx")


def results_slides(d, x, why_main, why_quality):
    s = x["s"]
    d.table("Evaluation protocol", ["Benchmark", "Questions", "Gold label", "Metric"], [
        ["Expert finding", str(s["experts"]["n"]), "Profile's domain", "Precision@5"],
        ["Single-hop QA", str(s["single_hop"]["graph"]["n"]), "Source passage's document", "Hit rate, judged quality"],
        ["Relational QA", str(s["relational"]["graph"]["n"]), "The one employee with both facts", "Exact match, hit rate"]],
        col_w=[2.6, 1.6, 4.2, 3.5], size=14,
        why="Baseline = same models, chunks and prompts with the graph steps off: only the graph differs.")
    d.chart("CRAG versus classic RAG", ["Expert P@5", "Single-hop hit", "Relational hit", "Relational exact"], {
        "CRAG": [s["experts"]["crag_p5"], s["single_hop"]["graph"]["hit_rate"], s["relational"]["graph"]["hit_rate"],
                 s["relational"]["graph"]["exact_match"]],
        "Classic RAG": [s["experts"]["baseline_p5"], s["single_hop"]["vector"]["hit_rate"], s["relational"]["vector"]["hit_rate"],
                        s["relational"]["vector"]["exact_match"]]}, y_max=1.1, why=why_main)
    d.chart("Answer quality and latency (single-hop)", ["Correctness (1-5)", "Faithfulness (1-5)", "Latency (s)"], {
        "CRAG": [s["single_hop"]["graph"]["correctness"], s["single_hop"]["graph"]["faithfulness"], s["single_hop"]["graph"]["latency_mean_s"]],
        "Classic RAG": [s["single_hop"]["vector"]["correctness"], s["single_hop"]["vector"]["faithfulness"], s["single_hop"]["vector"]["latency_mean_s"]]},
        why=why_quality)


def m7(D, x, why_main, why_quality, limits):
    d = meeting(7, "Evaluation and conclusions", "Does the graph make CRAG better than classic RAG?", 15)
    recap(d, ["Platform complete, tested and deployed"], ["Evaluation protocol and results", "Limits", "Report and defence plan"])
    results_slides(d, x, why_main, why_quality)
    d.points("Limits, stated honestly", limits)
    d.points("Report and defence", ["Report: 5 chapters + abstract (EN/FR), state of the art, design, implementation, evaluation",
                                    "Defence deck, jury Q&A prepared, live demo in both modes",
                                    "Improvement roadmap: OTHER_IDEAS.md (37 ideas)"])
    d.save(D / "Meeting_7_Evaluation_and_Conclusions.pptx")


def final(path, x, why_main, why_quality, limits, conclusion):
    d = Deck(f"CRAG · {AUTHOR}")
    d.cover("CRAG: a knowledge-graph-augmented LLM platform for enterprise knowledge",
            "Final-year project (PFE) · Master in Data Science and Engineering",
            ["Daoudi Ahmed Khalil", SUP, "Ecole Hassania des Travaux Publics · 2025/2026"],
            notes="Good morning. I will present CRAG, a platform that turns company documents into a knowledge graph and answers questions with it.")
    d.points("Outline", ["Context and problem", "State of the art", "Design of CRAG", "Implementation and demo",
                         "Evaluation", "Conclusion and perspectives"])
    d.section(1, "Context and problem", "Company knowledge is scattered; relations between facts are what matter")
    d.points("The problem", [
        "Knowledge is spread over thousands of documents; tacit knowledge sits with people",
        "Keyword search returns documents, not answers",
        "Classic RAG answers from passages scored one by one",
        "  It fails on relations ('who knows X and Y?') and on people ('who is the expert?')",
        "Research question: can an LLM-built knowledge graph, fused with semantic retrieval, do better, and explain itself?"],
        why="The value lies in the links between facts, which no single passage contains.")
    d.table("Objectives from the brief", ["Objective", "In CRAG"], [
        ["Collect knowledge, incl. scanned documents", "pypdf + Tesseract OCR"],
        ["Build the graph, find relations", "LLM extraction → Neo4j"],
        ["Answer complex questions", "LangGraph workflow, hybrid retrieval"],
        ["Explain answers from the graph", "Cited reasoning path"],
        ["Identify experts / recommend documents", "Hybrid scoring"],
        ["Visualise relations", "Interactive graph"],
        ["Better than classic RAG, production-ready", "Benchmark; Docker, tests, deployment"]], col_w=[6.2, 5.7], size=14)
    d.section(2, "State of the art", "RAG, knowledge graphs, GraphRAG")
    d.points("From RAG to GraphRAG", [
        "RAG (Lewis 2020): retrieve, then generate from the passages",
        "Knowledge graphs (Hogan 2021): entities, typed relations, multi-hop",
        "GraphRAG (Edge 2024): LLM-built graph + community summaries; costly",
        "LightRAG, HippoRAG (2024): link the question to entities, expand",
        "Corrective RAG (Yan 2024): grade the evidence, retry",
        "CRAG combines linking + expansion + vector fusion + correction, in one database"])
    d.image("Positioning", FIG / "positioning.png", max_h=4.0,
            why="CRAG aims at strong relational reasoning without the indexing cost of community summaries.")
    d.section(3, "Design", "Two pipelines, one knowledge store")
    d.image("Architecture", FIG / "workflow.png", why="Ingestion builds the graph once; every question reads it.")
    d.image("Who does what", FIG / "pipeline_roles.png", max_h=4.6,
            notes="Point out the three colours: you, a tool, the model. Only extraction, embedding, analysis, grading and generation call the model.")
    d.image("Graph data model", FIG / "data_model.png", max_h=3.9)
    d.points("Key design decisions", [
        "Graph and vectors in one database (Neo4j vector index)",
        "Reciprocal Rank Fusion of vector and graph rankings: no score calibration",
        "Corrective step: grade, rewrite, retry once",
        "Explanation extracted from the citations: faithful and free",
        "Experts: 0.4 graph proximity + 0.3 coverage + 0.3 semantic similarity"])
    d.section(4, "Implementation", "From files to cited answers")
    d.points("Ingestion", [
        "OCR when a PDF has under 20 characters per page; 2/2 scanned documents read",
        "Chunks ≤ 1,200 characters, 200 overlap",
        "Nemotron 3.5 Lightning extracts entities (10 types) and relations as JSON",
        "Validation in code: placeholders and dangling relations removed",
        f"Test graph: {x['n_ent']} entities, {x['n_rel']} relations from {x['n_docs']} documents"])
    items = sorted(x["types"].items(), key=lambda kv: -kv[1])
    d.chart("Entities by type", [k for k, _ in items], {"entities": [v for _, v in items]}, number_format="0")
    d.image("Demo: an expert question", FIG / "ui_answer.png", max_h=4.3,
            notes="Live demo: ask the same question in graph mode and in passages-only mode and compare.")
    d.image("The knowledge graph explorer", FIG / "ui_graph.png", max_h=4.3)
    d.points("Production readiness", ["Docker Compose: Neo4j + API, health checks, non-root",
                                      "Validation, admin token, rate limits, escaping", "11 automated tests, offline",
                                      "Public read-only demo on Vercel; code on GitHub"])
    d.section(5, "Evaluation", "CRAG versus classic RAG, same models")
    results_slides(d, x, why_main, why_quality)
    d.points("Limits", limits)
    d.section(6, "Conclusion", "")
    d.points("Conclusion", conclusion)
    d.points("Perspectives", ["Pilot on real company documents, with access control and self-hosted models",
                              "Better extraction: fixed ontology, synonym merging, provenance on every fact",
                              "Better retrieval: BM25, re-ranking, Personalised PageRank, text-to-Cypher",
                              "Larger, human-labelled evaluation with ablations"])
    d.quote("Thank you.", "Questions are welcome. The platform can be demonstrated live.")
    d.save(path)
