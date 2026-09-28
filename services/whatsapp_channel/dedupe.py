"""In-memory, per-process TTL set for inbound-message deduplication.

Meta retries webhook delivery aggressively (documented up to 24h) if we
don't return a 200 fast enough, so a slow reply can produce the same
message.id landing at our webhook two, three times. Without a dedupe the
router would advance drafts twice, send duplicate replies, and burn LLM
tokens on repeats.

Deliberately in-memory and per-process: matches the shape of
`_dev_proxy_usage` in main.py, and the plan explicitly notes this as a
v1 limitation (multi-worker deployment / restart re-processes -- known
tradeoff, callable out in docs).
"""
from __future__ import annotations

import threading
import time
from typing import Optional


class MessageDedupe:
    def __init__(self, ttl_seconds: float = 24 * 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def _sweep_locked(self, now: float) -> None:
        cutoff = now - self.ttl_seconds
        stale = [mid for mid, ts in self._seen.items() if ts < cutoff]
        for mid in stale:
            self._seen.pop(mid, None)

    def is_new(self, message_id: str, now: Optional[float] = None) -> bool:
        """True iff this message_id has NOT been seen inside the TTL
        window. Records the id atomically -- second call with the same id
        returns False. Empty/None id is always treated as new (some
        providers might not include one)."""
        if not message_id:
            return True
        stamp = now if now is not None else time.time()
        with self._lock:
            self._sweep_locked(stamp)
            if message_id in self._seen:
                return False
            self._seen[message_id] = stamp
            return True

    def size(self) -> int:
        with self._lock:
            return len(self._seen)


# Module-level singleton -- the router uses this. Tests inject their own
# instance via monkeypatch.setattr rather than reaching in here.
default_dedupe = MessageDedupe()
