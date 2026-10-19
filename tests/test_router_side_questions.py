"""Router side of side questions during an open booking/registration (see
tests/test_side_questions.py for the supervisors' side): the open flow
hands back a weather/query question untouched, and the router answers it
and adds the flow's reminder."""
from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from services.chat_orchestrator import adk_router


@pytest.fixture
def booking_open(monkeypatch):
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: True)
    monkeypatch.setattr(adk_router, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(adk_router, "get_session", lambda key: {})
    monkeypatch.delenv("CHAT_SIDE_QUESTIONS", raising=False)


def _turn_returning(result, seen):
    def turn(farmer_id, session_id, text, language, include_audio=True, side_question=None):
        seen["side_question"] = side_question
        return result

    return turn


def test_weather_question_gets_weather_reply_then_booking_reminder(monkeypatch, booking_open):
    seen = {}
    monkeypatch.setattr(adk_router._appointment_supervisor, "turn", _turn_returning(
        {"side_question": "weather", "reminder": "Your appointment booking is still open: animal: GAURI",
         "state": "CONFIRMING", "response_text": "Your appointment booking is still open: animal: GAURI"},
        seen,
    ))
    weather_calls = []

    def fake_run_weather(farmer_id, session_id, text, intent, include_audio, language, previous_asks=0):
        weather_calls.append((text, include_audio))
        return {"agent": "weather_alert", "reply_text": "Pune: 33°C, no rain."}

    monkeypatch.setattr(adk_router, "_run_weather", fake_run_weather)
    result = adk_router.route_turn_adk("f-001", "s-1", "what's the weather in Pune today?", "en-IN")
    assert seen["side_question"] is not None
    assert weather_calls == [("what's the weather in Pune today?", False)], "audio is made once, for the combined reply"
    assert result["agent"] == "appointment_supervisor"
    assert result["intent"] == "weather"
    assert result["reply_text"] == "Pune: 33°C, no rain.\n\nYour appointment booking is still open: animal: GAURI"
    assert result["result"]["response_text"] == result["reply_text"]


def test_query_question_uses_the_answer_the_booking_already_got(monkeypatch, booking_open):
    monkeypatch.setattr(adk_router._appointment_supervisor, "turn", _turn_returning(
        {"side_question": "query", "side_answer": "You have 14 goats.", "reminder": "Booking still open.",
         "state": "CONFIRMING"},
        {},
    ))
    monkeypatch.setattr(adk_router, "_run_weather", lambda *a, **k: pytest.fail("weather must not run"))
    result = adk_router.route_turn_adk("f-001", "s-1", "how many goats do I have?", "en-IN")
    assert result["intent"] == "query"
    assert result["reply_text"] == "You have 14 goats.\n\nBooking still open."


def test_ordinary_booking_turn_is_returned_as_before(monkeypatch, booking_open):
    monkeypatch.setattr(adk_router._appointment_supervisor, "turn", _turn_returning(
        {"response_text": "I understood: date: 2026-10-20", "state": "CONFIRMING", "response_audio_base64": None}, {},
    ))
    result = adk_router.route_turn_adk("f-001", "s-1", "day after tomorrow", "en-IN")
    assert result["intent"] is None
    assert result["reply_text"] == "I understood: date: 2026-10-20"


def test_pin_answers_the_waiting_weather_not_the_booking(monkeypatch, booking_open):
    """The weather agent asked for a PIN during a booking; the PIN must go
    to weather (it used to go to the booking)."""
    monkeypatch.setattr(adk_router, "get_session", lambda key: {"awaiting_location": True, "asks": 1})
    monkeypatch.setattr(adk_router._appointment_supervisor, "turn",
                        lambda *a, **k: pytest.fail("the PIN must not reach the booking"))
    monkeypatch.setattr(adk_router._appointment_supervisor, "reminder",
                        lambda farmer_id, session_id, language="en-IN": "Booking still open.")
    asks = []

    def fake_run_weather(farmer_id, session_id, text, intent, include_audio, language, previous_asks=0):
        asks.append(previous_asks)
        return {"agent": "weather_alert", "reply_text": "Pune: 33°C."}

    monkeypatch.setattr(adk_router, "_run_weather", fake_run_weather)
    result = adk_router.route_turn_adk("f-001", "s-1", "411001", "en-IN")
    assert asks == [1]
    assert result["intent"] == "weather"
    assert result["reply_text"] == "Pune: 33°C.\n\nBooking still open."


def test_pin_with_no_weather_waiting_goes_to_the_booking(monkeypatch, booking_open):
    seen = {}
    monkeypatch.setattr(adk_router._appointment_supervisor, "turn", _turn_returning(
        {"response_text": "booking reply", "state": "COLLECTING", "response_audio_base64": None}, seen,
    ))
    result = adk_router.route_turn_adk("f-001", "s-1", "411001", "en-IN")
    assert result["reply_text"] == "booking reply"


def test_kill_switch_sends_every_turn_to_the_open_flow_as_before(monkeypatch, booking_open):
    monkeypatch.setenv("CHAT_SIDE_QUESTIONS", "0")
    monkeypatch.setattr(adk_router, "get_session", lambda key: {"awaiting_location": True, "asks": 1})
    monkeypatch.setattr(
        adk_router._appointment_supervisor, "turn",
        lambda farmer_id, session_id, text, language, include_audio=True: {"response_text": "old path", "response_audio_base64": None},
    )
    result = adk_router.route_turn_adk("f-001", "s-1", "411001", "en-IN")
    assert result["reply_text"] == "old path"


def test_side_question_respects_the_channel_allowed_intents(monkeypatch, booking_open):
    """A channel limited to bookings (allowed_intents) must not get weather
    answers through the side-question path."""
    async def classifier_says_weather(text):
        return "weather"

    monkeypatch.setattr(adk_router, "_classify_intent_async", classifier_says_weather)
    labels = []

    def turn(farmer_id, session_id, text, language, include_audio=True, side_question=None):
        labels.append(side_question(text))
        return {"response_text": "booking reply", "response_audio_base64": None}

    monkeypatch.setattr(adk_router._appointment_supervisor, "turn", turn)
    adk_router.route_turn_adk("f-001", "s-1", "weather?", "en-IN", allowed_intents={"appointment"})
    assert labels == [None]


def test_registration_side_question_uses_the_registration_reminder(monkeypatch):
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: True)
    monkeypatch.setattr(adk_router, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(adk_router, "get_session", lambda key: {})
    monkeypatch.setattr(adk_router._animal_registration_supervisor, "turn", _turn_returning(
        {"side_question": "query", "side_answer": "You have 7 sheep.",
         "reminder": "Your new animal registration is still open. Please provide the ID.", "state": "COLLECTING"},
        {},
    ))
    result = adk_router.route_turn_adk("f-001", "s-2", "how many sheep do I have?", "en-IN")
    assert result["agent"] == "animal_registration"
    assert result["reply_text"] == "You have 7 sheep.\n\nYour new animal registration is still open. Please provide the ID."
    