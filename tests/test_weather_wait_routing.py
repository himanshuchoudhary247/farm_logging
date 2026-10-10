"""While weather waits for a PIN, the PIN (or a place name) still goes to
weather, but a different request goes to its own agent instead of being
swallowed by weather. Seen live: "register a goat" sent while weather waited
was answered by weather, used up an ask, and the PIN that followed went to
query_agent."""
from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from services.chat_orchestrator import adk_router


@pytest.fixture
def waiting(monkeypatch):
    """No booking/registration draft; weather is waiting for a PIN (1 ask so far)."""
    calls = {"classifier": 0, "weather": [], "dispatched": [], "sessions": {}}
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "get_session", lambda key: {"awaiting_location": True, "asks": 1})
    monkeypatch.setattr(adk_router, "update_session", lambda key, data: calls["sessions"].update({key: data}))

    def fake_run_weather(farmer_id, session_id, text, intent, include_audio, language, previous_asks=0):
        calls["weather"].append((text, previous_asks))
        return {"agent": "weather_alert"}

    monkeypatch.setattr(adk_router, "_run_weather", fake_run_weather)

    for name in ("appointment", "add_animal"):
        def fake_handler(farmer_id, session_id, text, language, include_audio, intent, _name=name):
            calls["dispatched"].append((_name, text))
            return {"agent": _name}

        monkeypatch.setitem(adk_router._DISPATCH_TABLE, name, fake_handler)
    return calls


def _classifier_says(monkeypatch, calls, intent):
    async def fake(text):
        calls["classifier"] += 1
        return intent

    monkeypatch.setattr(adk_router, "_classify_intent_async", fake)


def test_pin_goes_to_weather_without_classifier(monkeypatch, waiting):
    _classifier_says(monkeypatch, waiting, "query")
    result = adk_router.route_turn_adk("f-1", "s-1", "411001", "hi-IN")
    assert result["agent"] == "weather_alert"
    assert waiting["weather"] == [("411001", 1)]
    assert waiting["classifier"] == 0


def test_pin_with_space_goes_to_weather(monkeypatch, waiting):
    _classifier_says(monkeypatch, waiting, "query")
    adk_router.route_turn_adk("f-1", "s-1", "411 001", "hi-IN")
    assert waiting["weather"] == [("411 001", 1)]
    assert waiting["classifier"] == 0


def test_place_name_classified_as_query_stays_with_weather(monkeypatch, waiting):
    _classifier_says(monkeypatch, waiting, "query")
    result = adk_router.route_turn_adk("f-1", "s-1", "Pune", "hi-IN")
    assert result["agent"] == "weather_alert"
    assert waiting["classifier"] == 1


def test_weather_follow_up_stays_with_weather(monkeypatch, waiting):
    _classifier_says(monkeypatch, waiting, "weather")
    result = adk_router.route_turn_adk("f-1", "s-1", "आज बारिश होगी?", "hi-IN")
    assert result["agent"] == "weather_alert"


def test_registration_request_leaves_weather(monkeypatch, waiting):
    _classifier_says(monkeypatch, waiting, "add_animal")
    result = adk_router.route_turn_adk("f-1", "s-1", "बकरी रजिस्टर करनी है", "hi-IN")
    assert result["agent"] == "add_animal"
    assert waiting["dispatched"] == [("add_animal", "बकरी रजिस्टर करनी है")]
    assert waiting["weather"] == []
    key = adk_router._weather_session_key("f-1", "s-1")
    assert waiting["sessions"][key] == {"awaiting_location": False}


def test_booking_request_leaves_weather(monkeypatch, waiting):
    _classifier_says(monkeypatch, waiting, "appointment")
    result = adk_router.route_turn_adk("f-1", "s-1", "डॉक्टर बुक करना है", "hi-IN")
    assert result["agent"] == "appointment"
    assert waiting["weather"] == []


def test_channel_gate_still_applies_when_leaving_weather(monkeypatch, waiting):
    _classifier_says(monkeypatch, waiting, "add_animal")
    result = adk_router.route_turn_adk(
        "f-1", "s-1", "बकरी रजिस्टर करनी है", "hi-IN", allowed_intents={"weather", "query"},
    )
    assert result["agent"] is None
    assert waiting["dispatched"] == []


@pytest.mark.parametrize("text, expected", [
    ("411001", True),
    ("411 001", True),
    (" 411001 ", True),
    ("41100", False),
    ("4110011", False),
    ("४११००१", False),
    ("PIN 411001", False),
    ("", False),
])
def test_looks_like_pin(text, expected):
    assert adk_router._looks_like_pin(text) is expected
    