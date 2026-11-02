"""Thin client for NVIDIA NIM (OpenAI-compatible) chat and embedding endpoints."""
import json
import os
import re
import threading
import time

import httpx
import numpy as np

from .config import settings

_client = httpx.Client(timeout=120)
# Optional client-side pacing (seconds between requests) for batch jobs on rate-limited API tiers.
MIN_INTERVAL = float(os.getenv("CRAG_MIN_INTERVAL", "0"))
_pace_lock, _last_call = threading.Lock(), [0.0]


def _pace():
    if MIN_INTERVAL <= 0:
        return
    with _pace_lock:
        wait = _last_call[0] + MIN_INTERVAL - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()


def _post(path: str, payload: dict) -> dict:
    if not settings.nvidia_api_key:
        raise RuntimeError("NVIDIA_API_KEY is not set")
    headers = {"Authorization": f"Bearer {settings.nvidia_api_key}"}
    for attempt in range(8):
        _pace()
        r = _client.post(f"{settings.nvidia_base_url}{path}", json=payload, headers=headers)
        if r.status_code in (429, 500, 502, 503, 504):  # rate limit / transient: exponential backoff
            retry_after = r.headers.get("retry-after", "")
            time.sleep(float(retry_after) if retry_after.isdigit() else min(2 ** attempt, 30))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def chat(messages: list[dict], max_tokens: int = 1024, temperature: float = 0.2) -> str:
    data = _post("/chat/completions", {
        "model": settings.chat_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        # Nemotron 3.5 is a reasoning model; we keep thinking off for latency and parse-able output.
        "chat_template_kwargs": {"enable_thinking": False},
    })
    return (data["choices"][0]["message"].get("content") or "").strip()


def _merge_duplicates(pairs):
    """Models sometimes repeat a key ({"claims": [...], "claims": []}); json keeps only the last value.
    Repeated lists are concatenated; for anything else the first value wins."""
    out = {}
    for k, v in pairs:
        if isinstance(out.get(k), list) and isinstance(v, list):
            out[k] = out[k] + v
        else:
            out.setdefault(k, v)
    return out


def parse_json(text: str):
    """Extract the first JSON object/array from a model reply (tolerates ``` fences and prose)."""
    text = re.sub(r"```(?:json)?", "", text)
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
    if start == -1:
        raise ValueError(f"No JSON in model output: {text[:200]}")
    obj, _ = json.JSONDecoder(object_pairs_hook=_merge_duplicates).raw_decode(text[start:])
    return obj


def chat_json(system: str, user: str, max_tokens: int = 1500):
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    out = chat(msgs, max_tokens=max_tokens, temperature=0)
    try:
        return parse_json(out)
    except ValueError:
        msgs += [{"role": "assistant", "content": out},
                 {"role": "user", "content": "Return only valid JSON, nothing else."}]
        return parse_json(chat(msgs, max_tokens=max_tokens, temperature=0))


def embed(texts: list[str], kind: str = "passage") -> np.ndarray:
    """Return L2-normalised float32 embeddings. kind is 'passage' for documents, 'query' for questions."""
    vecs = []
    for i in range(0, len(texts), 32):
        batch = [t[:6000] or " " for t in texts[i:i + 32]]
        data = _post("/embeddings", {"model": settings.embed_model, "input": batch,
                                     "input_type": kind, "truncate": "END"})
        vecs += [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
    m = np.asarray(vecs, dtype=np.float32)
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
