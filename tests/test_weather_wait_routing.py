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
    """No booking/registration draft; weather is waiting for a PIN (1 ask so far).
    The "query" probe (see test_query_probe_* below) defaults to returning
    no sql/data, matching the common "Pune" case -- not a real database
    question, stays with weather."""
    calls = {"classifier": 0, "weather": [], "dispatched": [], "sessions": {}, "probed": []}
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "get_session", lambda key: {"awaiting_location": True, "asks": 1})
    monkeypatch.setattr(adk_router, "update_session", lambda key, data: calls["sessions"].update({key: data}))

    def fake_run_weather(farmer_id, session_id, text, intent, include_audio, language, previous_asks=0):
        calls["weather"].append((text, previous_asks))
        return {"agent": "weather_alert"}

    monkeypatch.setattr(adk_router, "_run_weather", fake_run_weather)

    def fake_dispatch_query(farmer_id, session_id, text, language, include_audio, intent):
        calls["probed"].append(text)
        return {"agent": "query_agent", "result": {}}

    monkeypatch.setattr(adk_router, "_dispatch_query", fake_dispatch_query)

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
    """"Pune" classifies as "query" (seen live, as often as "weather"),
    but isn't a real database question -- the probe (mocked to return no
    sql/data, the common case) must find nothing and fall through."""
    _classifier_says(monkeypatch, waiting, "query")
    result = adk_router.route_turn_adk("f-1", "s-1", "Pune", "hi-IN")
    assert result["agent"] == "weather_alert"
    assert waiting["classifier"] == 1
    assert waiting["probed"] == ["Pune"], "must probe query_agent before assuming it's a location reply"


def test_real_database_question_reaches_query_agent_not_weather(monkeypatch, waiting):
    """Real bug, found in whole-branch review: before this fix, EVERY
    "query"-classified turn while weather waited was swallowed by
    weather, including a genuine database question like "how many goats
    do I have" -- producing a nonsensical weather reply to it instead of
    an actual answer. A probe that returns real sql+data is strong
    evidence this was an answerable question, not a location reply."""
    _classifier_says(monkeypatch, waiting, "query")
    monkeypatch.setattr(
        adk_router, "_dispatch_query",
        lambda farmer_id, session_id, text, language, include_audio, intent: {
            "agent": "query_agent",
            "result": {"sql": "SELECT COUNT(*) FROM animals WHERE species='goat'", "data": {"count": 7}},
        },
    )
    result = adk_router.route_turn_adk("f-1", "s-1", "how many goats do I have", "hi-IN")
    assert result["agent"] == "query_agent"
    assert waiting["weather"] == [], "must not also run the weather branch once query_agent answers for real"


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
    assert waiting["sessions"][key] == {"awaiting_location": False, "last_was_weather": False}


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


@pytest.mark.parametrize("text, expected", [
    ("411001", True),   # valid 6-digit PIN
    ("41100", True),    # one digit dropped (5)
    ("4110011", True),  # one digit doubled (7)
    ("46111", True),    # a mistyped real-world PIN, seen live
    ("41100112", True), # top of the range (8)
    ("2026", False),    # a bare 4-digit year must NOT be swept in
    ("3", False),       # a bare quantity
    ("411000121", False),  # 9 digits, past the top of the range
    ("411 001", True),  # spaces allowed, same as _looks_like_pin
    ("PIN 411001", False),
    ("", False),
])
def test_looks_like_attempted_pin(text, expected):
    assert adk_router._looks_like_attempted_pin(text) is expected


@pytest.fixture
def after_success(monkeypatch):
    """No booking/registration draft; weather just ANSWERED on the previous
    turn (last_was_weather, not awaiting_location) -- the success-path
    sticky state these 3 commits add. Same probe/dispatch doubles as the
    `waiting` fixture above."""
    calls = {"classifier": 0, "weather": [], "dispatched": [], "sessions": {}, "probed": []}
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "get_session", lambda key: {"awaiting_location": False, "last_was_weather": True})
    monkeypatch.setattr(adk_router, "update_session", lambda key, data: calls["sessions"].update({key: data}))

    def fake_run_weather(farmer_id, session_id, text, intent, include_audio, language, previous_asks=0):
        calls["weather"].append((text, previous_asks))
        return {"agent": "weather_alert"}

    monkeypatch.setattr(adk_router, "_run_weather", fake_run_weather)

    def fake_dispatch_query(farmer_id, session_id, text, language, include_audio, intent):
        calls["probed"].append(text)
        return {"agent": "query_agent", "result": {}}

    monkeypatch.setattr(adk_router, "_dispatch_query", fake_dispatch_query)

    for name in ("appointment", "add_animal"):
        def fake_handler(farmer_id, session_id, text, language, include_audio, intent, _name=name):
            calls["dispatched"].append((_name, text))
            return {"agent": _name}

        monkeypatch.setitem(adk_router._DISPATCH_TABLE, name, fake_handler)
    return calls


def _classifier_must_not_be_called(monkeypatch):
    async def fail(text):
        raise AssertionError(f"classifier must not be called for a bare attempted-PIN, got text={text!r}")
    monkeypatch.setattr(adk_router, "_classify_intent_async", fail)


def test_pin_after_successful_weather_turn_stays_with_weather(monkeypatch, after_success):
    """Real bug, forwarded by the farmer_chat owner: a farmer with a PIN on
    file gets a weather answer, then asks about a different PIN -- the
    success path used to clear every weather flag, so the bare PIN was
    classified from scratch, looked like a number, and reached query_agent
    ("I see you've entered a number (461111)...")."""
    _classifier_must_not_be_called(monkeypatch)
    result = adk_router.route_turn_adk("f-1", "s-1", "461111", "en-IN")
    assert result["agent"] == "weather_alert"
    assert after_success["weather"] == [("461111", 1)]


def test_mistyped_pin_after_successful_weather_turn_reaches_weather(monkeypatch, after_success):
    """Follow-up bug in the same report: a digit-short PIN ("46111", 5
    digits) failed the exact-6-digit check, fell through to the
    classifier, and also reached query_agent -- with no hint the farmer
    was one digit short. _looks_like_attempted_pin routes it to weather
    instead, which can actually say the PIN looks wrong."""
    _classifier_must_not_be_called(monkeypatch)
    result = adk_router.route_turn_adk("f-1", "s-1", "46111", "en-IN")
    assert result["agent"] == "weather_alert"
    assert after_success["weather"] == [("46111", 1)]


def test_place_name_after_successful_weather_turn_classified_and_probed(monkeypatch, after_success):
    """Third bug in the same report: "Pune" after a weather answer went to
    query_agent ("You have 2 animals on your farm.") because the success
    path never armed any sticky flag at all. Now it's classified (not a
    bare-PIN shortcut), probed for a real answer, and falls back to
    weather when the probe finds nothing -- same disambiguation the
    awaiting_location branch already had."""
    _classifier_says(monkeypatch, after_success, "query")
    result = adk_router.route_turn_adk("f-1", "s-1", "Pune", "en-IN")
    assert result["agent"] == "weather_alert"
    assert after_success["classifier"] == 1
    assert after_success["probed"] == ["Pune"]


def test_genuine_data_question_after_weather_still_reaches_query_agent(monkeypatch, after_success):
    """Must not regress the existing disambiguation: a real database
    question right after a weather turn still gets a real answer, not a
    nonsensical weather reply."""
    _classifier_says(monkeypatch, after_success, "query")
    monkeypatch.setattr(
        adk_router, "_dispatch_query",
        lambda farmer_id, session_id, text, language, include_audio, intent: {
            "agent": "query_agent",
            "result": {"sql": "SELECT COUNT(*) FROM animals", "data": {"count": 7}},
        },
    )
    result = adk_router.route_turn_adk("f-1", "s-1", "how many animals do I have", "en-IN")
    assert result["agent"] == "query_agent"
    assert after_success["weather"] == []


def test_different_request_after_weather_reaches_its_own_agent(monkeypatch, after_success):
    _classifier_says(monkeypatch, after_success, "add_animal")
    result = adk_router.route_turn_adk("f-1", "s-1", "register a goat", "en-IN")
    assert result["agent"] == "add_animal"
    assert after_success["weather"] == []


def test_last_was_weather_is_one_shot(monkeypatch, after_success):
    """Cleared the moment it's used, so weather is sticky for exactly the
    turn right after it spoke and never beyond."""
    _classifier_says(monkeypatch, after_success, "add_animal")
    adk_router.route_turn_adk("f-1", "s-1", "register a goat", "en-IN")
    key = adk_router._weather_session_key("f-1", "s-1")
    assert after_success["sessions"][key] == {"awaiting_location": False, "last_was_weather": False}


@pytest.mark.parametrize("had_error", [True, False])
def test_run_weather_arms_last_was_weather_on_both_outcomes(monkeypatch, had_error):
    """last_was_weather must be set whether the weather lookup succeeded or
    failed -- the whole point of the fix is that the success path, which
    previously cleared every flag, now arms this one too."""
    sessions = {}
    monkeypatch.setattr(adk_router, "update_session", lambda key, data: sessions.update({key: data}))
    monkeypatch.setattr(adk_router, "_reply_text", lambda agent, result: "")
    monkeypatch.setattr(adk_router, "_envelope", lambda *a, **k: {"agent": "weather_alert"})
    result_payload = {"error": "no_location"} if had_error else {}
    monkeypatch.setattr(
        adk_router, "process_weather_query_adk",
        lambda text, farmer_id, session_id=None: {"result": result_payload, "answer": "ok", "speech_text": None},
    )
    adk_router._run_weather("f-1", "s-1", "any text", "weather", False, "en-IN", previous_asks=0)
    key = adk_router._weather_session_key("f-1", "s-1")
    assert sessions[key]["last_was_weather"] is True


def test_booking_draft_takes_priority_over_last_was_weather(monkeypatch):
    """A bare number sent mid-booking must still belong to the booking --
    the draft-priority checks run before the weather-stickiness check is
    even looked at, so last_was_weather being True must not matter here."""
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: True)
    monkeypatch.setattr(adk_router, "get_session", lambda key: {"awaiting_location": False, "last_was_weather": True})
    captured = {}

    def fake_turn(farmer_id, session_id, text, language, include_audio=True):
        captured["text"] = text
        return {"response_text": "ok"}

    monkeypatch.setattr(adk_router._appointment_supervisor, "turn", fake_turn)
    result = adk_router.route_turn_adk("f-1", "s-1", "411001", "en-IN")
    assert result["agent"] == "appointment_supervisor"
    assert captured["text"] == "411001"
