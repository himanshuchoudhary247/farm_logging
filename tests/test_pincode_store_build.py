"""_build() fetches weather_alert and seasonal_advisory concurrently
(they're independent -- neither needs the other's result), then
feed_market after (it needs the state either of them resolves). Found in
review of the weather flow: these ran one after another before, stacking
two full network round trips for no reason."""
import threading
import time

from services.pincode_store import store


def test_both_concurrent_calls_happen_and_merge_correctly(monkeypatch):
    monkeypatch.setattr(
        store, "get_weather_alert",
        lambda pin, days=3: {"resolved_location": {"state": "Maharashtra"}, "summary": "sunny"},
    )
    monkeypatch.setattr(
        store, "get_seasonal_advisory_data",
        lambda pin, days=7: {"district": "Pune", "state": "Maharashtra", "forecast": {}},
    )
    monkeypatch.setattr(
        store, "get_feed_price_snapshot",
        lambda state: {"state": state, "commodities": []},
    )
    result = store._build("411001")
    assert result["weather"]["summary"] == "sunny"
    assert result["seasonal"]["district"] == "Pune"
    assert result["state"] == "Maharashtra"
    assert result["feed_market"]["state"] == "Maharashtra"
    assert result["errors"] == []


def test_calls_actually_run_concurrently_not_one_after_another(monkeypatch):
    """Two 0.2s calls run one after another would take >= 0.4s; run
    concurrently they take ~0.2s. A generous 0.35s bound catches a
    regression back to sequential without being flaky on a slow CI box."""
    def slow_weather(pin, days=3):
        time.sleep(0.2)
        return {"resolved_location": {"state": "Maharashtra"}}

    def slow_seasonal(pin, days=7):
        time.sleep(0.2)
        return {"district": "Pune", "state": "Maharashtra"}

    monkeypatch.setattr(store, "get_weather_alert", slow_weather)
    monkeypatch.setattr(store, "get_seasonal_advisory_data", slow_seasonal)
    monkeypatch.setattr(store, "get_feed_price_snapshot", lambda state: {"state": state, "commodities": []})

    start = time.monotonic()
    store._build("411001")
    elapsed = time.monotonic() - start
    assert elapsed < 0.35, f"took {elapsed:.2f}s -- looks sequential, not concurrent"


def test_one_source_failing_does_not_block_the_other(monkeypatch):
    def failing_weather(pin, days=3):
        raise RuntimeError("weather provider down")

    monkeypatch.setattr(store, "get_weather_alert", failing_weather)
    monkeypatch.setattr(
        store, "get_seasonal_advisory_data",
        lambda pin, days=7: {"district": "Pune", "state": "Maharashtra"},
    )
    monkeypatch.setattr(store, "get_feed_price_snapshot", lambda state: {"state": state, "commodities": []})

    result = store._build("411001")
    assert result["weather"] is None
    assert result["seasonal"]["district"] == "Pune"
    assert any("weather_alert" in e for e in result["errors"])
    assert result["state"] == "Maharashtra", "state still resolved from seasonal when weather_alert fails"


def test_both_sources_failing_leaves_no_state_and_skips_feed_market(monkeypatch):
    calls = []

    def failing(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(store, "get_weather_alert", failing)
    monkeypatch.setattr(store, "get_seasonal_advisory_data", failing)
    monkeypatch.setattr(store, "get_feed_price_snapshot", lambda state: calls.append(state))

    result = store._build("411001")
    assert result["weather"] is None and result["seasonal"] is None
    assert result["state"] is None
    assert not calls, "feed_market must not be called with no resolvable state"
    assert "feed_prices: could not resolve state for this PIN" in result["errors"]
