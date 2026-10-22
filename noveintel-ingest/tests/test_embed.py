from types import SimpleNamespace

import numpy as np
import openai
import pytest

from noveintel_ingest import embed as embed_mod
from noveintel_ingest.embed import Core42Embedder, EmbeddingError, HashEmbedder, make_embedder
from noveintel_ingest.settings import Settings

try:  # openai ≥ 3 builds its errors on httpx2; earlier releases on httpx
    import httpx2 as httpx
except ImportError:  # pragma: no cover
    import httpx


class FakeEmbeddings:
    """Answers like the gateway: a 4096-wide vector per input, out of order."""

    def __init__(self, fail_with=None, failures=0):
        self.calls: list[list[str]] = []
        self.fail_with, self.failures = fail_with, failures

    def create(self, model, input):
        self.calls.append(list(input))
        if self.failures:
            self.failures -= 1
            raise self.fail_with
        data = [SimpleNamespace(index=i, embedding=list(np.arange(4096, dtype=float) + i + 1)) for i in range(len(input))]
        return SimpleNamespace(data=list(reversed(data)))


def _embedder(fake, **settings):
    e = Core42Embedder("qwen3-embedding", 1024, Settings(api_key="test", embed_batch=2, retry_delay=0, **settings))
    e._client = SimpleNamespace(embeddings=fake)
    return e


def _error(cls, status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://x/embeddings"))
    return cls("boom", response=response, body={"error": {"message": "You may not have a quota"}})


def test_only_the_approved_models_are_accepted():
    with pytest.raises(EmbeddingError, match="not on the approved list"):
        Core42Embedder("embed-v-4-0", 1024, Settings(api_key="test"))
    for model in ("qwen3-embedding", "text-embedding-3-large"):
        assert Core42Embedder(model, 1024, Settings(api_key="test")).model == model


def test_dimensions_bounded_by_the_model():
    with pytest.raises(EmbeddingError, match="outside"):
        Core42Embedder("text-embedding-3-large", 4096, Settings(api_key="test"))


def test_missing_key_refused():
    with pytest.raises(EmbeddingError, match="CORE42_API_KEY"):
        Core42Embedder("qwen3-embedding", 1024, Settings(api_key=""))


def test_batched_reordered_truncated_and_normalised():
    fake = FakeEmbeddings()
    vectors = _embedder(fake).embed_documents(["a", "b", "c"])
    assert [len(c) for c in fake.calls] == [2, 1]
    assert vectors.shape == (3, 1024)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1)
    expected = np.arange(1024) + 1.0
    assert np.allclose(vectors[0], expected / np.linalg.norm(expected))


def test_qwen_query_carries_the_instruction_documents_do_not():
    fake = FakeEmbeddings()
    e = _embedder(fake)
    e.embed_documents(["وثيقة"])
    e.embed_query("سؤال")
    assert fake.calls[0] == ["وثيقة"]
    assert fake.calls[1][0].startswith("Instruct: ") and fake.calls[1][0].endswith("\nQuery:سؤال")


def test_bad_request_not_retried_and_message_surfaced():
    fake = FakeEmbeddings(_error(openai.BadRequestError, 400), failures=5)
    with pytest.raises(EmbeddingError, match="quota"):
        _embedder(fake, max_retries=3).embed_documents(["a"])
    assert len(fake.calls) == 1


def test_rate_limit_retried_with_a_floor(monkeypatch):
    slept = []
    monkeypatch.setattr(embed_mod.time, "sleep", slept.append)
    fake = FakeEmbeddings(_error(openai.RateLimitError, 429), failures=1)
    assert _embedder(fake, max_retries=2).embed_documents(["a"]).shape == (1, 1024)
    assert slept == [10.0]


def test_hash_embedder_is_deterministic_and_lexical():
    e = make_embedder("local-hash", 256)
    assert isinstance(e, HashEmbedder)
    a, b, c = e.embed_documents(["متابعة الطلب عبر تم", "متابعة الطلب عبر تم", "الخصم المباشر"])
    assert np.allclose(a, b) and a @ b > a @ c


def test_unmapped_gateway_outage_is_retried(monkeypatch):
    """The gateway's "no healthy upstream" arrives as a bare APIStatusError."""
    monkeypatch.setattr(embed_mod.time, "sleep", lambda s: None)
    fake = FakeEmbeddings(_error(openai.APIStatusError, 503), failures=2)
    assert _embedder(fake, max_retries=2).embed_documents(["a"]).shape == (1, 1024)
    assert len(fake.calls) == 3


def test_outage_past_the_retries_is_an_embedding_error(monkeypatch):
    monkeypatch.setattr(embed_mod.time, "sleep", lambda s: None)
    fake = FakeEmbeddings(_error(openai.APIStatusError, 503), failures=5)
    with pytest.raises(EmbeddingError, match="after 2 attempts"):
        _embedder(fake, max_retries=1).embed_documents(["a"])


def test_outage_sent_as_a_4xx_is_still_retried(monkeypatch):
    monkeypatch.setattr(embed_mod.time, "sleep", lambda s: None)
    response = httpx.Response(400, request=httpx.Request("POST", "https://x/embeddings"))
    exc = openai.BadRequestError("boom", response=response, body={"error": {"message":
          "upstream connect error or disconnect/reset before headers. reset reason: remote connection failure"}})
    fake = FakeEmbeddings(exc, failures=1)
    assert _embedder(fake, max_retries=1).embed_documents(["a"]).shape == (1, 1024)
