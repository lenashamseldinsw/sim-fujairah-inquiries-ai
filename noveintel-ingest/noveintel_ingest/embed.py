"""
Embeddings through the Core42 gateway — the two approved models only.

* **Batching**: ``NOVEINGEST_EMBED_BATCH`` texts per request, sequentially.
* **Retries**: 429, 5xx, timeouts and dropped connections are retried
  ``LLM_MAX_RETRIES`` times with exponential backoff, capped at 60 s (a 10 s floor
  for 429s, as in the analytics services). A 400 is not retried — on this gateway it usually means
  the key has no quota for the model, which waiting does not fix.
* **Dimensions**: both models are Matryoshka-trained, so the vector is cut to
  ``NOVEINGEST_EMBED_DIMENSIONS`` and re-normalised here. That works whether or not
  the gateway honours the ``dimensions`` parameter, and gives unit vectors, so
  cosine similarity is a dot product.
* **Queries vs documents**: Qwen3 Embedding is instruction-aware — a query is
  embedded as ``Instruct: <task>\\nQuery:<text>`` and a document as-is. Embeddings
  3 Large takes both as-is.

``HashEmbedder`` is a deterministic, offline stand-in for tests and for trying the
flow without gateway access. It hashes character n-grams: it matches shared
wording, not meaning, and its collections are marked ``local-hash`` so they never
mix with real ones.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from .settings import ALLOWED_EMBEDDING_MODELS, NATIVE_DIMENSIONS, Settings, get_settings

__all__ = ["Core42Embedder", "Embedder", "EmbeddingError", "HashEmbedder", "make_embedder"]

logger = logging.getLogger(__name__)

_OUTAGE_WORDING = ("overloaded", "no healthy upstream", "upstream connect error", "connection refused")
DEFAULT_QUERY_TASK = "Given a question, retrieve the spreadsheet rows that answer it"
HASH_MODEL = "local-hash"


class EmbeddingError(RuntimeError):
    pass


class Embedder(Protocol):
    model: str
    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_query(self, text: str, task: str = DEFAULT_QUERY_TASK) -> np.ndarray: ...


def _fit(vectors: np.ndarray, dimensions: int) -> np.ndarray:
    if vectors.shape[1] < dimensions:
        raise EmbeddingError(
            f"The model returned {vectors.shape[1]}-dimensional vectors; {dimensions} were asked for. "
            "Lower NOVEINGEST_EMBED_DIMENSIONS."
        )
    vectors = vectors[:, :dimensions]
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class Core42Embedder:
    def __init__(self, model: str | None = None, dimensions: int | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.model = (model or self.settings.embed_model).strip()
        if self.model not in ALLOWED_EMBEDDING_MODELS:
            allowed = ", ".join(f"{k} ({v})" for k, v in ALLOWED_EMBEDDING_MODELS.items())
            raise EmbeddingError(f"Embedding model {self.model!r} is not on the approved list: {allowed}.")
        self.dimensions = dimensions or self.settings.embed_dimensions
        if not 32 <= self.dimensions <= NATIVE_DIMENSIONS[self.model]:
            raise EmbeddingError(
                f"{self.dimensions} dimensions is outside 32–{NATIVE_DIMENSIONS[self.model]} for {self.model}."
            )
        if not self.settings.api_key:
            raise EmbeddingError("CORE42_API_KEY is not set. Put it in .env or the environment, then restart.")
        from openai import OpenAI

        # The retry loop below is the only retry layer.
        self._client = OpenAI(
            api_key=self.settings.api_key, base_url=self.settings.base_url,
            timeout=self.settings.timeout, max_retries=0,
        )

    def _request(self, texts: list[str]) -> np.ndarray:
        import openai

        attempts = self.settings.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = self._client.embeddings.create(model=self.model, input=texts)
                data = sorted(response.data, key=lambda d: d.index)
                return np.asarray([d.embedding for d in data], dtype=np.float32)
            except (openai.APIStatusError, openai.APITimeoutError, openai.APIConnectionError) as exc:
                # Decided by status, not exception class: the gateway answers some
                # outages ("no healthy upstream") with a 5xx the SDK maps to no subclass.
                # Its proxy also sends some outages with a 4xx status, so their wording counts too.
                status = getattr(exc, "status_code", None)
                outage = any(s in _message(exc).lower() for s in _OUTAGE_WORDING)
                if status in (401, 403):
                    raise EmbeddingError(f"Core42 rejected the API key: {_message(exc)}") from exc
                if status is not None and status != 429 and status < 500 and not outage:
                    raise EmbeddingError(f"Core42 refused {self.model} ({status}): {_message(exc)}") from exc
                if attempt == attempts:
                    raise EmbeddingError(f"Core42 embedding failed after {attempts} attempts: {_message(exc)}") from exc
                delay = min(self.settings.retry_delay * 2 ** (attempt - 1), 60.0)
                if status == 429:
                    delay = max(delay, 10.0)
                logger.warning("Embedding attempt %d/%d failed (%s %s); retrying in %.0fs",
                               attempt, attempts, type(exc).__name__, status or "", delay)
                time.sleep(delay)
        raise AssertionError("unreachable")

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        size = max(1, self.settings.embed_batch)
        parts = [self._request(list(texts[i:i + size])) for i in range(0, len(texts), size)]
        return _fit(np.vstack(parts), self.dimensions)

    def embed_query(self, text: str, task: str = DEFAULT_QUERY_TASK) -> np.ndarray:
        if self.model.startswith("qwen3"):
            text = f"Instruct: {task}\nQuery:{text}"
        return _fit(self._request([text]), self.dimensions)[0]


def _message(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    return str(exc)


class HashEmbedder:
    """Character 3-gram feature hashing. Offline and deterministic; not semantic."""

    model = HASH_MODEL

    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions

    def _one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dimensions, dtype=np.float32)
        folded = " ".join(text.lower().split())
        for i in range(max(1, len(folded) - 2)):
            h = int.from_bytes(hashlib.blake2b(folded[i:i + 3].encode(), digest_size=8).digest(), "little")
            vec[h % self.dimensions] += 1.0 if (h >> 63) & 1 else -1.0
        return vec

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        return _fit(np.vstack([self._one(t) for t in texts]), self.dimensions)

    def embed_query(self, text: str, task: str = DEFAULT_QUERY_TASK) -> np.ndarray:
        return self.embed_documents([text])[0]


def make_embedder(model: str | None = None, dimensions: int | None = None) -> Embedder:
    if (model or "").strip() == HASH_MODEL:
        return HashEmbedder(dimensions or 512)
    return Core42Embedder(model, dimensions)
