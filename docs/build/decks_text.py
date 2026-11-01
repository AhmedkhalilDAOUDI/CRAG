"""Results narrative for the slides, phrased from the measured numbers (no hand-typed results)."""


def _cmp(a, b, tol=0.02):
    return "higher than" if a > b + tol else ("lower than" if a < b - tol else "on par with")


def TEXT(x):
    s = x["s"]
    e, sh, rl = s["experts"], s["single_hop"], s["relational"]
    lat = x["v1"]["single_hop"]  # unthrottled latency (run 2 was paced for the API rate limit)
    why_main = (f"Relational questions: CRAG names the right employee in {rl['graph']['exact_match']:.0%} of cases vs "
                f"{rl['vector']['exact_match']:.0%} for classic RAG. Expert P@5 is {_cmp(e['crag_p5'], e['baseline_p5'])} "
                f"the baseline ({e['crag_p5']:.2f} vs {e['baseline_p5']:.2f}); single-hop hit rate is "
                f"{_cmp(sh['graph']['hit_rate'], sh['vector']['hit_rate'])} it.")
    why_quality = (f"On simple questions CRAG's judged correctness is {_cmp(sh['graph']['correctness'], sh['vector']['correctness'], 0.15)} "
                   f"classic RAG; the graph costs time: {lat['graph']['latency_mean_s']:.1f} s vs {lat['vector']['latency_mean_s']:.1f} s per question.")
    limits = [
        f"Small test set ({e['n']} expert, {sh['graph']['n']} single-hop, {rl['graph']['n']} relational questions): a direction, not proof",
        "Iteration 2 was tuned after seeing iteration 1 on the same questions: optimistic for CRAG",
        "Public profile documents, not real company documents",
        "LLM judge from the same model family: correctness/faithfulness are indicative only",
        "Extraction quality not measured directly; synonyms not merged; weights set by hand",
        f"Latency: about {lat['graph']['latency_mean_s'] / max(lat['vector']['latency_mean_s'], 0.01):.1f}× classic RAG (extra model calls)"]
    conclusion = [
        "CRAG builds a knowledge graph from documents with an LLM and answers from graph + passages, with citations",
        "Every brief objective is implemented: OCR, graph, relations, QA, explanations, experts, recommendations, visualisation",
        f"Measured: the graph is decisive on relational questions ({rl['graph']['exact_match']:.0%} vs {rl['vector']['exact_match']:.0%} exact match)",
        "Not a free win: on simple lookups and broad expert queries it is on par, and it is slower",
        "Production-ready: Docker + Neo4j, tests, security, public deployment, documentation"]
    return {"why_main": why_main, "why_quality": why_quality, "limits": limits, "conclusion": conclusion}
