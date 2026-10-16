"""
One global in-flight cap for every outbound Core42 request — and it adapts to 429s.

Stage 3 fans out to 5 threads, Stage 6 to 7, and the English translation to 9,
so concurrency is not something any single call site can reason about. Every
outbound request therefore passes through ``llm_slot()`` and the limit applies
to the whole job however deeply the callers nest.

The cap is per process, but the gateway's quota is not: N instances at
``LLM_MAX_CONCURRENCY`` each put N times that in flight against one endpoint. So
the limit is additive-increase / multiplicative-decrease, as TCP is. A 429 halves
it (once per ``_CUT_COOLDOWN_SEC``, so one burst of 429s is one cut, not five);
each run of ``limit`` successful calls raises it by one, back up to
``LLM_MAX_CONCURRENCY``. Instances sharing a quota converge on their share of it
without talking to each other, and a single instance that never sees a 429 runs
exactly as a fixed cap would. ``LLM_ADAPTIVE_CONCURRENCY=false`` keeps it fixed.

Raising the limit is not free: Core42 429s reflect real capacity pressure on a
shared endpoint, and the back-off a 429 triggers costs wall-clock, so too much
concurrency makes a job *slower*.

Threads, not asyncio: the pipeline stages are synchronous and spend their time
waiting on HTTP, so the GIL is not the constraint.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# One cut per window: the requests already in flight when the gateway pushes back
# all come back 429 together, and they are one signal, not several. Matches the
# 10-second floor the retry layer waits after a 429.
_CUT_COOLDOWN_SEC = 10.0


class AdaptiveGate:
    """At most ``limit`` requests in flight, with ``limit`` between 1 and ``ceiling``."""

    def __init__(self, ceiling: int, adaptive: bool = True) -> None:
        self.ceiling = ceiling
        self.limit = ceiling
        self.adaptive = adaptive
        self.in_flight = 0
        self._successes = 0
        self._last_cut = float("-inf")
        self._cond = threading.Condition()

    def acquire(self) -> None:
        with self._cond:
            while self.in_flight >= self.limit:
                self._cond.wait()
            self.in_flight += 1

    def release(self, rate_limited: bool = False) -> None:
        with self._cond:
            self.in_flight -= 1
            if self.adaptive:
                if rate_limited:
                    self._cut()
                else:
                    self._grow()
            self._cond.notify_all()

    def _cut(self) -> None:
        now = time.monotonic()
        self._successes = 0
        if now - self._last_cut < _CUT_COOLDOWN_SEC or self.limit <= 1:
            return
        self._last_cut = now
        self.limit = max(1, self.limit // 2)
        logger.warning("Core42 answered 429: in-flight cap lowered to %d of %d", self.limit, self.ceiling)

    def _grow(self) -> None:
        if self.limit >= self.ceiling:
            return
        self._successes += 1
        if self._successes >= self.limit:
            self._successes = 0
            self.limit += 1
            logger.info("Core42 in-flight cap raised to %d of %d", self.limit, self.ceiling)


_lock = threading.Lock()
_gate: Optional[AdaptiveGate] = None
_config: Optional[tuple[int, bool]] = None


def _get_gate() -> Optional[AdaptiveGate]:
    """The process-wide gate, created on first use.

    Built lazily because settings are not available at import time. Rebuilt if
    the configured limit changes, which only happens in tests.
    """
    global _gate, _config
    from .settings import get_settings

    settings = get_settings()
    limit = int(getattr(settings, "max_concurrency", 0) or 0)
    if limit <= 0:
        return None
    config = (limit, bool(getattr(settings, "adaptive_concurrency", True)))
    with _lock:
        if _gate is None or _config != config:
            _gate = AdaptiveGate(*config)
            _config = config
            logger.debug("Core42 concurrency capped at %d in-flight requests (adaptive=%s)", *config)
        return _gate


def _is_rate_limit(exc: BaseException) -> bool:
    from openai import RateLimitError

    return isinstance(exc, RateLimitError)


@contextmanager
def llm_slot(label: str = "core42") -> Iterator[None]:
    """Hold one of the available request slots for the duration of the block.

    Wrap the network call only, never a retry loop: a request that fails and
    backs off should give its slot up to whoever is waiting rather than hold it
    through the wait. A slot held across a 40-second 429 back-off collapses the
    effective concurrency to whatever fraction of requests are not sleeping.
    """
    gate = _get_gate()
    if gate is None:
        yield
        return
    gate.acquire()
    rate_limited = False
    try:
        yield
    except BaseException as exc:
        rate_limited = _is_rate_limit(exc)
        raise
    finally:
        gate.release(rate_limited)


def current_limit() -> Optional[int]:
    """The in-flight cap right now, or None when uncapped. For logs and tests."""
    gate = _get_gate()
    return gate.limit if gate else None


def reset() -> None:
    """Discard the gate so the next call rebuilds it. For tests."""
    global _gate, _config
    with _lock:
        _gate = None
        _config = None
