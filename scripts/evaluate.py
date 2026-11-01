"""Compare CRAG (graph-augmented) against a classic passages-only RAG baseline on the test corpus.

Benchmarks (gold labels are objective, not produced by the system under test):
  1. Expert finding   - gold = employees whose profile belongs to the queried domain (Kaggle category)
  2. Single-hop QA    - LLM writes a question from one random passage; gold = that passage's document
  3. Relational QA    - question built from two graph facts of one employee; gold = that employee
Outputs data/eval/results.json and charts in docs/eval/.
"""
import json
import random
import re
import statistics as st
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crag import llm  # noqa: E402
from crag.store import get_store  # noqa: E402
from crag.workflow import ask as _ask  # noqa: E402


def ask(question, mode="graph"):
    """One failed question (e.g. persistent rate limit) is recorded as a miss instead of aborting the run."""
    try:
        return _ask(question, mode)
    except Exception as e:
        print("FAILED", mode, question[:60], e, flush=True)
        return {"answer": "", "sources": [], "facts": [], "experts": [], "latency_s": 0.0, "failed": True}

OUT = Path(__file__).resolve().parent.parent / "data" / "eval"
FIG = Path(__file__).resolve().parent.parent / "docs" / "eval"
rng = random.Random(7)

DOMAINS = {
    "INFORMATION-TECHNOLOGY": ["network administration and IT infrastructure", "IT project management and software systems"],
    "ENGINEERING": ["mechanical and electrical engineering design", "engineering testing and technical drawings"],
    "FINANCE": ["financial analysis and budgeting", "accounting, auditing and financial reporting"],
    "HR": ["recruiting and talent acquisition", "payroll, benefits and employee relations"],
    "CONSTRUCTION": ["construction site supervision", "building renovation and construction equipment"],
    "HEALTHCARE": ["patient care and clinical services", "healthcare administration and medical records"],
}


def person_category(store):
    docs = {d["id"]: d for d in store.documents()}
    return {p: docs[d]["source"].split("__")[-2] if docs[d]["source"].startswith("SCANNED")
            else docs[d]["source"].split("__")[0] for d, p in store.authors.items()}


def baseline_experts(store, question, k=5):
    """Classic RAG expert search: rank authors by their best passage similarity to the question."""
    q = llm.embed([question], "query")[0]
    best = {}
    for c, s in store.search_chunks(q, 60):
        p = store.authors.get(c["doc_id"])
        if p and s > best.get(p, -1):
            best[p] = s
    return sorted(best, key=lambda p: -best[p])[:k]


def bench_experts(store):
    cat = person_category(store)
    rows = []
    for gold, queries in DOMAINS.items():
        for topic in queries:
            question = f"Who are the experts in {topic}?"
            crag = [e["key"] for e in ask(question)["experts"]][:5]
            base = baseline_experts(store, question)
            p = lambda ranked: sum(cat.get(x) == gold for x in ranked) / 5  # noqa: E731
            rows.append({"topic": topic, "gold": gold, "crag_p5": p(crag), "baseline_p5": p(base)})
            print("experts", topic, rows[-1]["crag_p5"], rows[-1]["baseline_p5"], flush=True)
    return rows


JUDGE = """You grade an answer against a reference. Return JSON:
{"correctness": 1-5 (5 = fully matches the reference), "faithfulness": 1-5 (5 = every claim supported by the given context)}"""


def judge(question, reference, answer, context):
    try:
        j = llm.chat_json(JUDGE, f"QUESTION: {question}\nREFERENCE: {reference}\nANSWER: {answer}\nCONTEXT:\n{context[:6000]}", 200)
        return float(j["correctness"]), float(j["faithfulness"])
    except Exception:
        return None, None


def bench_singlehop(store, n=24):
    chunks = [c for c in store.chunks.values() if len(c["text"]) > 400]
    rows = []
    for c in rng.sample(chunks, n):
        try:
            qa = llm.chat_json("Write one specific factual question answerable only from this passage, and its short answer. "
                               'Refer to the person as "the employee". Return JSON {"question":"","answer":""}.', c["text"], 300)
        except Exception:
            continue
        for mode in ("graph", "vector"):
            r = ask(qa["question"], mode)
            ctx = "\n".join(s["text"] for s in r["sources"])  # judge sees everything the answer could cite:
            ctx += "\n" + "\n".join(f"{f['source']} -{f['type']}-> {f['target']}" for f in r["facts"])
            cor, fai = judge(qa["question"], qa["answer"], r["answer"], ctx)
            rows.append({"mode": mode, "hit": c["doc_id"] in {s["doc_id"] for s in r["sources"]},
                         "correctness": cor, "faithfulness": fai, "latency": r["latency_s"]})
        print("single-hop", rows[-2]["hit"], rows[-1]["hit"], flush=True)
    return rows


def bench_relational(store, n=12):
    """'Which employee has <A> and <B>?' where exactly one employee holds both facts."""
    by_person = defaultdict(set)
    for u, v, d in store.g.edges(data=True):
        if store.entities[u]["type"] == "Person" and store.entities[v]["type"] in ("Skill", "Technology", "Role", "Certification"):
            by_person[u].add((d["type"], v))
    holders = defaultdict(set)
    for p, facts in by_person.items():
        for f in facts:
            holders[f[1]].add(p)
    cands = []
    for p, facts in by_person.items():
        facts = [f for f in facts if 1 < len(holders[f[1]]) <= 6]  # each fact alone is ambiguous...
        for i in range(len(facts)):
            for j in range(i + 1, len(facts)):
                if holders[facts[i][1]] & holders[facts[j][1]] == {p}:  # ...but together they identify p
                    cands.append((p, facts[i], facts[j]))
    rows = []
    seen = set()
    for p, a, b in rng.sample(cands, min(len(cands), 80)):
        if p in seen or len(rows) >= 2 * n:
            continue
        seen.add(p)
        ea, eb = store.entities[a[1]]["name"], store.entities[b[1]]["name"]
        question = f"Which employee is associated with both {ea} and {eb}?"
        gold_id = re.findall(r"\d+", store.entities[p]["name"])[-1]
        for mode in ("graph", "vector"):
            r = ask(question, mode)
            rows.append({"mode": mode, "question": question, "exact": gold_id in r["answer"],
                         "hit": any(store.authors.get(s["doc_id"]) == p for s in r["sources"]), "latency": r["latency_s"]})
        print("relational", rows[-2]["exact"], rows[-1]["exact"], flush=True)
    return rows


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 3) if xs else None


def summarise(experts, single, rel):
    out = {"experts": {"n": len(experts), "crag_p5": mean([r["crag_p5"] for r in experts]),
                       "baseline_p5": mean([r["baseline_p5"] for r in experts])}}
    for name, rows in (("single_hop", single), ("relational", rel)):
        out[name] = {}
        for mode in ("graph", "vector"):
            rs = [r for r in rows if r["mode"] == mode]
            out[name][mode] = {"n": len(rs), "hit_rate": mean([float(r["hit"]) for r in rs]),
                               "latency_mean_s": mean([r["latency"] for r in rs]),
                               "latency_p95_s": round(sorted(r["latency"] for r in rs)[int(0.95 * (len(rs) - 1))], 2) if rs else None}
            if name == "single_hop":
                out[name][mode] |= {"correctness": mean([r["correctness"] for r in rs]),
                                    "faithfulness": mean([r["faithfulness"] for r in rs])}
            else:
                out[name][mode]["exact_match"] = mean([float(r["exact"]) for r in rs])
    return out


def charts(summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    clay, grey = "#C2643F", "#8A8880"
    metrics = [("Expert P@5", summary["experts"]["crag_p5"], summary["experts"]["baseline_p5"]),
               ("Single-hop hit", summary["single_hop"]["graph"]["hit_rate"], summary["single_hop"]["vector"]["hit_rate"]),
               ("Relational hit", summary["relational"]["graph"]["hit_rate"], summary["relational"]["vector"]["hit_rate"]),
               ("Relational exact", summary["relational"]["graph"]["exact_match"], summary["relational"]["vector"]["exact_match"])]
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=200)
    xs = range(len(metrics))
    ax.bar([x - 0.19 for x in xs], [m[1] or 0 for m in metrics], 0.38, color=clay, label="CRAG (graph-augmented)")
    ax.bar([x + 0.19 for x in xs], [m[2] or 0 for m in metrics], 0.38, color=grey, label="Classic RAG (passages only)")
    for x, m in zip(xs, metrics):
        ax.text(x - 0.19, (m[1] or 0) + 0.02, f"{m[1]:.2f}", ha="center", fontsize=9)
        ax.text(x + 0.19, (m[2] or 0) + 0.02, f"{m[2]:.2f}", ha="center", fontsize=9)
    ax.set_xticks(list(xs), [m[0] for m in metrics]); ax.set_ylim(0, 1.1); ax.set_ylabel("score (0-1)")
    ax.legend(frameon=False, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.12))
    fig.tight_layout(); fig.savefig(FIG / "retrieval_comparison.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 3.6), dpi=200)
    sh = summary["single_hop"]
    labels = ["Correctness", "Faithfulness"]
    ax.bar([0 - 0.19, 1 - 0.19], [sh["graph"]["correctness"], sh["graph"]["faithfulness"]], 0.38, color=clay, label="CRAG")
    ax.bar([0 + 0.19, 1 + 0.19], [sh["vector"]["correctness"], sh["vector"]["faithfulness"]], 0.38, color=grey, label="Classic RAG")
    ax.set_xticks([0, 1], labels); ax.set_ylim(0, 5.5); ax.set_ylabel("LLM-judge score (1-5)")
    ax.legend(frameon=False); fig.tight_layout(); fig.savefig(FIG / "answer_quality.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 3.6), dpi=200)
    ax.bar(["CRAG", "Classic RAG"], [sh["graph"]["latency_mean_s"], sh["vector"]["latency_mean_s"]], color=[clay, grey])
    ax.set_ylabel("mean latency per question (s)"); fig.tight_layout(); fig.savefig(FIG / "latency.png"); plt.close(fig)


def resumable(name, run):
    """Each benchmark is saved as soon as it finishes, so a rate-limited run can resume (--fresh to restart)."""
    part = OUT / f"part_{name}.json"
    if part.exists() and "--fresh" not in sys.argv:
        print("reusing", part.name, flush=True)
        return json.loads(part.read_text())
    rows = run()
    part.write_text(json.dumps(rows))
    return rows


def main():
    store = get_store()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    experts = resumable("experts", lambda: bench_experts(store))
    single = resumable("single_hop", lambda: bench_singlehop(store))
    rel = resumable("relational", lambda: bench_relational(store))
    summary = summarise(experts, single, rel)
    summary["corpus"] = store.stats()
    summary["duration_s"] = round(time.time() - t0)
    (OUT / "results.json").write_text(json.dumps({"summary": summary, "experts": experts, "single_hop": single,
                                                  "relational": rel}, indent=2))
    charts(summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
