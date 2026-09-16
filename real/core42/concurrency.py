"""
One global in-flight cap for every outbound Core42 request.

Stage 3 fans out to 5 threads, Stage 6 to 7, and the English translation to 9,
so concurrency is not something any single call site can reason about. Every
outbound request therefore passes through ``llm_slot()`` and the limit applies
to the whole job however deeply the callers nest.

Raising the limit is not free: Core42 429s reflect real capacity pressure on a
shared endpoint, and the back-off a 429 triggers costs wall-clock, so too much
concurrency makes a job *slower*.

Threads, not asyncio: the pipeline stages are synchronous and spend their time
waiting on HTTP, so the GIL is not the constraint.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_semaphore: Optional[threading.BoundedSemaphore] = None
_limit: Optional[int] = None


def _get_semaphore() -> Optional[threading.BoundedSemaphore]:
    """The process-wide gate, created on first use.

    Built lazily because settings are not available at import time. Rebuilt if
    the configured limit changes, which only happens in tests.
    """
    global _semaphore, _limit
    from .settings import get_settings

    limit = int(getattr(get_settings(), "max_concurrency", 0) or 0)
    if limit <= 0:
        return None
    with _lock:
        if _semaphore is None or _limit != limit:
            _semaphore = threading.BoundedSemaphore(limit)
            _limit = limit
            logger.debug("Core42 concurrency capped at %d in-flight requests", limit)
        return _semaphore


@contextmanager
def llm_slot(label: str = "core42") -> Iterator[None]:
    """Hold one of the available request slots for the duration of the block.

    Wrap the network call only, never a retry loop: a request that fails and
    backs off should give its slot up to whoever is waiting rather than hold it
    through the wait. A slot held across a 40-second 429 back-off collapses the
    effective concurrency to whatever fraction of requests are not sleeping.
    """
    semaphore = _get_semaphore()
    if semaphore is None:
        yield
        return
    semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()


def reset() -> None:
    """Discard the gate so the next call rebuilds it. For tests."""
    global _semaphore, _limit
    with _lock:
        _semaphore = None
        _limit = None
