"""Offline tests: the LLM and embedding calls are replaced by deterministic fakes."""
import dataclasses
import hashlib
import json
import re
import zipfile

import httpx
import numpy as np
import pytest

from crag import ingest, llm, store as store_mod, workflow
from crag.ingest import Chunk, chunk_pages, chunk_text, norm
from crag.store import MemoryStore


def fake_embed(texts, kind="passage"):
    """Bag-of-words hashing embedding: texts sharing words get high cosine similarity."""
    m = np.zeros((len(texts), 64), np.float32)
    for i, t in enumerate(texts):
        for w in norm(t).split():
            m[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)


def fake_chat(messages, max_tokens=1024, temperature=0.2):
    system, user = messages[0]["content"], messages[-1]["content"]
    if "knowledge graph" in system and "extract" in system:
        if "Python" in user:
            return json.dumps({"entities": [{"name": "Alice", "type": "Person"}, {"name": "Python", "type": "Skill"},
                                            {"name": "Company Name", "type": "Organization"}],
                               "relations": [{"source": "Alice", "target": "Python", "type": "HAS_SKILL",
                                              "quote": "Alice writes Python services"}]})
        return json.dumps({"entities": [{"name": "Bob", "type": "Person"}, {"name": "Payroll", "type": "Skill"}],
                           "relations": [{"source": "Bob", "target": "Payroll", "type": "HAS_SKILL",
                                          "quote": "Bob runs payroll"}]})
    if "Classify" in system:
        return '{"intent": "experts", "entities": ["Python"]}' if "expert" in user.lower() else '{"intent":"qa","entities":[]}'
    if "enough to answer" in system:
        return '{"sufficient": true}'
    # Answer: one claim quoting the first 20 characters of S1, citing F1 when facts were given.
    quote = re.search(r"\[S1\] \([^)]*\) (.{20})", user)
    return json.dumps({"claims": [{"text": "Alice knows Python [S9].",
                                   "sources": [{"id": "S1", "quote": quote[1]}] if quote else [],
                                   "facts": ["F1"] if "[F1]" in user else []}]})


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "embed", fake_embed)
    monkeypatch.setattr(llm, "chat", fake_chat)
    s = MemoryStore(tmp_path)
    monkeypatch.setattr(store_mod, "_store", s)
    (tmp_path / "a.txt").write_text("Alice writes Python services for the data platform.")
    (tmp_path / "b.txt").write_text("Bob runs payroll and benefits administration.")
    ingest.ingest_file(s, tmp_path / "a.txt", "Alice")
    ingest.ingest_file(s, tmp_path / "b.txt", "Bob")
    return s


def test_chunking_respects_size_and_overlap():
    text = " ".join(f"Sentence number {i} is here." for i in range(200))
    chunks = chunk_text(text, "d", size=300, overlap=50)
    assert len(chunks) > 5
    assert all(len(c.text) <= 300 + 60 for c in chunks)
    assert chunks[1].text[:20] in chunks[0].text  # overlap carried over


def test_chunking_hard_splits_run_on_text():
    chunks = chunk_text("x" * 2500, "d", size=1000, overlap=100)
    assert [len(c.text) for c in chunks] == [1000, 1000, 700]


def test_norm_and_placeholders():
    assert norm("  Microsoft-Excel ") == "microsoft excel"
    assert norm("C++") == "c++"
    assert norm("Company Name") in ingest.PLACEHOLDERS


def test_parse_json_tolerates_fences_and_prose():
    assert llm.parse_json('Sure!\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        llm.parse_json("no json here")
    assert llm.parse_json('{"claims": [1], "x": "a", "claims": [], "x": "b"}') == {"claims": [1], "x": "a"}


def test_ingest_builds_graph_and_drops_placeholders(mem):
    st = mem.stats()
    assert st["documents"] == 2 and st["relations"] == 2
    assert "company name" not in mem.entities
    assert mem.authors and set(mem.authors.values()) == {"alice", "bob"}


def test_snapshot_roundtrip(mem, tmp_path):
    again = MemoryStore(tmp_path)
    assert again.stats() == mem.stats()
    q = fake_embed(["Python"])[0]
    assert again.search_chunks(q, 1)[0][0]["text"] == mem.search_chunks(q, 1)[0][0]["text"]


def test_neighborhood_hops(mem):
    nodes, edges = mem.neighborhood(["python"], hops=1)
    assert {n["key"] for n in nodes} == {"python", "alice"}
    assert edges[0]["type"] == "HAS_SKILL"


def test_rrf_rewards_agreement():
    s = workflow._rrf(["a", "b"], ["b", "c"])
    assert s["b"] > s["a"] > s["c"]


def test_workflow_graph_mode_finds_expert(mem):
    r = workflow.ask("Who is an expert in Python?")
    assert r["intent"] == "experts"
    assert r["experts"][0]["name"] == "Alice"
    assert r["explanation"]["reasoning_path"][0]["type"] == "HAS_SKILL"
    assert [t["step"] for t in r["trace"]][:3] == ["analyze", "retrieve", "grade"]


def test_workflow_vector_mode_skips_graph(mem):
    r = workflow.ask("What does Alice write?", mode="vector")
    assert r["facts"] == [] and all(s["via"] == "vector" for s in r["sources"])
    assert "grade" not in [t["step"] for t in r["trace"]]


def test_api_validation_and_upload_auth(mem):
    from fastapi.testclient import TestClient
    from crag.api import app
    c = TestClient(app)
    assert c.get("/api/health").json()["status"] == "ok"
    assert c.post("/api/ask", json={"question": "x", "mode": "graph"}).status_code == 422
    assert c.post("/api/ask", json={"question": "hello there", "mode": "sql"}).status_code == 422
    assert c.post("/api/ingest", files={"file": ("a.txt", b"hi")}).status_code in (401, 403)
    doc = mem.documents()[0]["id"]
    assert c.get(f"/api/recommend?doc_id={doc}").status_code == 200
    assert c.get("/api/recommend?doc_id=nope").status_code == 404


# ---------- features ported from XRAG ----------------------------------------------------------

CHUNKS = [{"text": "Alice writes Python services for the data platform."}, {"text": "Bob runs payroll."}]
FACTS = [{"source": "Alice", "type": "HAS_SKILL", "target": "Python"}]


def claim(text, sources=(), facts=()):
    return {"text": text, "sources": [{"id": i, "quote": q} for i, q in sources], "facts": list(facts)}


def test_valid_claim_keeps_validated_markers_only():
    kept, rejected = workflow.validate_claims(
        {"claims": [claim("Alice uses Python [S7].", [("S1", "writes  PYTHON services")], ["F1"])]}, CHUNKS, FACTS)
    assert rejected == 0 and [workflow.format_claim(c) for c in kept] == ["Alice uses Python. [S1][F1]"]
    assert kept[0]["quotes"] == {"S1": ["writes  PYTHON services"]}


@pytest.mark.parametrize("bad", [
    claim("Fabricated source.", [("S3", "Alice manages the CFO team")]),  # S3 does not exist
    claim("Fabricated quote.", [("S1", "Alice manages the CFO team")]),  # not in the passage
    claim("Quote too short.", [("S1", "Alice")]),
    claim("Words changed.", [("S1", "Alice writes Java services")]),
    claim("Fabricated fact.", facts=["F2"]),
    claim("No citation at all."),
    "not a claim",
])
def test_invalid_claims_are_rejected(bad):
    assert workflow.validate_claims({"claims": [bad]}, CHUNKS, FACTS) == ([], 1)


def test_mislabelled_quote_is_moved_to_the_passage_that_contains_it():
    kept, rejected = workflow.validate_claims({"claims": [claim("Bob runs payroll.", [("S1", "Bob runs payroll")])]}, CHUNKS, FACTS)
    assert rejected == 0 and kept[0]["cites"] == ["S2"] and kept[0]["quotes"] == {"S2": ["Bob runs payroll"]}


def test_quote_check_ignores_punctuation_but_not_words():
    assert ingest.quoted("Oracle databases and AWS.\ninfrastructure, equipped", "Oracle databases and AWS infrastructure")
    assert not ingest.quoted("Oracle databases and AWS infrastructure", "Oracle databases and GCP infrastructure")


def test_partially_invalid_answer_keeps_valid_claims():
    raw = {"claims": [claim("Bob runs payroll.", [("S2", "Bob runs payroll")]), claim("Made up.", [("S1", "no such words here")])]}
    kept, rejected = workflow.validate_claims(raw, CHUNKS, FACTS)
    assert rejected == 1 and [workflow.format_claim(c) for c in kept] == ["Bob runs payroll. [S2]"]
    assert workflow.validate_claims("garbage", CHUNKS, FACTS) == ([], 1)


def test_rejected_claims_abstain_with_warning(mem, monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda m, **kw: fake_chat(m) if "claims" not in m[0]["content"]
                        else json.dumps({"claims": [claim("Invented.", [("S1", "words that are not in any passage")])]}))
    r = workflow.ask("What does Alice write?", mode="vector")
    assert r["abstained"] and r["answer"] == workflow.NO_ANSWER and r["warnings"]


def test_no_evidence_abstains_without_calling_the_model(mem, monkeypatch):
    def chat(messages, **kw):
        assert "claims" not in messages[0]["content"], "answer model called without evidence"
        return fake_chat(messages)
    monkeypatch.setattr(llm, "chat", chat)
    r = workflow.ask("zebra giraffe", mode="lexical")
    assert r["abstained"] and r["sources"] == [] and r["answer"] == workflow.NO_ANSWER


def scripted_chat(*replies):
    calls = []

    def chat(messages, **kw):
        calls.append(messages)
        reply = replies[len(calls) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply
    return chat, calls


def test_extraction_retries_once_and_drops_unquoted_relations(monkeypatch):
    good = json.dumps({"entities": [{"name": "Alice", "type": "Person"}, {"name": "Python", "type": "Skill"},
                                    {"name": "Spark", "type": "Technology"}],
                       "relations": [{"source": "Alice", "target": "Python", "type": "HAS_SKILL",
                                      "quote": "Alice writes Python services"},
                                     {"source": "Alice", "target": "Spark", "type": "USES", "quote": "Alice loves Spark daily"},
                                     {"source": "Alice", "target": "Python", "type": "USES"}]})
    chat, calls = scripted_chat("not json", good)
    monkeypatch.setattr(llm, "chat", chat)
    ex = ingest.extract(Chunk("d:0", "d", 0, "Alice writes Python services for the data platform."))
    assert len(calls) == 2 and "Return only one JSON object" in calls[1][-1]["content"]
    assert [(r["target"], r["type"]) for r in ex.relations] == [("Python", "HAS_SKILL")]


def test_extraction_fails_closed_after_two_malformed_replies(monkeypatch):
    chat, calls = scripted_chat('{"entities": "oops"}', "still not json")
    monkeypatch.setattr(llm, "chat", chat)
    ex = ingest.extract(Chunk("d:0", "d", 0, "Alice writes Python."))
    assert len(calls) == 2 and ex.entities == [] and ex.relations == []


def test_extraction_provider_failure_propagates(monkeypatch):
    chat, calls = scripted_chat(httpx.ConnectError("down"))
    monkeypatch.setattr(llm, "chat", chat)
    with pytest.raises(httpx.ConnectError):
        ingest.extract(Chunk("d:0", "d", 0, "Alice writes Python."))
    assert len(calls) == 1  # no schema retry on a provider error


def test_bm25_ranks_exact_terms_and_ignores_no_overlap(mem):
    assert mem.search_text("Who runs payroll?", 5)[0][0]["text"].startswith("Bob")
    assert mem.search_text("zebra giraffe", 5) == []
    assert mem.search_text("who is the", 5) == []  # stopwords only
    from crag.store import tokens
    assert tokens("Gestion de la paie, SQL-Server") == ["gestion", "de", "la", "paie", "sql", "server"]


def test_hybrid_and_lexical_modes(mem):
    r = workflow.ask("Who runs payroll?", mode="hybrid")
    assert "grade" in [t["step"] for t in r["trace"]]
    assert any("lexical" in s["via"] for s in r["sources"])
    r = workflow.ask("Who runs payroll?", mode="lexical")
    assert r["facts"] == [] and {s["via"] for s in r["sources"]} == {"lexical"}
    assert "grade" not in [t["step"] for t in r["trace"]]


def test_chunk_pages_never_cross_pages():
    pages = [(1, " ".join(f"Page one sentence {i}." for i in range(80))), (2, "Page two only.")]
    chunks = chunk_pages(pages, "d")
    assert [c.idx for c in chunks] == list(range(len(chunks)))
    assert chunks[-1].page == 2 and chunks[-1].text == "Page two only."
    assert all("two" not in c.text for c in chunks if c.page == 1)


def test_docx_is_read_with_the_standard_library(tmp_path):
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f'<w:p><w:r><w:t>{t}</w:t></w:r><w:r><w:t xml:space="preserve"> more</w:t></w:r></w:p>' for t in ("First", "Second"))
    with zipfile.ZipFile(tmp_path / "a.docx", "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')
    assert ingest.load_text(tmp_path / "a.docx") == ([(None, "First more\n\nSecond more")], False)
    (tmp_path / "bad.docx").write_bytes(b"not a zip")
    with pytest.raises(ValueError):
        ingest.load_text(tmp_path / "bad.docx")


def test_duplicate_content_is_skipped_and_changed_file_replaced(mem, tmp_path):
    (tmp_path / "copy.txt").write_text((tmp_path / "a.txt").read_text())
    assert ingest.ingest_file(mem, tmp_path / "copy.txt")["duplicate"]
    (tmp_path / "a.txt").write_text("Alice now leads the Kubernetes migration.")
    assert ingest.ingest_file(mem, tmp_path / "a.txt", "Alice")["replaced"]
    st = mem.stats()
    assert st["documents"] == 2 and st["relations"] == 1  # Alice's old Python relation went with the old version
    assert "python" not in mem.entities and mem.search_text("python", 5) == []


def test_delete_document_removes_orphans_only(mem):
    bob = next(d["id"] for d in mem.documents() if d["title"] == "b")
    assert mem.delete_document(bob) and not mem.delete_document(bob)
    assert {"bob", "payroll"}.isdisjoint(mem.entities) and {"alice", "python"} <= set(mem.entities)
    assert mem.stats()["relations"] == 1 and all(c["doc_id"] != bob for c in mem.chunks.values())
    mem.save()
    assert MemoryStore(mem.path).stats() == mem.stats()


def test_api_delete_requires_admin_and_accepts_new_modes(mem, monkeypatch):
    from fastapi.testclient import TestClient
    from crag import api
    monkeypatch.setattr(api, "settings", dataclasses.replace(api.settings, admin_token="secret", read_only=False))
    c = TestClient(api.app)
    doc = mem.documents()[0]["id"]
    assert c.delete(f"/api/documents/{doc}").status_code == 401
    assert c.delete(f"/api/documents/{doc}", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert c.delete("/api/documents/nope", headers={"X-Admin-Token": "secret"}).status_code == 404
    assert c.delete(f"/api/documents/{doc}", headers={"X-Admin-Token": "secret"}).json() == {"deleted": doc}
    for mode in ("hybrid", "lexical"):
        assert c.post("/api/ask", json={"question": "Who runs payroll?", "mode": mode}).status_code == 200


def test_repeated_claims_are_merged():
    raw = {"claims": [claim("Bob runs payroll.", [("S2", "Bob runs payroll")]), claim("Bob runs payroll.", facts=["F1"])]}
    kept, rejected = workflow.validate_claims(raw, CHUNKS, FACTS)
    assert rejected == 0 and [workflow.format_claim(c) for c in kept] == ["Bob runs payroll. [S2][F1]"]
