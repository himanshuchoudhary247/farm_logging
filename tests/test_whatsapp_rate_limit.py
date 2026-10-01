"""PhoneRateLimiter: limits still enforced, and idle phones are dropped
instead of being kept forever."""
from services.whatsapp_channel.rate_limit import (
    PhoneRateLimiter,
    _FULL_SWEEP_SECONDS,
    _HOUR_SECONDS,
)


def test_per_minute_limit_still_enforced():
    limiter = PhoneRateLimiter(per_min=2, per_hour=10)
    assert limiter.check("+911111111111", now=0)[0]
    assert limiter.check("+911111111111", now=1)[0]
    allowed, reason = limiter.check("+911111111111", now=2)
    assert not allowed
    assert reason.startswith("per_min")


def test_rejected_attempt_is_not_recorded():
    limiter = PhoneRateLimiter(per_min=1, per_hour=10)
    limiter.check("+911111111111", now=0)
    limiter.check("+911111111111", now=1)
    assert limiter.size() == 1


def test_phone_that_never_returns_is_dropped():
    limiter = PhoneRateLimiter(per_min=5, per_hour=50)
    limiter.check("+911111111111", now=0)
    later = _HOUR_SECONDS + _FULL_SWEEP_SECONDS + 1
    limiter.check("+912222222222", now=later)
    assert limiter.tracked_phones() == 1


def test_own_expired_entries_free_the_key():
    limiter = PhoneRateLimiter(per_min=5, per_hour=50)
    limiter.check("+911111111111", now=0)
    assert limiter.check("+911111111111", now=_HOUR_SECONDS + 1)[0]
    assert limiter.tracked_phones() == 1
    assert limiter.size() == 1
    