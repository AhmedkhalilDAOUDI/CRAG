# OTHER IDEAS: improvements that could be committed to CRAG

Each idea says what it changes, why it would help, and roughly how to build it. They are grouped by the part of the pipeline they touch, and ordered inside each group from cheapest to most ambitious.

## 1. Ingestion and document understanding

1. **More file formats.** Add DOCX (python-docx), PPTX (python-pptx), HTML (BeautifulSoup) and e-mail (.eml/.msg) loaders in `crag/ingest.py:load_text`. Enterprise knowledge lives in all of them.
2. **Layout-aware parsing.** Replace plain pypdf extraction with a layout model (NVIDIA `nemotron-parse`, available on the same API key, or Docling) to keep tables, headings and reading order. Tables become rows that can be turned into graph facts directly.
3. **Better OCR.** Tesseract is good on clean scans only. A vision-language model (e.g. `nemotron-3.5-super-vl`) can read handwriting, stamps and photographed pages. Keep Tesseract as the cheap first pass and escalate only low-confidence pages.
4. **Connectors for automatic collection.** The brief says "collect automatically": add scheduled pullers for SharePoint, Google Drive, Confluence, Notion and a watched network folder, each storing a content hash so only changed files are re-ingested.
5. **Incremental updates and deletions.** Today a re-ingested file is skipped by name. Store a SHA-256 of the content, and on change delete the document's chunks, mentions and relations (by `doc_id`) before re-adding them.
6. **Semantic chunking.** Split where the embedding of consecutive sentences changes sharply, instead of every 1,200 characters, so each chunk holds one idea.
7. **Metadata extraction.** Capture author, date, department and document type (procedure, report, contract) as properties; filter retrieval by them ("procedures from 2025 in Finance").

## 2. Knowledge graph quality

8. **Embedding-based entity resolution.** Normalised names miss synonyms ("MS Excel" and "Microsoft Excel"). Cluster entity embeddings (cosine > 0.92, same type) and ask the LLM to confirm merges.
9. **A fixed enterprise ontology.** Constrain relation types to a curated list (HAS_SKILL, WORKED_ON, OWNS_PROCESS, REPORTS_TO, ...) and validate them with SHACL or Pydantic. Fewer, cleaner relation types make Cypher queries reliable.
10. **Confidence and provenance on every edge.** Store the source chunk id, extraction confidence and date on each relation; show them in explanations; let users flag wrong facts.
11. **Community detection and summaries (Microsoft GraphRAG style).** Run Leiden clustering on the entity graph, have the LLM summarise each community, and answer "global" questions ("what are our main competence areas?") from the summaries.
12. **Temporal graph.** Add `valid_from` / `valid_to` to relations so the graph knows who *used to* own a process.
13. **Human-in-the-loop curation screen.** A UI to merge, rename and delete entities and approve new relation types.

## 3. Retrieval and reasoning

14. **Hybrid lexical search.** Add BM25 (Neo4j full-text index or `rank_bm25`) as a third ranking in the RRF fusion. Exact codes, product numbers and acronyms are found better lexically.
15. **Cross-encoder re-ranking.** Re-score the fused top 20 with a re-ranker model (NVIDIA `nv-rerankqa`) before generation.
16. **Text-to-Cypher.** For aggregate questions ("how many employees know Python and SQL?") let the LLM write a Cypher query, validate it read-only, run it, and answer from the rows.
17. **Personalised PageRank for multi-hop (HippoRAG).** Seed PageRank on the linked entities instead of a fixed 2-hop walk; it ranks distant but strongly connected nodes better.
18. **Learned fusion weights.** The expert weights (0.4/0.3/0.3) and document weights (0.7/0.3) were set by hand; tune them on a labelled validation set with grid search or logistic regression.
19. **Conversation memory.** Keep the last turns in the LangGraph state so follow-ups ("and who else?") work.
20. **Streaming answers.** Stream tokens to the UI with server-sent events to cut perceived latency.

## 4. Evaluation

21. **A human-labelled gold set** of 100 real company questions with expected answers and sources, built with domain experts.
22. **RAGAS metrics** (context precision/recall, answer relevancy) and repeated runs with confidence intervals.
23. **Ablations.** Measure each component alone: no graph expansion, no corrective loop, no entity linking, different hop counts and chunk sizes.
24. **Online feedback.** Thumbs up/down on each answer stored with the trace, to find failure patterns.

## 5. Security, governance and operations

25. **Authentication and SSO** (OIDC with the company identity provider) instead of a shared admin token.
26. **Document-level access control.** Store allowed groups on each Document and filter retrieval by the user's groups, so the model never sees what the user may not read.
27. **PII detection and redaction** before indexing (Presidio), with an audit log of who asked what.
28. **Self-hosted models.** Run Nemotron through NVIDIA NIM containers on company GPUs so no document leaves the network.
29. **Observability.** OpenTelemetry traces per LangGraph node, Prometheus metrics (latency, token usage, error rate) and a Grafana dashboard.
30. **Shared rate limiting and caching** with Redis (the current limiter is per process); cache embeddings of repeated questions.
31. **CI/CD.** GitHub Actions running the tests, a lint step and a Docker build on each push; deploy on tag.
32. **Managed Neo4j (AuraDB)** for the public deployment, so the online demo uses the same backend as production.

## 6. Product features

33. **Expert profiles.** A page per person: skills graph, documents, projects, and "ask this expert" contact links.
34. **Skill-gap analysis.** Compare the skills a project needs with the skills available in the graph.
35. **Onboarding paths.** Recommend the ordered set of procedures and documents a new hire in a role should read.
36. **Alerts.** Notify an expert when a new document mentions their domain.
37. **Multilingual support.** Embeddings already handle many languages; add French and Arabic UI strings and evaluate on French documents, which matter in a Moroccan enterprise.
