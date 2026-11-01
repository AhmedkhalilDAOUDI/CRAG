"""HTTP API + static web UI."""
import tempfile
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT, settings
from .ingest import SUPPORTED, ingest_file
from .store import get_store
from .workflow import ask, recommend_documents

app = FastAPI(title="CRAG", version="1.0.0",
              description="Knowledge-graph-augmented retrieval and question answering over enterprise documents.")
WEB = ROOT / "web"

# shortcut: per-process, in-memory rate limit; use a shared store (Redis) when running several replicas.
_hits: dict[str, deque] = defaultdict(deque)
RATE_LIMIT = 20  # requests per minute per client IP on LLM-backed endpoints


def _rate_limit(request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    q, now = _hits[ip], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "Too many requests, wait a minute.")
    q.append(now)


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    mode: str = Field("graph", pattern="^(graph|vector)$")


@app.get("/api/health")
def health():
    return {"status": "ok", "backend": settings.backend, "model": settings.chat_model,
            "embedding_model": settings.embed_model, "read_only": settings.read_only}


@app.get("/api/stats")
def stats():
    return get_store().stats()


@app.get("/api/documents")
def documents():
    return sorted(get_store().documents(), key=lambda d: d.get("title", ""))


@app.post("/api/ask")
def ask_endpoint(body: AskIn, request: Request):
    _rate_limit(request)
    return ask(body.question.strip(), body.mode)


@app.get("/api/experts")
def experts_endpoint(topic: str, request: Request):
    _rate_limit(request)
    if not 1 < len(topic) <= 200:
        raise HTTPException(422, "topic must be 2-200 characters")
    return ask(f"Who are the experts in {topic}?")


@app.get("/api/recommend")
def recommend_endpoint(doc_id: str):
    store = get_store()
    v = store.doc_vector(doc_id)
    if v is None:
        raise HTTPException(404, "Unknown document")
    return recommend_documents(store, v, store.doc_entities(doc_id), exclude=doc_id)


@app.get("/api/graph")
def graph(limit: int = 150):
    nodes, edges = get_store().sample_graph(max(10, min(limit, 400)))
    return {"nodes": nodes, "edges": edges}


@app.post("/api/ingest")
async def ingest_endpoint(file: UploadFile = File(...), x_admin_token: str = Header(default="")):
    if settings.read_only:
        raise HTTPException(403, "This deployment is read-only.")
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(401, "A valid X-Admin-Token header is required to upload documents.")
    name = Path(file.filename or "upload").name
    if Path(name).suffix.lower() not in SUPPORTED:
        raise HTTPException(415, f"Supported types: {', '.join(sorted(SUPPORTED))}")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File larger than {settings.max_upload_mb} MB")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        path.write_bytes(data)
        try:
            return ingest_file(get_store(), path)
        except ValueError as e:
            raise HTTPException(422, str(e))


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")
