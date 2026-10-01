"""Per-phone-number rate limiter with a per-minute and per-hour window.

In-memory, per-process; same shape/limitation as `_dev_proxy_usage` in
main.py. Not a hard security boundary -- it's cheap insurance against a
looped client or a spammer running up LLM cost, not protection against a
motivated attacker (who could rotate numbers, or just DDoS the webhook
directly). The plan calls out that a multi-worker / restart scenario
loses the counter -- known v1 tradeoff.

Rolling-window impl (not fixed calendar windows): each phone keeps a
short list of the request timestamps within the hour, we count how many
fall in the last 60s and how many in the last 3600s. Cheap for our
volumes (a handful of messages per farmer per hour); if this ever needs
to scale, swap for a token-bucket or Redis-backed counter.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Optional


_HOUR_SECONDS = 3600
_MIN_SECONDS = 60

# How often check() also sweeps every other tracked phone. Without this, a
# phone that messaged once and never came back kept its key (and its
# timestamps) forever, because a phone's entries were only swept when that
# same phone messaged again -- slow unbounded growth over months.
_FULL_SWEEP_SECONDS = 300


class PhoneRateLimiter:
    def __init__(self, per_min: int, per_hour: int) -> None:
        self.per_min = per_min
        self.per_hour = per_hour
        self._log: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_full_sweep = 0.0

    def _sweep_locked(self, phone: str, now: float) -> None:
        q = self._log.get(phone)
        if q is None:
            return
        cutoff = now - _HOUR_SECONDS
        while q and q[0] < cutoff:
            q.popleft()
        if not q:
            # Drop the key itself, not just its entries, so idle phones
            # don't leave empty deques behind.
            del self._log[phone]

    def _sweep_all_locked(self, now: float) -> None:
        for phone in list(self._log.keys()):
            self._sweep_locked(phone, now)
        self._last_full_sweep = now

    def check(self, phone: str, now: Optional[float] = None) -> tuple[bool, str]:
        """(allowed, reason). If allowed, the request is recorded and
        counts against the window. If not allowed, no record is created
        for this attempt (so a client that backs off correctly can retry
        once the window rolls forward)."""
        stamp = now if now is not None else time.time()
        with self._lock:
            if stamp - self._last_full_sweep >= _FULL_SWEEP_SECONDS:
                self._sweep_all_locked(stamp)
            else:
                self._sweep_locked(phone, stamp)
            q = self._log.get(phone, deque())
            in_last_min = sum(1 for t in q if t >= stamp - _MIN_SECONDS)
            in_last_hour = len(q)
            if in_last_min >= self.per_min:
                return False, f"per_min ({self.per_min})"
            if in_last_hour >= self.per_hour:
                return False, f"per_hour ({self.per_hour})"
            self._log[phone].append(stamp)
            return True, ""

    def size(self) -> int:
        with self._lock:
            return sum(len(q) for q in self._log.values())

    def tracked_phones(self) -> int:
        """Number of phones currently holding entries (for tests/metrics)."""
        with self._lock:
            return len(self._log)

        