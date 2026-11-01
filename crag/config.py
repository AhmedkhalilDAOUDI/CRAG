"""Runtime settings, read once from environment variables (and .env if present)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    nvidia_api_key: str = os.getenv("NVIDIA_API_KEY", "")
    nvidia_base_url: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    chat_model: str = os.getenv("CRAG_CHAT_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    embed_model: str = os.getenv("CRAG_EMBED_MODEL", "nvidia/nemotron-3.5-embed-1b")
    # "memory" = NetworkX + NumPy snapshot on disk; "neo4j" = Neo4j graph + native vector index.
    backend: str = os.getenv("CRAG_BACKEND", "memory")
    index_dir: Path = Path(os.getenv("CRAG_INDEX_DIR", str(ROOT / "data" / "index")))
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "")
    chunk_size: int = int(os.getenv("CRAG_CHUNK_SIZE", "1200"))
    chunk_overlap: int = int(os.getenv("CRAG_CHUNK_OVERLAP", "200"))
    top_k: int = int(os.getenv("CRAG_TOP_K", "6"))
    graph_hops: int = int(os.getenv("CRAG_GRAPH_HOPS", "2"))
    # Read-only mode disables uploads (used on serverless hosts with ephemeral disks).
    read_only: bool = os.getenv("CRAG_READ_ONLY", "0") == "1"
    admin_token: str = os.getenv("CRAG_ADMIN_TOKEN", "")
    max_upload_mb: int = int(os.getenv("CRAG_MAX_UPLOAD_MB", "20"))


settings = Settings()
