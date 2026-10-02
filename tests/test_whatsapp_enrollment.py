"""Pending OTP store: correct code links once, wrong codes lock after the
limit, codes expire, and plain codes are never stored."""
from services.whatsapp_channel.enrollment import (
    OTP_MAX_ATTEMPTS,
    OTP_TTL_SECONDS,
    PendingEnrollments,
    new_code,
)

WA = "+919876543210"


def _start(store, code="123456", now=0.0, question=""):
    store.start(WA, "f-1", "Asha", code, question=question, now=now)


def test_new_code_is_six_digits():
    for _ in range(50):
        code = new_code()
        assert len(code) == 6 and code.isdigit()


def test_correct_code_returns_pending_once():
    store = PendingEnrollments()
    _start(store, question="how many goats")
    status, pending = store.verify(WA, "123456", now=10)
    assert status == "ok"
    assert pending.farmer_id == "f-1"
    assert pending.question == "how many goats"
    assert store.verify(WA, "123456", now=11) == ("none", None)


def test_plain_code_is_not_stored():
    store = PendingEnrollments()
    _start(store)
    assert store._items[WA].code_hash != "123456"


def test_wrong_codes_lock_after_the_limit():
    store = PendingEnrollments()
    _start(store)
    for _ in range(OTP_MAX_ATTEMPTS - 1):
        assert store.verify(WA, "000000", now=1)[0] == "wrong"
    assert store.verify(WA, "000000", now=1)[0] == "locked"
    assert store.verify(WA, "123456", now=2) == ("none", None)


def test_code_expires():
    store = PendingEnrollments()
    _start(store, now=0)
    assert store.verify(WA, "123456", now=OTP_TTL_SECONDS + 1) == ("none", None)
    assert store.size() == 0


def test_expired_entries_are_dropped_when_a_new_one_starts():
    store = PendingEnrollments()
    store.start("+911111111111", "f-1", "Asha", "111111", now=0)
    store.start("+912222222222", "f-2", "Ravi", "222222", now=OTP_TTL_SECONDS + 1)
    assert store.size() == 1
    