# How to use this document

These are the questions a jury is most likely to ask about CRAG, with answers you can give in your own words. They are grouped by theme. Each answer starts with the short version (say this first), then the detail (use it if they dig). Numbers come from the evaluation run in Chapter 5 of the report.

Three rules for the defence: answer the question that was asked, in the first sentence; when you do not know, say so and say how you would find out; when a limit is pointed out, agree with what is true and say what you would do about it (most are in OTHER_IDEAS.md).

# Table of contents

[[TOC]]

# The subject and the problem

### Q1. In one minute, what is CRAG?
**Short.** A platform that turns company documents into a knowledge graph with an LLM, and answers questions by combining that graph with classic passage retrieval, citing its sources and showing the graph path behind each answer. It also finds experts and recommends similar documents.

**Detail.** Two pipelines. Ingestion: read (with OCR if scanned), chunk, extract entities and relations with the LLM, embed, store in Neo4j. Query: a LangGraph workflow that analyses the question, retrieves passages by meaning and facts from the graph, fuses them, checks the evidence, answers with citations and extracts the reasoning path.

### Q2. Why is classic RAG not enough?
**Short.** It scores each passage alone against the question, so it fails when the answer is a *relation* between facts in different documents, or a question about *people*.

**Detail.** "Who knows both X and Y?" is not similar to any single passage that mentions only X or only Y. A graph stores X and Y as nodes linked to the same person, so one walk finds the answer. My relational benchmark measures exactly this case.

### Q3. Why does the platform use a graph and not just a bigger context window?
**Short.** Long contexts are expensive and models use the middle of long inputs badly (Liu et al., "Lost in the Middle"). A graph selects the few facts that matter and makes the links explicit and citable.

### Q4. What does "CRAG" stand for? Isn't it the name of an existing paper?
**Short.** It is the platform's name, given in the brief's spirit (Connected RAG). Yes, "Corrective RAG" by Yan et al. (2024) is also abbreviated CRAG; I borrowed its corrective step (grade the evidence, retry), but my system is different: it is graph-based and the corrective step is only one node.

### Q5. Who are the users and what do they gain?
**Short.** Employees who need an answer or an expert, and knowledge administrators who add documents. Gain: answers instead of document lists, verifiable through citations, and access to tacit knowledge by knowing who to ask.

# State of the art

### Q6. What is the difference between your approach and Microsoft GraphRAG?
**Short.** GraphRAG pre-computes communities and summaries of the whole graph, which is costly but answers global questions. CRAG does local search: link the question to entities, expand two hops, fuse with vector retrieval. It is cheaper to index and update, but it does not answer "summarise the whole corpus" questions well. Community summaries are in my improvement list.

### Q7. How is CRAG related to LightRAG and HippoRAG?
**Short.** Same family: link query to entities and expand. LightRAG retrieves at entity and relation level; HippoRAG ranks the graph with Personalised PageRank. I use a bounded 2-hop walk and Reciprocal Rank Fusion with vector results. Personalised PageRank is a natural upgrade for my expansion step.

### Q8. Which papers did you rely on most?
Lewis 2020 (RAG), Edge 2024 (GraphRAG), Pan 2024 (LLM + KG roadmap), Hogan 2021 (knowledge graphs), Yan 2024 (Corrective RAG), and Cormack 2009 for Reciprocal Rank Fusion. All 22 are in the RESEARCH PAPERS folder with an index.

### Q9. Where does CRAG sit in Pan et al.'s taxonomy?
**Short.** "Synergised LLM + KG": the LLM builds the graph (LLM-augmented KG) and the graph grounds and explains the LLM (KG-enhanced LLM).

# Data and ingestion

### Q10. You had no company data. How can you claim it works on company documents?
**Short.** The platform is document-agnostic: it reads PDF, text and images and extracts whatever entities they contain. For testing I used a public corpus of anonymised professional profiles, because they contain the knowledge types the brief targets: people, skills, roles, tools, projects. The test data were used only for validation.

**Honest limit.** Real procedures and reports have different structure (tables, references between documents). Before production I would validate on a sample of real documents with the company and adjust the entity types.

### Q11. How does OCR work and when is it used?
**Short.** If a PDF page has almost no text layer (fewer than 20 characters per page on average), we render each page as an image (pypdfium2, 2x resolution) and read it with Tesseract 5. Images are always OCR'd. Both scanned test documents were read correctly.

### Q12. Why chunks of 1,200 characters with 200 overlap?
**Short.** About 250–300 tokens: one or two paragraphs. Small enough for a precise embedding and citation, large enough to keep context. The overlap prevents a fact cut at a boundary from being lost. It is a standard range; tuning it is an ablation I listed.

### Q13. How do you make sure the LLM extracts correct entities and relations?
**Short.** Three layers. A strict prompt (10 allowed types, both ends of a relation must be listed entities, JSON schema, temperature 0). Validation in code (unknown types remapped, dangling relations dropped, placeholders removed). And evaluation downstream: if extraction were poor, expert finding and relational questions would score badly.

**Limit.** I did not measure extraction precision and recall against a hand-labelled set. That is the first evaluation I would add.

### Q14. Give an example of an extraction error you found.
**Short.** The model extracted anonymisation placeholders like "Company Name" and "City" despite the instruction to ignore them. They would have become hub nodes linking every employee to every other, so graph expansion would return everyone. I added a stop-list in code. Lesson: never trust model output without validation.

### Q15. How do you handle duplicates like "MS Excel" and "Microsoft Excel"?
**Short.** Names are normalised (lower case, punctuation removed) so spelling variants merge. True synonyms do not merge yet; the fix is embedding-based clustering with LLM confirmation, which is in the improvement list.

### Q16. How long does ingestion take, and how would it scale?
**Short.** About 20–50 seconds per document, dominated by one LLM call per chunk, with 4 chunks in parallel. To scale: more parallel calls within the API rate limit, a self-hosted model, a smaller extraction model, and incremental re-ingestion of changed files only.

# Graph and storage

### Q17. Why Neo4j?
**Short.** It is a native property-graph database with a mature query language (Cypher), and since version 5 it has vector indexes, so text vectors and graph live in one database. One system to deploy, secure and back up, and joins between vector hits and graph neighbours happen locally.

### Q18. Why do you also have an in-memory backend?
**Short.** Three reasons: the public serverless demo cannot run a database server; tests run in one second without Docker; and the expensive LLM extraction is done once and then copied into Neo4j. Both backends implement the same interface and serve the same workflow.

### Q19. Why one generic RELATED edge instead of specific relationship types?
**Short.** The LLM produces an open vocabulary of verbs, and Cypher cannot take relationship types as parameters. Storing the verb as a property keeps queries simple and robust. The cost is weaker schema enforcement; a fixed ontology is a listed improvement.

### Q20. What is HNSW?
**Short.** Hierarchical Navigable Small World: a multi-layer graph of vectors. Search starts at a sparse top layer, moves greedily toward the query, and descends layer by layer. It finds near neighbours in roughly logarithmic time instead of scanning all vectors, at the cost of being approximate.

### Q21. Show me a Cypher query you use.
```
CALL db.index.vector.queryNodes('chunk_vec', 18, $q) YIELD node, score
OPTIONAL MATCH (node)-[:MENTIONS]->(e:Entity)
RETURN node.id, node.text, collect(e.key), score
```
It returns the 18 passages closest to the question vector with the entities they mention. Note: Neo4j returns (1 + cosine) / 2, which I convert back to cosine so both backends rank the same way.

# Retrieval and the workflow

### Q22. Walk us through what happens when I ask a question.
1. **Analyze**: the LLM returns the intent (lookup, experts, recommendation) and key entities.
2. **Retrieve**: the question is embedded; top passages by cosine; entities linked by name and by vector similarity (≥ 0.35); 2-hop expansion gives facts; passages mentioning those entities form a second ranking; Reciprocal Rank Fusion merges both.
3. **Grade**: the LLM judges if the evidence suffices; if not, it rewrites the query and we retrieve once more.
4. **Experts / recommend**, if asked.
5. **Generate**: the answer cites passages [S#] and facts [F#].
6. **Explain**: the cited facts form the reasoning path drawn in the interface.

### Q23. What is Reciprocal Rank Fusion and why use it?
**Short.** Each item gets the sum, over the rankings it appears in, of 1/(60 + its rank). Items ranked well by both lists win. It needs no calibration between scores of different nature (cosine versus mention counts) and is a robust standard (Cormack et al., 2009). One rule on top: the 3 best semantic passages are always kept, because the first evaluation showed pure fusion could push the best passage out.

### Q24. Why 2 hops?
**Short.** One hop misses chains such as skill → person → other skill. Three hops in a dense graph reaches almost every node, which brings noise. Two is the usual compromise; I cap the neighbourhood at 60 entities, closest first.

### Q25. Why LangGraph and not a simple Python function or a free agent?
**Short.** The workflow has a loop (grade → retrieve again) and branches by intent. LangGraph makes those steps and transitions explicit, gives a trace, and stays testable. A free agent would choose its own steps: more flexible, but less predictable in cost and harder to evaluate.

### Q26. How does the corrective loop help, and why only one retry?
**Short.** When the first retrieval is off-target, a rewritten query often recovers it. Each retry costs about two model calls and a few seconds, so I bound it to one.

### Q27. How do you identify experts exactly?
**Short.** Each candidate gets three signals scaled to [0, 1]: graph evidence (relations between the person and the question's entities, 1 point each, 0.25 for relations to their neighbours), coverage (how many different question entities the person is linked to), and the best semantic similarity of their documents to the question. Score = 0.4 graph + 0.3 coverage + 0.3 semantic. The interface shows the three components and the evidence as citable facts.

**Detail.** The first version counted all of a person's relations; evaluation showed a degree bias (people with long documents won every topic), so the graph signal now counts only evidence about the question.

### Q28. How did you choose 0.4 / 0.3 / 0.3?
**Short.** By hand, giving the graph the largest weight since it carries the explicit skill relations. It is a limit: the right method is to tune them on a labelled validation set (grid search or a small logistic regression). It is in the improvement list.

### Q29. How do recommendations work?
**Short.** For each candidate document: 0.7 × best semantic similarity of its passages + 0.3 × Jaccard overlap of the entity sets. Semantic similarity captures topic; shared entities capture concrete overlap (same tools, same skills).

### Q30. How is the explanation produced? Can it be wrong?
**Short.** It is not generated separately: I extract the [F#] facts and [S#] passages the answer cites. So the explanation shows exactly what the answer relied on. It can still be incomplete if the model makes a claim without citing it; the prompt forbids that, and faithfulness is measured by the judge.

# Models

### Q31. Which models do you use, and why these?
**Short.** Chat: NVIDIA Nemotron 3.5 Lightning 30B-A3B, a Mixture-of-Experts model with about 3 billion active parameters per token, so it is fast, with reasoning turned off for speed and clean JSON. Embeddings: Nemotron 3.5 Embed 1B, 2,048 dimensions. Both via the NVIDIA NIM API provided for the project. I tested the available models first: the ones I planned to use (Llama 3.3 70B, nv-embedqa-e5) had been retired.

### Q32. What is a Mixture of Experts?
**Short.** A model whose layers contain several sub-networks ("experts") and a router that sends each token to only a few of them. Total capacity is large (30B), compute per token is small (about 3B active), hence speed.

### Q33. What about confidentiality? Company documents are sent to an external API.
**Short.** Correct, and for real company data that matters. The same models run as NVIDIA NIM containers on company GPUs with the same API, so the code would not change: only the base URL. Access control per document is also on the roadmap.

### Q34. How do you prevent hallucinations?
**Short.** Grounding (answer only from numbered sources), mandatory citations, an instruction to say when the context is insufficient, temperature 0.2, and a faithfulness score in the evaluation. The interface lets the user click each citation to check it.

# Evaluation

### Q35. How did you evaluate CRAG?
**Short.** Against a classic RAG baseline that uses the same models, chunks and prompts with the graph steps off. Three benchmarks with gold labels not produced by the system: expert finding (Precision@5 by domain), single-hop questions written from random passages (hit rate, judged correctness and faithfulness), and relational questions built from two facts that together identify one person (exact match).

### Q36. What were the results?
{{RESULTS_ANSWER}}

### Q37. Isn't the relational benchmark biased toward the graph?
**Short.** Partly, and deliberately: it targets the case the graph is meant to solve, and the baseline sees the same documents, which contain those facts in plain text. The single-hop benchmark is the counterweight: it is written from single passages, which favours vector search, and checks that the graph does not hurt there.

### Q38. Your test set is small. Are the differences significant?
**Short.** It is small ({{N_EXP}} expert questions, {{N_SH}} single-hop, {{N_RELQ}} relational), so the results show a direction, not a statistically established effect. With more time I would build 100+ questions, repeat runs and report confidence intervals, and above all use real company questions.

### Q39. Why trust an LLM as a judge?
**Short.** LLM judges agree reasonably with humans on correctness and faithfulness (Zheng et al., 2023; RAGAS), but they have biases, and here the judge belongs to the same model family as the system. That is why the main metrics (Precision@5, hit rate, exact match) do not use a judge at all.

### Q40. What would you measure next?
Extraction precision/recall on hand-labelled passages; ablations (no expansion, no corrective loop, different hops and chunk sizes); RAGAS context precision/recall; and user satisfaction in a pilot.

# Engineering and production

### Q41. What does "production-ready" mean for your project?
Containerised (Docker Compose with Neo4j and the API, health checks, non-root user); configured by environment variables; secrets outside the code; input validation, upload authentication, size and type limits, rate limiting, output escaping; retries and error isolation; 11 automated tests; documentation; public deployment.

### Q42. What would break first under heavy load?
The external model API (rate limits and latency), then the in-process rate limiter, which does not share state between replicas. Fixes: self-hosted models or a higher quota, Redis for rate limiting and caching, more API replicas behind a load balancer; Neo4j itself handles this graph size easily.

### Q43. How do you update the graph when a document changes?
**Short.** Today, ingestion is idempotent (MERGE) and skips already-ingested files by name. Proper updates need a content hash and deletion of the document's chunks and relations before re-adding them. That is listed as improvement 5.

### Q44. How did you test the code?
**Short.** 11 automated tests with fake, deterministic models, so they run offline in about a second: chunking, normalisation, JSON parsing, graph building, persistence, neighbourhoods, fusion, the full workflow in both modes, and the API's validation and security. I also tested the Neo4j backend by loading the graph into a container.

### Q45. How is it deployed?
**Short.** Production: `docker compose up` starts Neo4j and the API. Public demo: Vercel serverless, read-only, serving the in-memory snapshot. Code on GitHub. The API key is in the host's encrypted environment settings, never in Git.

### Q46. Why a read-only public demo?
**Short.** Serverless functions have no persistent disk and should not accept uploads from anyone; ingestion also takes longer than a serverless time limit. Ingestion belongs to the Docker deployment with an administrator token.

# Limits and future work

### Q47. What are the main limitations?
Test data not from a real company; small evaluation set; extraction quality not measured directly; synonyms not merged; hand-set weights; no access control per document; external model API. Each has a concrete fix in OTHER_IDEAS.md.

### Q48. If you had three more months, what would you do?
1. Pilot with real company documents and questions, with access control and a self-hosted model.
2. Measure and improve extraction: fixed ontology, embedding-based entity resolution, provenance on each edge.
3. Upgrade retrieval: BM25 as a third ranking, a cross-encoder re-ranker, Personalised PageRank, and text-to-Cypher for counting questions.

### Q49. What did you learn?
Technically: verify external dependencies first (the planned models had been retired); validate every model output in code; measure against a baseline instead of assuming. Methodologically: build the simplest version end to end, then improve where the measurements point.

### Q50. Why should a company adopt this rather than a commercial assistant?
**Short.** It exposes relations and experts, not only passages; every answer is explainable by a graph path; it can run fully on-premise with self-hosted models; and the graph itself is a reusable asset (skills map, expertise directory) beyond question answering.
