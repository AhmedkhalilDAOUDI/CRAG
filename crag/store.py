"""Graph + vector storage behind one interface, with two interchangeable backends.

Graph model (both backends):
  (:Document)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(:Entity)-[:RELATED {type}]->(:Entity)
  (:Entity {type:'Person'})-[:AUTHORED]->(:Document)
"""
import json
from collections import defaultdict

import networkx as nx
import numpy as np

from .config import settings


class MemoryStore:
    """NetworkX graph + NumPy vector matrix, persisted as JSON + NPZ. Used for tests and serverless serving."""

    def __init__(self, path=None):
        self.path = path or settings.index_dir
        self.docs: dict[str, dict] = {}
        self.chunks: dict[str, dict] = {}
        self.entities: dict[str, dict] = {}
        self.mentions: dict[str, set] = defaultdict(set)  # entity key -> chunk ids
        self.authors: dict[str, str] = {}                  # doc id -> person key
        self.g = nx.MultiDiGraph()
        self._cvec: dict[str, np.ndarray] = {}
        self._evec: dict[str, np.ndarray] = {}
        self._mat = None
        self.load()

    # ----- writes
    def add_document(self, meta):
        self.docs[meta["id"]] = meta

    def upsert_entity(self, key, ent, vec):
        if key not in self.entities:
            self.entities[key] = {"key": key, "name": ent["name"], "type": ent["type"],
                                  "description": ent.get("description", "")}
            self._evec[key] = np.asarray(vec, np.float32)
            self.g.add_node(key)
        self._mat = None

    def add_chunk(self, chunk, vec, entity_keys):
        self.chunks[chunk.id] = {"id": chunk.id, "doc_id": chunk.doc_id, "idx": chunk.idx, "text": chunk.text,
                                 "entities": sorted(set(k for k in entity_keys if k in self.entities))}
        self._cvec[chunk.id] = np.asarray(vec, np.float32)
        for k in self.chunks[chunk.id]["entities"]:
            self.mentions[k].add(chunk.id)
        self._mat = None

    def add_relation(self, src, tgt, rtype, desc, doc_id):
        if src in self.entities and tgt in self.entities and src != tgt:
            self.g.add_edge(src, tgt, type=rtype, description=desc, doc_id=doc_id)

    def add_authorship(self, person_key, doc_id):
        self.authors[doc_id] = person_key

    # ----- persistence
    def save(self):
        self.path.mkdir(parents=True, exist_ok=True)
        edges = [{"source": u, "target": v, **d} for u, v, d in self.g.edges(data=True)]
        (self.path / "graph.json").write_text(json.dumps({
            "docs": self.docs, "chunks": self.chunks, "entities": self.entities,
            "authors": self.authors, "edges": edges}))
        ck, ek = list(self._cvec), list(self._evec)
        np.savez_compressed(self.path / "vectors.npz", chunk_ids=np.array(ck), entity_keys=np.array(ek),
                            chunk_vecs=np.stack([self._cvec[k] for k in ck]).astype(np.float16) if ck else np.zeros((0, 1)),
                            entity_vecs=np.stack([self._evec[k] for k in ek]).astype(np.float16) if ek else np.zeros((0, 1)))

    def load(self):
        gj, vz = self.path / "graph.json", self.path / "vectors.npz"
        if not gj.exists():
            return
        data = json.loads(gj.read_text())
        self.docs, self.chunks, self.entities, self.authors = data["docs"], data["chunks"], data["entities"], data["authors"]
        self.g.add_nodes_from(self.entities)
        for e in data["edges"]:
            self.g.add_edge(e.pop("source"), e.pop("target"), **e)
        for cid, c in self.chunks.items():
            for k in c["entities"]:
                self.mentions[k].add(cid)
        v = np.load(vz)
        self._cvec = dict(zip(v["chunk_ids"].tolist(), v["chunk_vecs"].astype(np.float32)))
        self._evec = dict(zip(v["entity_keys"].tolist(), v["entity_vecs"].astype(np.float32)))

    # ----- reads
    def _matrices(self):
        if self._mat is None:
            ck, ek = list(self._cvec), list(self._evec)
            self._mat = (ck, np.stack([self._cvec[k] for k in ck]) if ck else np.zeros((0, 1)),
                         ek, np.stack([self._evec[k] for k in ek]) if ek else np.zeros((0, 1)))
        return self._mat

    def search_chunks(self, qvec, k):
        ck, cm, _, _ = self._matrices()
        if not ck:
            return []
        s = cm @ qvec
        return [(self.chunks[ck[i]], float(s[i])) for i in np.argsort(-s)[:k]]

    def search_entities(self, qvec, k):
        _, _, ek, em = self._matrices()
        if not ek:
            return []
        s = em @ qvec
        return [(self.entities[ek[i]], float(s[i])) for i in np.argsort(-s)[:k]]

    def entities_by_name(self, keys):
        return [self.entities[k] for k in keys if k in self.entities]

    def neighborhood(self, keys, hops, limit=60):
        """Entities within `hops` (ignoring direction) of the seeds, and the relation edges among them."""
        und = self.g.to_undirected(as_view=True)
        dist = {}
        for k in keys:
            if k in und:
                for n, d in nx.single_source_shortest_path_length(und, k, cutoff=hops).items():
                    dist[n] = min(d, dist.get(n, 99))
        keep = set(sorted(dist, key=lambda n: (dist[n], -und.degree(n)))[:limit])
        edges = [{"source": u, "target": v, "type": d["type"], "description": d.get("description", ""),
                  "doc_id": d.get("doc_id")} for u, v, d in self.g.subgraph(keep).edges(data=True)]
        return [dict(self.entities[n], hops=dist[n]) for n in keep], edges

    def chunks_for_entities(self, keys, limit=20):
        count = defaultdict(int)
        for k in keys:
            for cid in self.mentions.get(k, ()):
                count[cid] += 1
        return [(self.chunks[c], n) for c, n in sorted(count.items(), key=lambda x: -x[1])[:limit]]

    def doc_vector(self, doc_id):
        vs = [self._cvec[c] for c, ch in self.chunks.items() if ch["doc_id"] == doc_id]
        if not vs:
            return None
        v = np.mean(vs, axis=0)
        return v / max(np.linalg.norm(v), 1e-9)

    def doc_entities(self, doc_id):
        return {k for c in self.chunks.values() if c["doc_id"] == doc_id for k in c["entities"]}

    def documents(self):
        return list(self.docs.values())

    def stats(self):
        types = defaultdict(int)
        for e in self.entities.values():
            types[e["type"]] += 1
        return {"backend": "memory", "documents": len(self.docs), "chunks": len(self.chunks),
                "entities": len(self.entities), "relations": self.g.number_of_edges(), "entity_types": dict(types)}

    def sample_graph(self, limit=150):
        top = sorted(self.g.degree, key=lambda x: -x[1])[:limit]
        keep = {n for n, _ in top}
        return ([self.entities[n] for n in keep],
                [{"source": u, "target": v, "type": d["type"]} for u, v, d in self.g.subgraph(keep).edges(data=True)])


class Neo4jStore:
    """Neo4j graph with native HNSW vector indexes on Chunk and Entity embeddings (Neo4j >= 5.13)."""

    def __init__(self, dim=2048):
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        self.driver.verify_connectivity()
        for q in [
            "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (e:Entity) REQUIRE e.key IS UNIQUE",
            f"CREATE VECTOR INDEX chunk_vec IF NOT EXISTS FOR (c:Chunk) ON c.embedding OPTIONS "
            f"{{indexConfig: {{`vector.dimensions`: {dim}, `vector.similarity_function`: 'cosine'}}}}",
            f"CREATE VECTOR INDEX entity_vec IF NOT EXISTS FOR (e:Entity) ON e.embedding OPTIONS "
            f"{{indexConfig: {{`vector.dimensions`: {dim}, `vector.similarity_function`: 'cosine'}}}}",
        ]:
            self._run(q)

    def _run(self, cypher, **params):
        with self.driver.session() as s:
            return [r.data() for r in s.run(cypher, **params)]

    # ----- writes
    def add_document(self, meta):
        self._run("MERGE (d:Document {id:$m.id}) SET d += $m", m=meta)

    def upsert_entity(self, key, ent, vec):
        self._run("MERGE (e:Entity {key:$key}) ON CREATE SET e.name=$name, e.type=$type, "
                  "e.description=$desc, e.embedding=$vec", key=key, name=ent["name"], type=ent["type"],
                  desc=ent.get("description", ""), vec=[float(x) for x in vec])

    def add_chunk(self, chunk, vec, entity_keys):
        self._run("MATCH (d:Document {id:$doc}) MERGE (c:Chunk {id:$id}) "
                  "SET c.text=$text, c.idx=$idx, c.doc_id=$doc, c.embedding=$vec MERGE (d)-[:HAS_CHUNK]->(c) "
                  "WITH c UNWIND $keys AS k MATCH (e:Entity {key:k}) MERGE (c)-[:MENTIONS]->(e)",
                  doc=chunk.doc_id, id=chunk.id, text=chunk.text, idx=chunk.idx,
                  vec=[float(x) for x in vec], keys=list(set(entity_keys)))

    def add_relation(self, src, tgt, rtype, desc, doc_id):
        if src != tgt:
            self._run("MATCH (a:Entity {key:$s}), (b:Entity {key:$t}) "
                      "MERGE (a)-[r:RELATED {type:$type, doc_id:$doc}]->(b) SET r.description=$desc",
                      s=src, t=tgt, type=rtype, desc=desc, doc=doc_id)

    def add_authorship(self, person_key, doc_id):
        self._run("MATCH (p:Entity {key:$p}), (d:Document {id:$d}) MERGE (p)-[:AUTHORED]->(d)", p=person_key, d=doc_id)

    def save(self):
        pass  # Neo4j commits each write transaction

    # ----- reads
    @staticmethod
    def _chunk(r):
        return {"id": r["id"], "doc_id": r["doc_id"], "idx": r["idx"], "text": r["text"], "entities": r["entities"]}

    def search_chunks(self, qvec, k):
        rows = self._run("CALL db.index.vector.queryNodes('chunk_vec', $k, $q) YIELD node, score "
                         "OPTIONAL MATCH (node)-[:MENTIONS]->(e:Entity) "
                         "RETURN node.id AS id, node.doc_id AS doc_id, node.idx AS idx, node.text AS text, "
                         "collect(e.key) AS entities, score ORDER BY score DESC", k=k, q=[float(x) for x in qvec])
        # Neo4j cosine score is (1 + cos) / 2; convert back to cosine so both backends agree.
        return [(self._chunk(r), 2 * r["score"] - 1) for r in rows]

    def search_entities(self, qvec, k):
        rows = self._run("CALL db.index.vector.queryNodes('entity_vec', $k, $q) YIELD node, score "
                         "RETURN node.key AS key, node.name AS name, node.type AS type, "
                         "node.description AS description, score", k=k, q=[float(x) for x in qvec])
        return [({kk: r[kk] for kk in ("key", "name", "type", "description")}, 2 * r["score"] - 1) for r in rows]

    def entities_by_name(self, keys):
        return self._run("MATCH (e:Entity) WHERE e.key IN $keys RETURN e.key AS key, e.name AS name, "
                         "e.type AS type, e.description AS description", keys=list(keys))

    def neighborhood(self, keys, hops, limit=60):
        hops = int(hops)  # variable-length bounds cannot be query parameters
        nodes = self._run(
            f"MATCH (s:Entity) WHERE s.key IN $keys MATCH p=shortestPath((s)-[:RELATED*0..{hops}]-(n:Entity)) "
            "WITH n, min(length(p)) AS d RETURN n.key AS key, n.name AS name, n.type AS type, "
            "n.description AS description, d AS hops ORDER BY d, COUNT { (n)--() } DESC LIMIT $limit",
            keys=list(keys), limit=limit)
        edges = self._run("MATCH (a:Entity)-[r:RELATED]->(b:Entity) WHERE a.key IN $ks AND b.key IN $ks "
                          "RETURN a.key AS source, b.key AS target, r.type AS type, r.description AS description, "
                          "r.doc_id AS doc_id", ks=[n["key"] for n in nodes])
        return nodes, edges

    def chunks_for_entities(self, keys, limit=20):
        rows = self._run("MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) WHERE e.key IN $keys "
                         "WITH c, count(e) AS n ORDER BY n DESC LIMIT $limit "
                         "OPTIONAL MATCH (c)-[:MENTIONS]->(x:Entity) "
                         "RETURN c.id AS id, c.doc_id AS doc_id, c.idx AS idx, c.text AS text, "
                         "collect(x.key) AS entities, n", keys=list(keys), limit=limit)
        return [(self._chunk(r), r["n"]) for r in rows]

    @property
    def authors(self):
        return {r["d"]: r["p"] for r in self._run("MATCH (p:Entity)-[:AUTHORED]->(d:Document) RETURN p.key AS p, d.id AS d")}

    @property
    def entities(self):
        return {r["key"]: r for r in self._run("MATCH (e:Entity) RETURN e.key AS key, e.name AS name, "
                                                "e.type AS type, e.description AS description")}

    def doc_vector(self, doc_id):
        rows = self._run("MATCH (c:Chunk {doc_id:$d}) RETURN c.embedding AS v", d=doc_id)
        if not rows:
            return None
        v = np.mean([r["v"] for r in rows], axis=0).astype(np.float32)
        return v / max(np.linalg.norm(v), 1e-9)

    def doc_entities(self, doc_id):
        return {r["k"] for r in self._run("MATCH (:Chunk {doc_id:$d})-[:MENTIONS]->(e:Entity) RETURN DISTINCT e.key AS k", d=doc_id)}

    def documents(self):
        return [r["d"] for r in self._run("MATCH (d:Document) RETURN properties(d) AS d")]

    def stats(self):
        r = self._run("CALL () { MATCH (d:Document) RETURN count(d) AS documents } "
                      "CALL () { MATCH (c:Chunk) RETURN count(c) AS chunks } "
                      "CALL () { MATCH (e:Entity) RETURN count(e) AS entities } "
                      "CALL () { MATCH ()-[r:RELATED]->() RETURN count(r) AS relations } "
                      "RETURN documents, chunks, entities, relations")[0]
        types = {x["t"]: x["n"] for x in self._run("MATCH (e:Entity) RETURN e.type AS t, count(*) AS n")}
        return {"backend": "neo4j", **r, "entity_types": types}

    def sample_graph(self, limit=150):
        nodes = self._run("MATCH (e:Entity) RETURN e.key AS key, e.name AS name, e.type AS type, "
                          "e.description AS description ORDER BY COUNT { (e)-[:RELATED]-() } DESC LIMIT $l", l=limit)
        edges = self._run("MATCH (a:Entity)-[r:RELATED]->(b:Entity) WHERE a.key IN $ks AND b.key IN $ks "
                          "RETURN a.key AS source, b.key AS target, r.type AS type", ks=[n["key"] for n in nodes])
        return nodes, edges


def copy_memory_to_neo4j(mem: MemoryStore, neo: Neo4jStore) -> None:
    """Load a memory snapshot into Neo4j, so extraction (the expensive LLM step) runs only once."""
    from .ingest import Chunk
    for d in mem.docs.values():
        neo.add_document(d)
    for k, e in mem.entities.items():
        neo.upsert_entity(k, e, mem._evec[k])
    for c in mem.chunks.values():
        neo.add_chunk(Chunk(c["id"], c["doc_id"], c["idx"], c["text"]), mem._cvec[c["id"]], c["entities"])
    for u, v, d in mem.g.edges(data=True):
        neo.add_relation(u, v, d["type"], d.get("description", ""), d.get("doc_id"))
    for doc_id, p in mem.authors.items():
        neo.add_authorship(p, doc_id)


_store = None


def get_store():
    global _store
    if _store is None:
        _store = Neo4jStore() if settings.backend == "neo4j" else MemoryStore()
    return _store
