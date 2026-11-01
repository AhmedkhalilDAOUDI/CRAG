"""Ingestion: file -> text (with OCR fallback) -> chunks -> entities/relations -> graph store."""
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import llm
from .config import settings

TEXT_EXT = {".txt", ".md"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
SUPPORTED = TEXT_EXT | IMAGE_EXT | {".pdf"}
ENTITY_TYPES = ["Person", "Organization", "Skill", "Technology", "Concept", "Project",
                "Procedure", "Role", "Certification", "Location"]


@dataclass
class Chunk:
    id: str
    doc_id: str
    idx: int
    text: str


@dataclass
class Extraction:
    entities: list[dict] = field(default_factory=list)   # {name, type, description}
    relations: list[dict] = field(default_factory=list)  # {source, target, type, description}


# ---------- 1. Loading -------------------------------------------------------------------------

def _ocr_image(img) -> str:
    import pytesseract  # optional dependency: only needed for scanned documents
    return pytesseract.image_to_string(img)


def load_text(path: Path) -> tuple[str, bool]:
    """Return (text, used_ocr). PDFs with no text layer are rendered and OCR'd page by page."""
    ext = path.suffix.lower()
    if ext in TEXT_EXT:
        return path.read_text(errors="ignore"), False
    if ext in IMAGE_EXT:
        from PIL import Image
        return _ocr_image(Image.open(path)), True
    if ext == ".pdf":
        from pypdf import PdfReader
        pages = [p.extract_text() or "" for p in PdfReader(path).pages]
        text = "\n".join(pages)
        if len(text.strip()) >= 20 * len(pages):  # a real text layer: no OCR needed
            return text, False
        import pypdfium2
        pdf = pypdfium2.PdfDocument(path)
        return "\n".join(_ocr_image(pdf[i].render(scale=2).to_pil()) for i in range(len(pdf))), True
    raise ValueError(f"Unsupported file type: {ext}")


def clean(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


# ---------- 2. Chunking ------------------------------------------------------------------------

def chunk_text(text: str, doc_id: str, size: int | None = None, overlap: int | None = None) -> list[Chunk]:
    """Greedy sentence packing into ~size-character windows, with overlap carried between windows."""
    size = size or settings.chunk_size
    overlap = overlap if overlap is not None else settings.chunk_overlap
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", text) if s.strip()]
    chunks, buf = [], ""
    for s in sentences:
        while len(s) > size:  # a single run-on "sentence" longer than a window gets hard-split
            head, s = s[:size], s[size - overlap:]
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(head)
        if len(buf) + len(s) + 1 > size and buf:
            chunks.append(buf)
            buf = buf[-overlap:] if overlap else ""
        buf = f"{buf} {s}".strip()
    if buf:
        chunks.append(buf)
    return [Chunk(f"{doc_id}:{i}", doc_id, i, c) for i, c in enumerate(chunks)]


# ---------- 3. Knowledge extraction ------------------------------------------------------------

EXTRACT_SYSTEM = f"""You build an enterprise knowledge graph. From the text, extract:
- entities: the important people, organizations, skills, technologies, concepts, projects,
  procedures, roles, certifications and locations. Allowed types: {", ".join(ENTITY_TYPES)}.
- relations between those entities, as short UPPER_SNAKE_CASE verbs
  (e.g. HAS_SKILL, WORKED_AT, USES, PART_OF, RESPONSIBLE_FOR, CERTIFIED_IN, LOCATED_IN, RELATED_TO).
Rules: use canonical names (e.g. "Microsoft Excel" not "excel 2010"); every relation's source and
target must appear in entities; ignore placeholders like "Company Name" or "City"; at most 15 entities.
Return JSON: {{"entities":[{{"name":"","type":"","description":""}}],
"relations":[{{"source":"","target":"","type":"","description":""}}]}}"""


def extract(chunk: Chunk, subject: str | None = None) -> Extraction:
    hint = (f'This text comes from a document about "{subject}". Represent the document subject as the '
            f'Person entity "{subject}" and attach first-person facts (skills, roles, employers) to it.\n\n'
            if subject else "")
    try:
        data = llm.chat_json(EXTRACT_SYSTEM, hint + "TEXT:\n" + chunk.text)
    except Exception:
        return Extraction()  # one bad chunk must not abort a whole ingestion run
    ents = [e for e in data.get("entities", []) if isinstance(e, dict) and e.get("name")
            and norm(e["name"]) not in PLACEHOLDERS]
    for e in ents:
        e["type"] = e.get("type") if e.get("type") in ENTITY_TYPES else "Concept"
    names = {norm(e["name"]) for e in ents}
    rels = [r for r in data.get("relations", []) if isinstance(r, dict)
            and norm(r.get("source", "")) in names and norm(r.get("target", "")) in names]
    return Extraction(ents, rels)


# Anonymisation placeholders would become hub nodes linking unrelated people; drop them.
PLACEHOLDERS = {"company name", "company", "city", "state", "city state", "name", "n a", ""}


def norm(name: str) -> str:
    """Entity resolution key: case/punctuation-insensitive name."""
    return re.sub(r"[^a-z0-9+#]+", " ", name.lower()).strip()


def doc_id_for(path: Path) -> str:
    return hashlib.sha1(path.name.encode()).hexdigest()[:12]


# ---------- 4. Orchestration -------------------------------------------------------------------

def ingest_file(store, path: Path, subject: str | None = None, workers: int = 4) -> dict:
    text, used_ocr = load_text(path)
    text = clean(text)
    if not text:
        raise ValueError(f"No text could be read from {path.name}")
    doc_id = doc_id_for(path)
    chunks = chunk_text(text, doc_id)
    with ThreadPoolExecutor(workers) as pool:
        extractions = list(pool.map(lambda c: extract(c, subject), chunks))
    chunk_vecs = llm.embed([c.text for c in chunks], "passage")

    entities: dict[str, dict] = {}
    for ex in extractions:
        for e in ex.entities:
            entities.setdefault(norm(e["name"]), e)
    if subject:
        entities.setdefault(norm(subject), {"name": subject, "type": "Person", "description": "Document subject"})
    ent_keys = list(entities)
    ent_vecs = llm.embed([f'{entities[k]["name"]} ({entities[k]["type"]}): {entities[k].get("description", "")}'
                          for k in ent_keys], "passage") if ent_keys else []

    store.add_document({"id": doc_id, "title": path.stem, "source": path.name,
                        "author": subject or "", "ocr": used_ocr, "chars": len(text)})
    for k, v in zip(ent_keys, ent_vecs):
        store.upsert_entity(k, entities[k], v)
    for c, v, ex in zip(chunks, chunk_vecs, extractions):
        store.add_chunk(c, v, [norm(e["name"]) for e in ex.entities])
        for r in ex.relations:
            store.add_relation(norm(r["source"]), norm(r["target"]), r.get("type", "RELATED_TO"),
                               r.get("description", ""), doc_id)
    if subject:
        store.add_authorship(norm(subject), doc_id)
    store.save()
    return {"doc_id": doc_id, "chunks": len(chunks), "entities": len(ent_keys),
            "relations": sum(len(e.relations) for e in extractions), "ocr": used_ocr}
