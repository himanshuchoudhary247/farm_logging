"""Pending WhatsApp enrollments: the OTP step (finding 1 of the PR #24
review).

An unknown WhatsApp number that claims a farmer (by registered phone or
username) is NOT linked straight away any more. A 6-digit code is sent by
SMS to that farmer's registered phone, and the WhatsApp number is linked
only after it sends that code back.

In-memory, per-process, same limitation as the rate limiter and dedupe:
a restart drops pending codes (the farmer just asks for a new one), and
a multi-worker deployment needs sticky routing or a shared store.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Optional

OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 3

# Codes are kept only as an HMAC with a per-process random key, so the
# plain code is never held in memory after it is sent.
_HASH_KEY = secrets.token_bytes(32)


def new_code() -> str:
    """Random 6-digit code from the OS CSPRNG (never `random`)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash(code: str) -> str:
    return hmac.new(_HASH_KEY, code.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class PendingEnrollment:
    farmer_id: str
    farmer_name: str
    code_hash: str
    expires_at: float
    question: str = ""
    attempts: int = 0


class PendingEnrollments:
    def __init__(self) -> None:
        self._items: dict[str, PendingEnrollment] = {}
        self._lock = threading.Lock()

    def _drop_expired_locked(self, now: float) -> None:
        for phone in [p for p, item in self._items.items() if item.expires_at <= now]:
            del self._items[phone]

    def start(self, wa_phone: str, farmer_id: str, farmer_name: str, code: str,
              question: str = "", now: Optional[float] = None) -> None:
        """Remember a sent code for this WhatsApp number. A new claim from
        the same number replaces any earlier pending one."""
        stamp = now if now is not None else time.time()
        with self._lock:
            self._drop_expired_locked(stamp)
            self._items[wa_phone] = PendingEnrollment(
                farmer_id=farmer_id,
                farmer_name=farmer_name,
                code_hash=_hash(code),
                expires_at=stamp + OTP_TTL_SECONDS,
                question=question,
            )

    def has(self, wa_phone: str, now: Optional[float] = None) -> bool:
        stamp = now if now is not None else time.time()
        with self._lock:
            item = self._items.get(wa_phone)
            if item is None:
                return False
            if item.expires_at <= stamp:
                del self._items[wa_phone]
                return False
            return True

    def verify(self, wa_phone: str, code: str,
               now: Optional[float] = None) -> tuple[str, Optional[PendingEnrollment]]:
        """("ok", pending) on a correct code (pending is removed),
        ("wrong", None) on a wrong code with attempts left,
        ("locked", None) when that was the last allowed attempt (removed),
        ("none", None) when nothing is pending or it has expired."""
        stamp = now if now is not None else time.time()
        with self._lock:
            item = self._items.get(wa_phone)
            if item is None:
                return "none", None
            if item.expires_at <= stamp:
                del self._items[wa_phone]
                return "none", None
            if hmac.compare_digest(item.code_hash, _hash(code.strip())):
                del self._items[wa_phone]
                return "ok", item
            item.attempts += 1
            if item.attempts >= OTP_MAX_ATTEMPTS:
                del self._items[wa_phone]
                return "locked", None
            return "wrong", None

    def size(self) -> int:
        with self._lock:
            return len(self._items)
        