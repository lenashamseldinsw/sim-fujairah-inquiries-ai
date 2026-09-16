"""
Retry policy for Core42 calls.

Two rules do all the work:

  * **Classify before retrying.** A wrong key, a bad model name or a malformed
    request produces the same result on every attempt, so retrying burns the
    whole budget and a minute of latency to reproduce one error. Those are
    raised immediately; rate limits and 5xx are retried, because those heal.
  * **Rate limits get their own schedule.** Core42 429s reflect real capacity
    pressure on a shared endpoint rather than per-second rate limiting, so the
    floor for those is 10s (10/20/40) rather than the 2/4/8 appropriate to a
    transient network blip. An explicit ``Retry-After`` always wins.

Implemented without tenacity to keep the dependency set unchanged.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Tuple, Type, TypeVar

from openai import (
    APIError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from .settings import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Deterministic API failures: the same request fails the same way every time.
DETERMINISTIC_API_ERRORS: Tuple[Type[BaseException], ...] = (
    AuthenticationError,
    PermissionDeniedError,
    BadRequestError,
    NotFoundError,
    UnprocessableEntityError,
)


def retry_after_seconds(exc: BaseException) -> Optional[float]:
    """Read a Retry-After header off an OpenAI SDK error, if present."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None  # HTTP-date form; fall back to the exponential schedule


def wait_seconds(exc: BaseException, attempt: int, base_delay: float) -> float:
    """How long to sleep before attempt ``attempt + 1`` (1-based attempts)."""
    if isinstance(exc, RateLimitError):
        after = retry_after_seconds(exc)
        if after is not None:
            return min(after, 120.0)
        return min(10.0 * (2 ** (attempt - 1)), 120.0)   # 10 / 20 / 40
    return min(base_delay * (2 ** (attempt - 1)), 60.0)  # 2 / 4 / 8


def call_with_retry(fn: Callable[[], T], *, label: str = "core42") -> T:
    """Run ``fn``, retrying only failures that can plausibly heal."""
    s = get_settings()
    attempts = max(s.max_retries, 0) + 1

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except DETERMINISTIC_API_ERRORS as exc:
            logger.error("[%s] Non-retryable API error: %s: %s", label, type(exc).__name__, exc)
            raise
        except (APIError, TimeoutError, ConnectionError) as exc:
            if attempt >= attempts:
                logger.error("[%s] Failed after %d attempt(s): %s", label, attempt, exc)
                raise
            delay = wait_seconds(exc, attempt, s.retry_delay)
            logger.warning(
                "[%s] %s on attempt %d/%d — retrying in %.1fs: %s",
                label, type(exc).__name__, attempt, attempts, delay, exc,
            )
            time.sleep(delay)

    raise RuntimeError(f"[{label}] retry loop exited without a result")  # unreachable
