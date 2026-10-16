"""
The Core42 in-flight cap: fixed without 429s, halved by one, grown back by clean calls.
"""
from __future__ import annotations

import threading

import httpx
import pytest
from openai import RateLimitError

from noveintel_complaints.core42 import concurrency
from noveintel_complaints.core42.concurrency import AdaptiveGate


def _rate_limit() -> RateLimitError:
    request = httpx.Request("POST", "https://gateway.test/chat/completions")
    return RateLimitError("rate limited", response=httpx.Response(429, request=request), body=None)


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(concurrency.time, "monotonic", lambda: now[0])
    return now


class TestAdaptiveGate:
    def test_without_429s_it_is_a_fixed_cap(self):
        gate = AdaptiveGate(5)
        for _ in range(50):
            gate.acquire()
            gate.release()
        assert gate.limit == 5 and gate.in_flight == 0

    def test_a_429_halves_the_cap_once_per_window(self, clock):
        gate = AdaptiveGate(8)
        for _ in range(4):           # one burst: four requests come back 429 together
            gate.acquire()
        for _ in range(4):
            gate.release(rate_limited=True)
        assert gate.limit == 4
        clock[0] += concurrency._CUT_COOLDOWN_SEC
        gate.acquire()
        gate.release(rate_limited=True)
        assert gate.limit == 2

    def test_never_below_one(self, clock):
        gate = AdaptiveGate(2)
        for _ in range(5):
            gate.acquire()
            gate.release(rate_limited=True)
            clock[0] += concurrency._CUT_COOLDOWN_SEC
        assert gate.limit == 1

    def test_clean_calls_grow_it_back_to_the_ceiling(self, clock):
        gate = AdaptiveGate(6)
        gate.acquire()
        gate.release(rate_limited=True)
        assert gate.limit == 3
        for _ in range(3 + 4 + 5):   # a round of `limit` clean calls per step
            gate.acquire()
            gate.release()
        assert gate.limit == 6
        for _ in range(20):
            gate.acquire()
            gate.release()
        assert gate.limit == 6

    def test_fixed_when_not_adaptive(self, clock):
        gate = AdaptiveGate(4, adaptive=False)
        gate.acquire()
        gate.release(rate_limited=True)
        assert gate.limit == 4

    def test_a_lowered_cap_holds_new_requests_back(self, clock):
        gate = AdaptiveGate(4)
        for _ in range(3):
            gate.acquire()
        gate.release(rate_limited=True)          # limit 2, 2 still in flight
        entered = threading.Event()

        def request():
            gate.acquire()
            entered.set()
            gate.release()

        worker = threading.Thread(target=request)
        worker.start()
        assert not entered.wait(0.1)             # 2 in flight at a cap of 2
        gate.release()
        assert entered.wait(2)
        worker.join(2)
        gate.release()
        assert gate.in_flight == 0


class TestSlot:
    @pytest.fixture(autouse=True)
    def fresh(self, monkeypatch):
        monkeypatch.setenv("LLM_MAX_CONCURRENCY", "4")
        monkeypatch.delenv("LLM_ADAPTIVE_CONCURRENCY", raising=False)
        from noveintel_complaints.core42.settings import reload_settings

        reload_settings()
        concurrency.reset()
        yield
        concurrency.reset()
        reload_settings()

    def test_a_429_through_the_slot_lowers_the_cap(self):
        with pytest.raises(RateLimitError):
            with concurrency.llm_slot():
                raise _rate_limit()
        assert concurrency.current_limit() == 2

    def test_another_failure_does_not(self):
        with pytest.raises(ValueError):
            with concurrency.llm_slot():
                raise ValueError("not the gateway pushing back")
        assert concurrency.current_limit() == 4

    def test_the_setting_turns_it_off(self, monkeypatch):
        from noveintel_complaints.core42.settings import reload_settings

        monkeypatch.setenv("LLM_ADAPTIVE_CONCURRENCY", "false")
        reload_settings()
        concurrency.reset()
        with pytest.raises(RateLimitError):
            with concurrency.llm_slot():
                raise _rate_limit()
        assert concurrency.current_limit() == 4
