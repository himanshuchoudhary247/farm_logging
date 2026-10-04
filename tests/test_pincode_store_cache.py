"""Weather data cache in pincode_store: saved per location for the
configured lifetime, one entry per place, failures not kept for hours,
older data served if a refresh fails, one fetch per place at a time."""
import threading
import time

import pytest

from services.pincode_store import store


@pytest.fixture
def clock(monkeypatch):
    store.clear()
    monkeypatch.delenv("WEATHER_CACHE_TTL_HOURS", raising=False)
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(store, "_now", lambda: now["t"])
    yield now
    store.clear()


def _fake_build(calls, ok=True, delay=0.0):
    def build(pin):
        if delay:
            time.sleep(delay)
        calls.append(pin)
        return {
            "pin": pin,
            "weather": {"temp_c": 30} if ok else None,
            "errors": [] if ok else ["weather_alert: down"],
            "fetched_at": 0,
        }
    return build


def test_second_ask_within_lifetime_uses_saved_data(clock, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "_build", _fake_build(calls))
    store.get_pincode_data("411001")
    clock["t"] += 11 * 3600
    store.get_pincode_data("411001")
    assert calls == ["411001"]


def test_data_is_fetched_again_after_lifetime(clock, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "_build", _fake_build(calls))
    store.get_pincode_data("411001")
    clock["t"] += 12 * 3600 + 1
    store.get_pincode_data("411001")
    assert calls == ["411001", "411001"]


def test_default_lifetime_is_12_hours(clock):
    assert store._ttl_seconds() == 12 * 3600


def test_lifetime_from_env(clock, monkeypatch):
    monkeypatch.setenv("WEATHER_CACHE_TTL_HOURS", "24")
    assert store._ttl_seconds() == 24 * 3600
    monkeypatch.setenv("WEATHER_CACHE_TTL_HOURS", "abc")
    assert store._ttl_seconds() == 12 * 3600
    monkeypatch.setenv("WEATHER_CACHE_TTL_HOURS", "0")
    assert store._ttl_seconds() == 12 * 3600


def test_same_place_in_different_case_is_one_entry(clock, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "_build", _fake_build(calls))
    store.get_pincode_data("Pune")
    store.get_pincode_data("  pune ")
    store.get_pincode_data("PUNE")
    assert len(calls) == 1


def test_failed_lookup_is_retried_after_5_minutes_not_12_hours(clock, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "_build", _fake_build(calls, ok=False))
    store.get_pincode_data("000000")
    clock["t"] += 60
    store.get_pincode_data("000000")
    assert len(calls) == 1, "not retried on every message"
    clock["t"] += 5 * 60
    store.get_pincode_data("000000")
    assert len(calls) == 2, "retried after 5 minutes"


def test_failed_refresh_returns_older_data_marked_stale(clock, monkeypatch):
    monkeypatch.setattr(store, "_build", _fake_build([]))
    store.get_pincode_data("411001")
    clock["t"] += 12 * 3600 + 1
    monkeypatch.setattr(store, "_build", _fake_build([], ok=False))
    data = store.get_pincode_data("411001")
    assert data["weather"] == {"temp_c": 30}
    assert data["stale"] is True
    assert "stale" not in store.peek("411001"), "saved entry itself is not changed"


def test_caller_can_still_pass_its_own_lifetime(clock, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "_build", _fake_build(calls))
    store.get_pincode_data("411001", ttl_sec=60)
    clock["t"] += 61
    store.get_pincode_data("411001", ttl_sec=60)
    assert len(calls) == 2


def test_many_asks_at_once_fetch_only_once(clock, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "_build", _fake_build(calls, delay=0.2))
    threads = [threading.Thread(target=store.get_pincode_data, args=("411001",)) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
