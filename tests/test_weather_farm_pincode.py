"""Weather uses the PIN code of the farmer's farm in main_backend when the
farmer has no saved weather location, so they are not asked for a PIN the app
already has. Best effort: off, failing or missing all fall back to asking."""
import pytest
import requests

from services.flokiq_sync import client
from services.weather_alert import adk_agent

FARMER = "9e95446d-c317-4074-b698-c8cc35325de6"


class _Resp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.fixture(autouse=True)
def fresh_cache():
    client._farm_pin_cache.clear()
    yield
    client._farm_pin_cache.clear()


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("FLOKIQ_SYNC_ENABLED", "true")
    monkeypatch.setenv("FLOKIQ_API_BASE_URL", "https://backend.test/v1/")
    monkeypatch.setenv("FLOKIQ_INTERNAL_API_KEY", "secret-key")


def _capture_get(monkeypatch, resp):
    calls = []

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(client.requests, "get", fake_get)
    return calls


# ---- client.get_farm_pincode ----

def test_off_by_default_makes_no_call(monkeypatch):
    monkeypatch.delenv("FLOKIQ_SYNC_ENABLED", raising=False)
    calls = _capture_get(monkeypatch, _Resp(200, {"pincode": "411001"}))
    assert client.get_farm_pincode(FARMER) is None
    assert calls == []


def test_returns_the_farm_pin_from_the_internal_route(monkeypatch, on):
    calls = _capture_get(monkeypatch, _Resp(200, {"pincode": "411001", "district": "Pune", "state": "Maharashtra"}))
    assert client.get_farm_pincode(FARMER) == "411001"
    assert calls[0]["url"] == f"https://backend.test/v1/internal/farmers/{FARMER}/farm-location"
    assert calls[0]["headers"] == {"X-Internal-Api-Key": "secret-key"}
    assert calls[0]["timeout"] == 3.0


def test_demo_farmer_is_not_looked_up(monkeypatch, on):
    calls = _capture_get(monkeypatch, _Resp(200, {"pincode": "411001"}))
    assert client.get_farm_pincode("f-001") is None
    assert calls == []


def test_missing_key_makes_no_call(monkeypatch, on):
    monkeypatch.delenv("FLOKIQ_INTERNAL_API_KEY")
    calls = _capture_get(monkeypatch, _Resp(200, {"pincode": "411001"}))
    assert client.get_farm_pincode(FARMER) is None
    assert calls == []


@pytest.mark.parametrize("resp", [
    _Resp(404),
    _Resp(500, text="boom"),
    _Resp(200, {"pincode": "4110"}),
    _Resp(200, {"pincode": "011001"}),
    _Resp(200, None),
    _Resp(200, ["411001"]),
    requests.ConnectionError("down"),
])
def test_no_pin_when_farm_missing_call_fails_or_data_is_bad(monkeypatch, on, resp):
    _capture_get(monkeypatch, resp)
    assert client.get_farm_pincode(FARMER) is None


def test_found_pin_is_cached(monkeypatch, on):
    calls = _capture_get(monkeypatch, _Resp(200, {"pincode": "411001"}))
    assert client.get_farm_pincode(FARMER) == "411001"
    assert client.get_farm_pincode(FARMER) == "411001"
    assert len(calls) == 1


def test_missing_farm_is_cached_too(monkeypatch, on):
    calls = _capture_get(monkeypatch, _Resp(404))
    client.get_farm_pincode(FARMER)
    client.get_farm_pincode(FARMER)
    assert len(calls) == 1


def test_failed_call_is_retried_after_a_minute(monkeypatch, on):
    clock = {"t": 1000.0}
    monkeypatch.setattr(client, "_now", lambda: clock["t"])
    calls = _capture_get(monkeypatch, requests.ConnectionError("down"))
    client.get_farm_pincode(FARMER)
    client.get_farm_pincode(FARMER)
    assert len(calls) == 1
    clock["t"] += client._FARM_PIN_RETRY_S + 1
    client.get_farm_pincode(FARMER)
    assert len(calls) == 2


# ---- weather tool ----

def _tool(monkeypatch, farmer=None, farm_pin=None):
    seen = {}

    def fake_farm_pin(farmer_id):
        seen["farm_pin_asked"] = farmer_id
        return farm_pin

    def fake_data(loc):
        seen["loc"] = loc
        return {"pin": loc}

    monkeypatch.setattr(adk_agent, "get_farmer_by_id", lambda farmer_id: farmer)
    monkeypatch.setattr(adk_agent, "_farm_context", lambda farmer_id: None)
    monkeypatch.setattr(adk_agent.flokiq_sync, "get_farm_pincode", fake_farm_pin)
    monkeypatch.setattr(adk_agent, "get_pincode_data", fake_data)
    return adk_agent._make_get_weather_context_tool(FARMER), seen


class _Farmer:
    def __init__(self, weather_location=""):
        self.weather_location = weather_location


def test_farm_pin_is_used_when_no_location_is_saved(monkeypatch):
    tool, seen = _tool(monkeypatch, farmer=_Farmer(""), farm_pin="411001")
    assert tool("") == {"pin": "411001"}
    assert seen["farm_pin_asked"] == FARMER


def test_app_farmer_missing_from_local_store_still_gets_the_farm_pin(monkeypatch):
    tool, seen = _tool(monkeypatch, farmer=None, farm_pin="411001")
    assert tool("") == {"pin": "411001"}


def test_saved_weather_location_wins_over_the_farm_pin(monkeypatch):
    tool, seen = _tool(monkeypatch, farmer=_Farmer("Nashik"), farm_pin="411001")
    tool("")
    assert seen["loc"] == "Nashik"
    assert "farm_pin_asked" not in seen


def test_place_named_by_the_farmer_wins(monkeypatch):
    tool, seen = _tool(monkeypatch, farmer=_Farmer(""), farm_pin="411001")
    tool("422001")
    assert seen["loc"] == "422001"
    assert "farm_pin_asked" not in seen


def test_no_farm_pin_still_asks_for_a_location(monkeypatch):
    tool, seen = _tool(monkeypatch, farmer=_Farmer(""), farm_pin=None)
    assert tool("")["error"] == "no_location"
    assert "loc" not in seen
