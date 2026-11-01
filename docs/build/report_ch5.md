# Evaluation

## Objectives and protocol

The evaluation answers one question: *does graph augmentation make CRAG better than classic RAG?* To isolate the contribution of the graph, the baseline is CRAG itself in passages-only mode: the same chat and embedding models, the same chunks, the same prompts and the same top-*k*, with entity linking, graph expansion, fusion, grading and graph-based ranking switched off. In the baseline, experts are ranked by the best similarity between the question and any passage of their documents, which is the document-centred expert-finding model [26].

The validation corpus contains {{N_DOCS}} anonymised public documents describing professional profiles in six occupational domains, two of them scanned. It was used only to validate the platform. Three benchmarks were built so that their gold labels do not come from the system being evaluated (Table 5.1).

<p class="tcap">Table 5.1: Evaluation benchmarks</p>

| Benchmark | Questions | Gold label | Metrics | What it tests |
|---|---|---|---|---|
| Expert finding | {{N_EXP}} (two per domain), e.g. "Who are the experts in payroll, benefits and employee relations?" | People whose profile belongs to the queried domain | Precision@5 | Identifying experts (O6) |
| Single-hop QA | {{N_SH}}, written by the LLM from one randomly sampled passage, with a reference answer | The document of that passage | Hit rate; correctness and faithfulness (LLM judge, 1–5); latency | Simple lookups, where vector search is expected to be strong |
| Relational QA | {{N_RELQ}}, "Which employee is associated with both X and Y?", where X and Y are graph facts that each match 2–6 people but together exactly one | That person | Exact match (the answer names them); hit rate; latency | Questions that need relations between facts (O4, O5) |

The single-hop benchmark deliberately favours vector retrieval, since each question is written from one passage: it checks that the graph does not degrade simple questions. The relational benchmark targets the situation the graph is designed for. Its questions are built from the graph, which favours CRAG; however, the facts used are stated in the documents, which the baseline retrieves from as well. Precision@5, hit rate and exact match require no judge. Correctness and faithfulness are scored by an LLM judge given the question, the reference answer, the system's answer and all the context the answer could cite [22], [29]; since the judge belongs to the same model family as the system, these two scores are treated as indicative.
