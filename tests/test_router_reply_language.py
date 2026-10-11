"""Router passes the app language to weather/query, and keeps sending the
farmer's next message to weather while it is still asking for a location
(capped, so a farmer who moved on is never trapped)."""
from services.chat_orchestrator import adk_router


def test_reply_language_added_for_indian_languages():
    assert adk_router._with_reply_language("411001", "mr-IN").endswith("(Reply in Marathi.)")
    assert adk_router._with_reply_language("411001", "hi-IN").endswith("(Reply in Hindi.)")


def test_english_or_unknown_language_leaves_text_alone():
    assert adk_router._with_reply_language("411001", "en-IN") == "411001"
    assert adk_router._with_reply_language("411001", "xx-IN") == "411001"
    assert adk_router._with_reply_language("411001", "") == "411001"


def _run(monkeypatch, result, previous_asks=0):
    seen, sessions = {}, {}

    def fake_weather(text, farmer_id):
        seen["text"] = text
        return {"result": result, "answer": "PIN?", "speech_text": None}

    monkeypatch.setattr(adk_router, "process_weather_query_adk", fake_weather)
    monkeypatch.setattr(adk_router, "update_session", lambda key, data: sessions.update({key: data}))
    adk_router._run_weather("f-1", "s-1", "पाऊस पडेल का", "weather", False, "mr-IN", previous_asks=previous_asks)
    key = adk_router._weather_session_key("f-1", "s-1")
    return seen, sessions[key]


def test_weather_gets_the_app_language(monkeypatch):
    seen, _ = _run(monkeypatch, {"error": "no_location"})
    assert seen["text"].endswith("(Reply in Marathi.)")


def test_first_location_ask_waits_for_the_pin(monkeypatch):
    _, state = _run(monkeypatch, {"error": "no_location"})
    assert state == {"awaiting_location": True, "asks": 1}


def test_second_ask_still_waits(monkeypatch):
    # "weather?" -> PIN asked -> "will it rain?" -> PIN asked again:
    # the next message (the PIN) must still go to weather.
    _, state = _run(monkeypatch, {"error": "no_location"}, previous_asks=1)
    assert state == {"awaiting_location": True, "asks": 2}


def test_stops_waiting_after_the_cap(monkeypatch):
    _, state = _run(monkeypatch, {"error": "no_location"}, previous_asks=adk_router._MAX_LOCATION_ASKS - 1)
    assert state == {"awaiting_location": False}


def test_real_weather_result_clears_the_wait(monkeypatch):
    _, state = _run(monkeypatch, {"pin": "411001", "weather": {"summary": "Hot"}})
    assert state == {"awaiting_location": False}

def test_place_not_found_error_also_waits_for_the_pin(monkeypatch):
    _, state = _run(monkeypatch, {"error": "Could not find that place"})
    assert state == {"awaiting_location": True, "asks": 1}

    