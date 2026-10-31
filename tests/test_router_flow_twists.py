"""Router side of the layer-4 twists (see tests/test_flow_twists.py for the
supervisors): a cancel that also asks for something else, and a switch
between the booking and the registration flow. Classifier and agents are
stubbed, as in tests/test_router_side_questions.py."""
from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from services.chat_orchestrator import adk_router


@pytest.fixture
def booking_open(monkeypatch):
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: True)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(adk_router, "get_session", lambda key: {})
    monkeypatch.setattr(adk_router, "update_session", lambda key, data: None)
    for name in ("CHAT_SIDE_QUESTIONS", "CHAT_CANCEL_THEN_ROUTE", "CHAT_FLOW_SWITCH", "CHAT_RECENT_ANIMAL"):
        monkeypatch.delenv(name, raising=False)


def _classifier(monkeypatch, intent, calls=None):
    async def classify(text):
        if calls is not None:
            calls.append(text)
        if isinstance(intent, Exception):
            raise intent
        return intent

    monkeypatch.setattr(adk_router, "_classify_intent_async", classify)


_CANCELLED = {"state": "CANCELLED", "response_text": "The appointment draft was cancelled.",
              "response_audio_base64": None, "cancel_with_details": False}


def _booking_turns(monkeypatch, *results):
    seen = []
    results = iter(results)

    def turn(farmer_id, session_id, text, language, include_audio=True, side_question=None,
             recent_animal=None, fresh_start=False):
        seen.append({"fresh_start": fresh_start, "include_audio": include_audio})
        return next(results)

    monkeypatch.setattr(adk_router._appointment_supervisor, "turn", turn)
    return seen


def test_cancel_and_a_count_in_one_message_answers_both(monkeypatch, booking_open):
    _booking_turns(monkeypatch, dict(_CANCELLED))
    _classifier(monkeypatch, "query")
    monkeypatch.setattr(adk_router, "process_query_adk", lambda query, farmer_id, session_id=None, app_language=None: {
        "answer": "You have 9 cows.", "sql": "SELECT ...", "data": [{"n": 9}], "speech_text": "9 cows."})
    result = adk_router.route_turn_adk("f-001", "s-1", "cancel the booking and tell me how many cows I have", "en-IN")
    assert result["agent"] == "query_agent"
    assert result["reply_text"] == "The appointment draft was cancelled.\n\nYou have 9 cows."


def test_plain_cancel_gives_only_the_cancel(monkeypatch, booking_open):
    _booking_turns(monkeypatch, dict(_CANCELLED))
    _classifier(monkeypatch, "appointment")
    monkeypatch.setattr(adk_router, "process_query_adk", lambda query, farmer_id, session_id=None, app_language=None: {
        "answer": "What would you like to know?", "sql": None, "data": None})
    result = adk_router.route_turn_adk("f-001", "s-1", "cancel it", "en-IN")
    assert result["agent"] == "appointment_supervisor"
    assert result["reply_text"] == "The appointment draft was cancelled."


def test_cancel_classified_as_query_without_a_real_answer_gives_only_the_cancel(monkeypatch, booking_open):
    _booking_turns(monkeypatch, dict(_CANCELLED))
    _classifier(monkeypatch, "query")
    monkeypatch.setattr(adk_router, "process_query_adk", lambda query, farmer_id, session_id=None, app_language=None: {
        "answer": "What would you like to know?", "sql": None, "data": None})
    result = adk_router.route_turn_adk("f-001", "s-1", "leave it", "en-IN")
    assert result["reply_text"] == "The appointment draft was cancelled."


def test_cancel_with_new_booking_details_starts_the_new_booking(monkeypatch, booking_open):
    seen = _booking_turns(monkeypatch, {**_CANCELLED, "cancel_with_details": True},
                          {"state": "CONFIRMING", "response_text": "I understood: animal: MOTI; time: 11:00",
                           "response_audio_base64": None})
    _classifier(monkeypatch, "appointment")
    result = adk_router.route_turn_adk("f-001", "s-1", "forget all this, MOTI is limping, vet tomorrow 11 am", "en-IN")
    assert [s["fresh_start"] for s in seen] == [False, True]
    assert result["agent"] == "appointment_supervisor"
    assert result["reply_text"] == "The appointment draft was cancelled.\n\nI understood: animal: MOTI; time: 11:00"


def test_cancel_then_route_kill_switch(monkeypatch, booking_open):
    monkeypatch.setenv("CHAT_CANCEL_THEN_ROUTE", "0")
    _booking_turns(monkeypatch, dict(_CANCELLED))
    calls = []
    _classifier(monkeypatch, "query", calls)
    result = adk_router.route_turn_adk("f-001", "s-1", "cancel the booking and tell me how many cows I have", "en-IN")
    assert calls == []
    assert result["reply_text"] == "The appointment draft was cancelled."


def test_a_classifier_error_after_the_cancel_keeps_the_cancel_reply(monkeypatch, booking_open):
    _booking_turns(monkeypatch, dict(_CANCELLED))
    _classifier(monkeypatch, RuntimeError("no AWS"))
    result = adk_router.route_turn_adk("f-001", "s-1", "cancel and how many cows", "en-IN")
    assert result["reply_text"] == "The appointment draft was cancelled."


def test_booking_request_during_a_registration_switches_flow(monkeypatch, booking_open):
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: True)
    monkeypatch.setattr(adk_router._animal_registration_supervisor, "turn",
                        lambda farmer_id, session_id, text, language, include_audio=True, side_question=None:
                        {"side_question": "appointment", "reminder": "Registration still open.", "state": "COLLECTING"})
    closed = []
    monkeypatch.setattr(adk_router._animal_registration_supervisor, "confirm",
                        lambda farmer_id, session_id, response, include_audio=True:
                        closed.append(response) or {"state": "CANCELLED", "response_text": "Registration cancelled."})
    _booking_turns(monkeypatch, {"state": "CONFIRMING", "response_text": "I understood: animal: GAURI",
                                 "response_audio_base64": None})
    result = adk_router.route_turn_adk("f-001", "s-2", "leave that, GAURI has fever, vet tomorrow 10 am", "en-IN")
    assert closed == ["cancel"]
    assert result["agent"] == "appointment_supervisor"
    assert result["reply_text"] == "Registration cancelled.\n\nI understood: animal: GAURI"


def test_flow_switch_kill_switch_keeps_other_flow_labels_away(monkeypatch, booking_open):
    monkeypatch.setenv("CHAT_FLOW_SWITCH", "0")
    _classifier(monkeypatch, "add_animal")
    assert adk_router._side_question_label("I want to register a goat") is None
    monkeypatch.delenv("CHAT_FLOW_SWITCH")
    assert adk_router._side_question_label("I want to register a goat") == "add_animal"



def test_cancel_classified_as_the_booking_still_answers_a_real_question(monkeypatch, booking_open):
    """hi/ta/te: the classifier called "cancel the booking and tell me how
    many cows I have" a booking message, and the count was lost."""
    _booking_turns(monkeypatch, dict(_CANCELLED))
    _classifier(monkeypatch, "appointment")
    monkeypatch.setattr(adk_router, "process_query_adk", lambda query, farmer_id, session_id=None, app_language=None: {
        "answer": "You have 9 cows.", "sql": "SELECT COUNT(*) FROM animals WHERE species = 'cow'", "data": [{"n": 9}]})
    result = adk_router.route_turn_adk("f-001", "s-1", "booking cancel karo aur batao kitni gaay hain", "hi-IN")
    assert result["reply_text"] == "The appointment draft was cancelled.\n\nYou have 9 cows."


def test_cancel_my_booking_does_not_list_appointments(monkeypatch, booking_open):
    _booking_turns(monkeypatch, dict(_CANCELLED))
    _classifier(monkeypatch, "appointment")
    monkeypatch.setattr(adk_router, "process_query_adk", lambda query, farmer_id, session_id=None, app_language=None: {
        "answer": "You have 2 pending appointments.", "sql": "SELECT * FROM appointments", "data": [{"id": 1}]})
    result = adk_router.route_turn_adk("f-001", "s-1", "cancel my booking", "en-IN")
    assert result["reply_text"] == "The appointment draft was cancelled."



def _registration_open_then_cancelled(monkeypatch):
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: True)
    monkeypatch.setattr(adk_router._animal_registration_supervisor, "turn",
                        lambda farmer_id, session_id, text, language, include_audio=True, side_question=None:
                        {"state": "CANCELLED", "response_text": "Registration cancelled.", "response_audio_base64": None})
    monkeypatch.setattr(adk_router, "clear_session", lambda key: None)


def test_plain_cancel_of_a_registration_does_not_start_a_booking(monkeypatch, booking_open):
    """Tamil "no, cancel it" was classified as a booking and a booking started."""
    _registration_open_then_cancelled(monkeypatch)
    _classifier(monkeypatch, "appointment")
    monkeypatch.setattr(adk_router, "process_text_input", lambda text, session_id: {"entities": {}})
    monkeypatch.setattr(adk_router._appointment_supervisor, "turn", lambda *a, **k: pytest.fail("no booking"))
    result = adk_router.route_turn_adk("f-001", "s-3", "no, cancel it", "ta-IN")
    assert result["reply_text"] == "Registration cancelled."


def test_cancel_of_a_registration_with_booking_details_starts_the_booking(monkeypatch, booking_open):
    _registration_open_then_cancelled(monkeypatch)
    _classifier(monkeypatch, "appointment")
    monkeypatch.setattr(adk_router, "process_text_input", lambda text, session_id: {"entities": {"animal_name": "GAURI"}})
    _booking_turns(monkeypatch, {"state": "COLLECTING", "response_text": "I understood: animal: GAURI",
                                 "response_audio_base64": None})
    result = adk_router.route_turn_adk("f-001", "s-3", "cancel that, GAURI needs a vet", "en-IN")
    assert result["reply_text"] == "Registration cancelled.\n\nI understood: animal: GAURI"



def test_plain_cancel_is_not_answered_with_a_made_up_count(monkeypatch, booking_open):
    """ml: a plain "cancel" came back with "you have 53 animals"."""
    _booking_turns(monkeypatch, dict(_CANCELLED))
    _classifier(monkeypatch, "query")
    monkeypatch.setattr(adk_router, "process_query_adk", lambda query, farmer_id, session_id=None, app_language=None: {
        "answer": "NO_QUESTION", "sql": "SELECT COUNT(*) FROM animals", "data": [{"n": 53}]})
    result = adk_router.route_turn_adk("f-001", "s-1", "cancel", "ml-IN")
    assert result["reply_text"] == "The appointment draft was cancelled."
    