"""Query-time reasoning as a LangGraph state machine.

analyze -> retrieve -> grade --(insufficient, once)--> retrieve
                           \\-> experts | recommend | (qa) -> generate -> explain
mode="vector" disables the graph steps and the corrective loop: that is the classic-RAG baseline.
"""
import re
import time
from collections import defaultdict
from typing import TypedDict

from langgraph.graph import END, StateGraph

from . import llm
from .config import settings
from .ingest import norm
from .store import get_store

RRF_K = 60            # Reciprocal Rank Fusion constant (Cormack et al., 2009)
ENTITY_MIN_SIM = 0.35  # below this cosine, a query->entity link is treated as noise
VECTOR_KEEP = 3        # top semantic passages always kept after fusion


class State(TypedDict, total=False):
    question: str
    mode: str            # "graph" (CRAG) or "vector" (baseline)
    intent: str          # qa | experts | recommend
    keywords: list
    query: str
    attempts: int
    qvec: object
    seeds: list
    chunks: list
    facts: list
    graph: dict
    experts: list
    recommendations: list
    answer: str
    explanation: dict
    trace: list
    retry: bool


def _log(state, step, **info):
    state.setdefault("trace", []).append({"step": step, "t": round(time.time(), 3), **info})


# ---------- nodes ------------------------------------------------------------------------------

ANALYZE_SYSTEM = """Classify an enterprise knowledge question. Return JSON:
{"intent": "qa" | "experts" | "recommend", "entities": ["key names, skills, technologies, topics in the question"]}
intent=experts when the user asks about people: who knows / who is expert / who can help / which employee or
person has, did or is associated with something.
intent=recommend when the user asks for similar or relevant documents, procedures, projects or profiles.
Otherwise intent=qa."""


def analyze(state: State) -> State:
    try:
        out = llm.chat_json(ANALYZE_SYSTEM, state["question"], max_tokens=300)
    except Exception:
        out = {}
    intent = out.get("intent") if out.get("intent") in ("qa", "experts", "recommend") else "qa"
    state.update(intent=intent, keywords=[k for k in out.get("entities", []) if isinstance(k, str)],
                 query=state["question"], attempts=0)
    _log(state, "analyze", intent=intent, keywords=state["keywords"])
    return state


def _rrf(*rankings):
    score = defaultdict(float)
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            score[cid] += 1 / (RRF_K + rank + 1)
    return score


def retrieve(state: State) -> State:
    store, k = get_store(), settings.top_k
    qvec = llm.embed([state["query"]], "query")[0]
    vec_hits = store.search_chunks(qvec, 3 * k)
    by_id = {c["id"]: (c, s) for c, s in vec_hits}
    state["qvec"] = qvec
    if state.get("mode") == "vector":
        state.update(chunks=[{**c, "score": s, "via": "vector"} for c, s in vec_hits[:k]], facts=[], seeds=[],
                     graph={"nodes": [], "edges": []})
        _log(state, "retrieve", mode="vector", chunks=len(state["chunks"]))
        return state

    # 1) Entity linking: exact names from the question + nearest entities in embedding space.
    seeds = {e["key"]: e for e in store.entities_by_name([norm(x) for x in state.get("keywords", [])])}
    for e, s in store.search_entities(qvec, 8):
        if s >= ENTITY_MIN_SIM:
            seeds.setdefault(e["key"], e)
    # 2) Graph expansion: multi-hop neighbourhood of the seeds -> relational facts.
    nodes, edges = store.neighborhood(list(seeds), settings.graph_hops)
    names = {n["key"]: n["name"] for n in nodes}
    # 3) Graph-side chunk ranking: passages mentioning many seed/neighbour entities.
    near = list(seeds) + [n["key"] for n in nodes if n.get("hops", 9) <= 1]
    graph_hits = store.chunks_for_entities(near, 3 * k)
    for c, _ in graph_hits:
        by_id.setdefault(c["id"], (c, 0.0))
    # 4) Fusion of the two rankings.
    fused = _rrf([c["id"] for c, _ in vec_hits], [c["id"] for c, _ in graph_hits])
    graph_ids = {c["id"] for c, _ in graph_hits}
    vec_ids = {c["id"] for c, _ in vec_hits}
    # The best semantic hits are always kept: the graph adds evidence, it never displaces it.
    keep = [c["id"] for c, _ in vec_hits[:VECTOR_KEEP]]
    top = keep + [cid for cid in sorted(fused, key=lambda cid: -fused[cid]) if cid not in keep][: k - len(keep)]
    prev = {c["id"]: c for c in state.get("chunks", [])}  # keep evidence found by an earlier attempt
    chunks = [{**by_id[cid][0], "score": round(fused[cid], 5),
               "via": "both" if cid in graph_ids and cid in vec_ids else ("graph" if cid in graph_ids else "vector")}
              for cid in top]
    chunks += [c for cid, c in prev.items() if cid not in top][: max(0, k - 2)]
    facts = [{"source": names.get(e["source"], e["source"]), "type": e["type"],
              "target": names.get(e["target"], e["target"]), "description": e.get("description", ""),
              "source_key": e["source"], "target_key": e["target"]} for e in edges]
    # Facts touching a seed first: they are the most relevant to the question.
    facts.sort(key=lambda f: -((f["source_key"] in seeds) + (f["target_key"] in seeds)))
    state.update(seeds=list(seeds.values()), chunks=chunks, facts=facts[:25],
                 graph={"nodes": nodes, "edges": edges})
    _log(state, "retrieve", mode="graph", seeds=[s["name"] for s in seeds.values()], chunks=len(chunks),
         facts=len(facts), attempt=state.get("attempts", 0))
    return state


GRADE_SYSTEM = """You check whether retrieved context is enough to answer a question.
Return JSON: {"sufficient": true|false, "better_query": "a reformulated search query if not sufficient"}"""


def grade(state: State) -> State:
    ctx = "\n".join(c["text"][:400] for c in state["chunks"][:4])
    ctx += "\n" + "\n".join(f"{f['source']} -{f['type']}-> {f['target']}" for f in state["facts"][:12])
    try:
        out = llm.chat_json(GRADE_SYSTEM, f"QUESTION: {state['question']}\n\nCONTEXT:\n{ctx}", max_tokens=200)
    except Exception:
        out = {"sufficient": True}
    sufficient = bool(out.get("sufficient", True))
    state["attempts"] = state.get("attempts", 0) + 1
    if not sufficient and out.get("better_query"):
        state["query"] = out["better_query"]
    state["retry"] = not sufficient and state["attempts"] < 2
    _log(state, "grade", sufficient=sufficient, query=state["query"])
    return state


def experts(state: State) -> State:
    """Rank Person entities by graph evidence, coverage of the question's entities, and semantic similarity."""
    store = get_store()
    authors = store.authors
    seeds = {s["key"]: s["name"] for s in state["seeds"]}
    persons = {n["key"]: n["name"] for n in state["graph"]["nodes"] if n["type"] == "Person"}
    graph_s, vector_s = defaultdict(float), defaultdict(float)
    covered = defaultdict(set)  # person -> seed entities they are linked to (graph edge or own documents)
    evidence = defaultdict(list)
    near = {n["key"] for n in state["graph"]["nodes"] if n.get("hops") == 1}
    # Graph evidence = relations to the question's entities (1.0) or to their direct neighbours (0.25).
    # Counting all of a person's relations would favour people with long documents (degree bias).
    for e in state["graph"]["edges"]:
        for p, other in ((e["source"], e["target"]), (e["target"], e["source"])):
            if p in persons:
                if other in seeds:
                    graph_s[p] += 1.0
                    covered[p].add(other)
                elif other in near:
                    graph_s[p] += 0.25
    for i, f in enumerate(state["facts"]):  # cite-able evidence: the numbered facts shown to the model
        for p in (f["source_key"], f["target_key"]):
            if p in persons:
                evidence[p].append(f"[F{i + 1}] {f['source']} {f['type']} {f['target']}")
    for c, _ in store.chunks_for_entities(list(seeds), 80):
        if (p := authors.get(c["doc_id"])):
            covered[p] |= set(c["entities"]) & set(seeds)
    for c, s in store.search_chunks(state["qvec"], 40):
        if (p := authors.get(c["doc_id"])):
            vector_s[p] = max(vector_s[p], s)
            # Lexical fallback: extraction keeps <= 15 entities per chunk, so long skill lists lose some.
            text = f" {norm(c['text'])} "
            covered[p] |= {k for k in seeds if f" {k} " in text}
    coverage = {p: len(ks) for p, ks in covered.items()}
    names = {e["key"]: e["name"] for e in store.entities_by_name(list(set(authors.values())))} | persons

    def scaled(d):
        m = max(d.values(), default=0) or 1
        return {k: v / m for k, v in d.items()}

    g, m, v = scaled(graph_s), scaled(coverage), scaled(vector_s)
    score = {p: 0.4 * g.get(p, 0) + 0.3 * m.get(p, 0) + 0.3 * v.get(p, 0) for p in set(g) | set(m) | set(v)}
    ranked = sorted(score, key=lambda p: -score[p])[:5]
    state["experts"] = [{"key": p, "name": names.get(p, p), "score": round(score[p], 3),
                         "signals": {"graph": round(g.get(p, 0), 3), "coverage": round(m.get(p, 0), 3),
                                     "semantic": round(v.get(p, 0), 3)},
                         "covers": sorted(seeds[k] for k in covered[p]),
                         "documents": [d for d, a in authors.items() if a == p],
                         "evidence": evidence[p][:4]} for p in ranked]
    _log(state, "experts", ranked=[e["name"] for e in state["experts"]])
    return state


def recommend_documents(store, qvec, entity_keys, exclude=None, k=5):
    """Hybrid document similarity: 0.7 x embedding similarity + 0.3 x Jaccard overlap of graph entities."""
    vec = {}
    for c, s in store.search_chunks(qvec, 40):
        vec[c["doc_id"]] = max(vec.get(c["doc_id"], -1), s)
    ents = set(entity_keys)
    docs = {d["id"]: d for d in store.documents()}
    out = []
    for d in vec:
        if d == exclude or d not in docs:
            continue
        de = store.doc_entities(d)
        jac = len(ents & de) / len(ents | de) if ents | de else 0
        out.append({"doc_id": d, "title": docs[d].get("title", d), "score": round(0.7 * vec[d] + 0.3 * jac, 4),
                    "semantic": round(vec[d], 4), "shared_entities": round(jac, 4)})
    return sorted(out, key=lambda x: -x["score"])[:k]


def recommend(state: State) -> State:
    keys = [s["key"] for s in state["seeds"]] + [n["key"] for n in state["graph"]["nodes"]]
    state["recommendations"] = recommend_documents(get_store(), state["qvec"], keys)
    _log(state, "recommend", docs=[r["title"] for r in state["recommendations"]])
    return state


ANSWER_SYSTEM = """You are CRAG, an enterprise knowledge assistant. Answer ONLY from the provided sources
[S#] (document passages) and graph facts [F#] (relations from the knowledge graph).
Cite every claim with its marker in square brackets, e.g. [S2] or [F4]. Graph facts are a partial view;
passages are the full text, so check both before concluding something is absent. When a ranked list of
people is given, use it and cite the [F#] markers in their evidence. When the context does not contain
the answer, say so plainly. Be concise and structured. Answer in the language of the question."""


def generate(state: State) -> State:
    store = get_store()
    authors = store.authors
    subjects = {e["key"]: e["name"] for e in store.entities_by_name(list({authors[c["doc_id"]] for c in state["chunks"]
                                                                          if c["doc_id"] in authors}))}
    src = "\n\n".join(f"[S{i + 1}] (doc {c['doc_id']}"
                       + (f", about {subjects[authors[c['doc_id']]]}" if authors.get(c["doc_id"]) in subjects else "")
                       + f") {c['text']}" for i, c in enumerate(state["chunks"]))
    facts = "\n".join(f"[F{i + 1}] {f['source']} -{f['type']}-> {f['target']}" for i, f in enumerate(state["facts"]))
    extra = ""
    if state.get("experts"):
        extra = "\nRANKED EXPERTS (computed from the graph):\n" + "\n".join(
            f"- {e['name']} (score {e['score']}; linked to: {', '.join(e['covers']) or 'none'}; "
            f"evidence: {'; '.join(e['evidence']) or 'document similarity only'})"
            for e in state["experts"])
    if state.get("recommendations"):
        extra = "\nRECOMMENDED DOCUMENTS:\n" + "\n".join(
            f"- {r['title']} (doc {r['doc_id']}, score {r['score']})" for r in state["recommendations"])
    user = f"QUESTION: {state['question']}\n\nSOURCES:\n{src}\n\nGRAPH FACTS:\n{facts or '(none)'}\n{extra}"
    state["answer"] = llm.chat([{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": user}],
                               max_tokens=900)
    _log(state, "generate", chars=len(state["answer"]))
    return state


def explain(state: State) -> State:
    """Deterministic explanation: which graph facts and passages the answer actually cited."""
    cited_s = sorted({int(x) for x in re.findall(r"\[S(\d+)\]", state["answer"])})
    cited_f = sorted({int(x) for x in re.findall(r"\[F(\d+)\]", state["answer"])})
    state["explanation"] = {
        "seed_entities": [s["name"] for s in state.get("seeds", [])],
        "reasoning_path": [state["facts"][i - 1] for i in cited_f if 0 < i <= len(state["facts"])],
        "sources": [{"marker": f"S{i}", "doc_id": state["chunks"][i - 1]["doc_id"],
                     "via": state["chunks"][i - 1]["via"], "excerpt": state["chunks"][i - 1]["text"][:300]}
                    for i in cited_s if 0 < i <= len(state["chunks"])],
        "corrective_retries": max(0, state.get("attempts", 1) - 1),
    }
    _log(state, "explain", cited_sources=len(cited_s), cited_facts=len(cited_f))
    return state


# ---------- graph wiring -----------------------------------------------------------------------

def _after_grade(state: State) -> str:
    if state.get("retry"):
        return "retrieve"
    return {"experts": "experts", "recommend": "recommend"}.get(state["intent"], "generate")


def _after_retrieve(state: State) -> str:
    return "generate" if state.get("mode") == "vector" else "grade"


def build_graph():
    g = StateGraph(State)
    for name, fn in [("analyze", analyze), ("retrieve", retrieve), ("grade", grade), ("experts", experts),
                     ("recommend", recommend), ("generate", generate), ("explain", explain)]:
        g.add_node(name, fn)
    g.set_entry_point("analyze")
    g.add_edge("analyze", "retrieve")
    g.add_conditional_edges("retrieve", _after_retrieve, ["grade", "generate"])
    g.add_conditional_edges("grade", _after_grade, ["retrieve", "experts", "recommend", "generate"])
    g.add_edge("experts", "generate")
    g.add_edge("recommend", "generate")
    g.add_edge("generate", "explain")
    g.add_edge("explain", END)
    return g.compile()


_app = None


def ask(question: str, mode: str = "graph") -> dict:
    global _app
    _app = _app or build_graph()
    t0 = time.time()
    s = _app.invoke({"question": question, "mode": mode})
    return {"question": question, "mode": mode, "intent": s.get("intent"), "answer": s.get("answer", ""),
            "explanation": s.get("explanation", {}), "experts": s.get("experts", []),
            "recommendations": s.get("recommendations", []),
            "sources": [{k: c[k] for k in ("id", "doc_id", "score", "via", "text")} for c in s.get("chunks", [])],
            "facts": [{k: f[k] for k in ("source", "type", "target")} for f in s.get("facts", [])],
            "graph": s.get("graph", {}), "trace": s.get("trace", []), "latency_s": round(time.time() - t0, 2)}
