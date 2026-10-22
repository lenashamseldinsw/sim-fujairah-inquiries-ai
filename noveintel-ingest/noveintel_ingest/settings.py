"""
Settings, read once from the environment (and a ``.env`` beside the process).

The Core42 variables carry the same names as the analytics services', so one key
configures all three. Settings are cached: restart after editing ``.env``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

__all__ = ["ALLOWED_EMBEDDING_MODELS", "Settings", "get_settings"]

# The approved model list allows exactly two embedding models. The gateway serves
# others (embed-v-4-0, for one) — they are refused here, not left to discipline.
ALLOWED_EMBEDDING_MODELS: dict[str, str] = {
    "qwen3-embedding": "Qwen3 Embedding 8B",
    "text-embedding-3-large": "Embeddings 3 Large",
}

# Native output sizes. Both are Matryoshka-trained: a prefix of the vector,
# re-normalised, is itself a good embedding.
NATIVE_DIMENSIONS: dict[str, int] = {
    "qwen3-embedding": 4096,
    "text-embedding-3-large": 3072,
}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    base_url: str = "https://api.core42.ai/v1"
    embed_model: str = "text-embedding-3-large"
    embed_dimensions: int = 1024
    embed_batch: int = 64
    timeout: float = 120.0
    max_retries: int = 2
    retry_delay: float = 2.0
    pg_dsn: str = ""
    pg_data_dir: str = ".pgdata"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    base = (os.environ.get("CORE42_BASE_URL") or "https://api.core42.ai/v1").strip().rstrip("/")
    base = base.removesuffix("/chat/completions").removesuffix("/embeddings").rstrip("/")
    return Settings(
        api_key=(os.environ.get("CORE42_API_KEY") or "").strip(),
        base_url=base,
        embed_model=(os.environ.get("CORE42_MODEL_EMBED") or "text-embedding-3-large").strip(),
        embed_dimensions=_int("NOVEINGEST_EMBED_DIMENSIONS", 1024),
        embed_batch=_int("NOVEINGEST_EMBED_BATCH", 64),
        timeout=_float("CORE42_REQUEST_TIMEOUT", 120.0),
        max_retries=_int("LLM_MAX_RETRIES", 2),
        retry_delay=_float("LLM_RETRY_DELAY", 2.0),
        pg_dsn=(os.environ.get("NOVEINGEST_PG_DSN") or "").strip(),
        pg_data_dir=(os.environ.get("NOVEINGEST_PG_DATA_DIR") or ".pgdata").strip(),
    )
