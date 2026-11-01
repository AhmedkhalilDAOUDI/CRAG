"""Offline tests: the LLM and embedding calls are replaced by deterministic fakes."""
import hashlib
import json

import numpy as np
import pytest

from crag import ingest, llm, store as store_mod, workflow
from crag.ingest import chunk_text, norm
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
                               "relations": [{"source": "Alice", "target": "Python", "type": "HAS_SKILL"}]})
        return json.dumps({"entities": [{"name": "Bob", "type": "Person"}, {"name": "Payroll", "type": "Skill"}],
                           "relations": [{"source": "Bob", "target": "Payroll", "type": "HAS_SKILL"}]})
    if "Classify" in system:
        return '{"intent": "experts", "entities": ["Python"]}' if "expert" in user.lower() else '{"intent":"qa","entities":[]}'
    if "enough to answer" in system:
        return '{"sufficient": true}'
    return "Alice knows Python [S1] [F1]."


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
