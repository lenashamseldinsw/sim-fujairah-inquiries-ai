"""
Embeddings through the Core42 gateway — inquiries only.

Not one of the files the two services share (the complaints service has no use for
it), so it reads its own settings here rather than adding fields to ``settings.py``,
which must stay identical across both copies.

* **Approved models only**: ``text-embedding-3-large`` (default) and
  ``qwen3-embedding``. The gateway serves others; they are refused.
* **The same plumbing as a chat call**: the shared client, the in-flight cap
  (``llm_slot``), the one retry layer (``call_with_retry``), and the run's token
  ledger — a call that fails for good is counted as a gateway failure.
* **Dimensions**: both models are Matryoshka-trained, so a vector is cut to
  ``CORE42_EMBED_DIMENSIONS`` (default 1024) and re-normalised here; cosine similarity
  is then a dot product. On the ADPF FAQ benchmark, 1024 scored the same as the full
  3,072 (``noveintel-ingest/scripts/compare_models.py``).
* **Queries**: Qwen3 Embedding is instruction-aware, so a query is sent as
  ``Instruct: …\\nQuery:…``; Embeddings 3 Large takes both sides as-is.

Call sites go through the module (``embeddings.embed_texts``) so tests can replace it.
"""
from __future__ import annotations

import os
from typing import Sequence

import numpy as np
from openai import APIError

from . import tokens as token_tracker
from .client import get_core42_client
from .concurrency import llm_slot
from .retry import call_with_retry

__all__ = ["ALLOWED_EMBEDDING_MODELS", "embed_texts", "embedding_model"]

#: Approved embedding model → native size.
ALLOWED_EMBEDDING_MODELS: dict[str, int] = {
    "text-embedding-3-large": 3072,
    "qwen3-embedding": 4096,
}
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
_BATCH = 128
_QUERY_TASK = "Given a customer question, retrieve the published FAQ entry that answers it"


def embedding_model() -> str:
    model = (os.environ.get("CORE42_MODEL_EMBED") or DEFAULT_EMBEDDING_MODEL).strip()
    if model not in ALLOWED_EMBEDDING_MODELS:
        raise ValueError(
            f"CORE42_MODEL_EMBED={model!r} is not an approved embedding model; "
            f"use one of {', '.join(ALLOWED_EMBEDDING_MODELS)}."
        )
    return model


def _dimensions(model: str) -> int:
    raw = (os.environ.get("CORE42_EMBED_DIMENSIONS") or "").strip()
    size = int(raw) if raw else 1024
    return max(32, min(size, ALLOWED_EMBEDDING_MODELS[model]))


def _request(model: str, texts: list[str], stage: str) -> np.ndarray:
    client = get_core42_client()

    def _call():
        with llm_slot("embeddings"):
            return client.embeddings.create(model=model, input=texts)

    try:
        response = call_with_retry(_call, label=f"core42:{stage}:embeddings")
    except (APIError, TimeoutError, ConnectionError):
        token_tracker.track_failure()
        raise
    usage = getattr(response, "usage", None)
    token_tracker.track(model, getattr(usage, "prompt_tokens", 0) or 0, 0, stage)
    data = sorted(response.data, key=lambda d: d.index)
    return np.asarray([d.embedding for d in data], dtype=np.float32)


def embed_texts(texts: Sequence[str], *, query: bool = False, stage: str = "faqs") -> np.ndarray:
    """Unit vectors, one row per text, in order."""
    model = embedding_model()
    size = _dimensions(model)
    if not texts:
        return np.zeros((0, size), dtype=np.float32)
    items = list(texts)
    if query and model.startswith("qwen3"):
        items = [f"Instruct: {_QUERY_TASK}\nQuery:{t}" for t in items]
    chunks = [items[i:i + _BATCH] for i in range(0, len(items), _BATCH)]
    if len(chunks) == 1:
        parts = [_request(model, chunks[0], stage)]
    else:
        # Batches side by side; ``llm_slot`` still caps what is in flight process-wide.
        from .tokens import ScopedThreadPoolExecutor

        with ScopedThreadPoolExecutor(max_workers=4) as pool:
            parts = list(pool.map(lambda chunk: _request(model, chunk, stage), chunks))
    vectors = np.vstack(parts)[:, :size]
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)
