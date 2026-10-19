"""A question for another agent asked in the middle of an open booking or
registration ("how many goats do I have?", "what's the weather in Pune
today?"). Found by evals layer 3 (en/hi/ta): the open flow took the
message, the question went unanswered, and "today" from the weather
question became the booking date.

The entities below have the shape the real extraction returned for these
turns (checked live with the debug script): the session cache repeats the
booking's own fields, intent stays CREATE_APPOINTMENT, and there is no
confirmation signal. The classifier (side_question) is a stub here, as the
router's own tests do for _classify_intent_async."""
from __future__ import annotations

import datetime as _dt

import pytest

from services.animal_registration.service import AnimalRegistrationSupervisor
from services.animal_registration import service as reg_service
from services.appointment_supervisor import service


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    # Session cache in memory, so these tests never write data/voice_sessions.
    monkeypatch.setenv("VOICE_SESSIONS_MEMORY", "1")
    monkeypatch.setattr(service, "process_query", lambda query, farmer_id: {"answer": None, "sql": None, "data": None})
    monkeypatch.setattr(service, "_today_ist", lambda: _dt.date(2026, 8, 20))
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [
        type("Animal", (), {"id": "a-gauri", "tag_or_name": "GAURI", "species": "goat"})(),
    ])
    monkeypatch.setattr(reg_service, "process_query", lambda query, farmer_id: {"answer": None, "sql": None, "data": None})
    monkeypatch.setattr(reg_service, "synthesize_speech", lambda text, target_lang=None: (None, None))


_BOOKING = {"animal_name": "GAURI", "issue": "fever", "symptoms": ["fever"], "date": "2026-08-22", "time": "10:00"}


def _extraction(*turns):
    """Fake process_text_input returning one result per call, in order."""
    results = iter(turns)

    def fake(text, session_id, pending_questions_override=None):
        return next(results)

    return fake


def _classifier(label, calls):
    def side_question(text):
        calls.append(text)
        return label

    return side_question


def _booked(monkeypatch, tmp_path, session, second):
    """First turn: a complete booking (read back for yes/no). Second turn: `second`."""
    monkeypatch.setattr(service, "process_text_input", _extraction(
        {"entities": dict(_BOOKING), "intent": "CREATE_APPOINTMENT"},
        second,
    ))
    supervisor = service.AppointmentSupervisor(tmp_path)
    first = supervisor.turn("f-001", session, "GAURI has fever, day after tomorrow 10 am", "en-IN")
    assert first["state"] == "CONFIRMING" and first["missing_fields"] == []
    return supervisor


def test_count_question_at_readback_is_answered_and_booking_kept(tmp_path, monkeypatch):
    calls = []
    supervisor = _booked(monkeypatch, tmp_path, "s-count", {
        "entities": {**_BOOKING, "animal_id": "a-gauri", "species": "goat"}, "intent": "CREATE_APPOINTMENT",
    })
    monkeypatch.setattr(service, "process_query", lambda query, farmer_id: {
        "answer": "You have 14 goats.", "sql": "SELECT COUNT(*) ...", "data": [{"n": 14}],
    })
    result = supervisor.turn("f-001", "s-count", "by the way, how many goats do I have?", "en-IN",
                             side_question=_classifier("query", calls))
    assert calls == ["by the way, how many goats do I have?"]
    assert result["side_question"] == "query"
    assert result["side_answer"] == "You have 14 goats."
    assert result["state"] == "CONFIRMING"
    assert result["draft"]["date"] == "2026-08-22" and result["draft"]["time"] == "10:00"
    assert "GAURI" in result["reminder"] and "still open" in result["reminder"]
    assert "response_audio_base64" not in result, "the router speaks the combined reply"


def test_weather_question_does_not_change_the_booking_date(tmp_path, monkeypatch):
    """Live: "what's the weather in Pune today?" came back with date=today
    and weather_location=Pune, and the booking moved to today."""
    calls = []
    supervisor = _booked(monkeypatch, tmp_path, "s-weather", {
        "entities": {**_BOOKING, "date": "2026-08-20", "weather_location": "Pune"}, "intent": "CREATE_APPOINTMENT",
    })
    result = supervisor.turn("f-001", "s-weather", "what's the weather in Pune today?", "en-IN",
                             side_question=_classifier("weather", calls))
    assert result["side_question"] == "weather"
    assert result["draft"]["date"] == "2026-08-22"
    assert result["draft"]["time"] == "10:00"
    saved = supervisor._load("s-weather", "f-001", "en-IN")
    assert saved["draft"]["date"] == "2026-08-22", "the stored draft must not change either"


def test_side_question_leaves_no_trace_in_the_session_cache(tmp_path, monkeypatch):
    """The extraction writes every turn into the session entity cache; a
    "today" left there would come back as the booking date next turn."""
    cache_key = "f-001:s-cache"
    service.clear_session(cache_key)
    service.update_session(cache_key, {"intent": "CREATE_APPOINTMENT", "entities": dict(_BOOKING)})

    def extraction_that_writes_the_cache(text, session_id, pending_questions_override=None):
        service.update_session(session_id, {"entities": {**_BOOKING, "date": "2026-08-20", "weather_location": "Pune"}})
        return {"entities": {**_BOOKING, "date": "2026-08-20", "weather_location": "Pune"}, "intent": "CREATE_APPOINTMENT"}

    supervisor = _booked(monkeypatch, tmp_path, "s-cache", {"entities": dict(_BOOKING)})
    service.update_session(cache_key, {"intent": "CREATE_APPOINTMENT", "entities": dict(_BOOKING)})
    monkeypatch.setattr(service, "process_text_input", extraction_that_writes_the_cache)
    supervisor.turn("f-001", "s-cache", "what's the weather in Pune today?", "en-IN",
                    side_question=_classifier("weather", []))
    entities = service.get_session(cache_key).get("entities") or {}
    assert entities.get("date") == "2026-08-22"
    assert "weather_location" not in entities
    service.clear_session(cache_key)


def test_ordinary_booking_turns_never_call_the_classifier(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "process_text_input", _extraction(
        {"entities": {"animal_name": "GAURI", "issue": "fever", "symptoms": ["fever"]}, "intent": "CREATE_APPOINTMENT"},
        {"entities": {"animal_name": "GAURI", "issue": "fever", "symptoms": ["fever"], "date": "2026-08-22", "time": "10:00"}},
        {"entities": dict(_BOOKING), "confirmation_signal": "yes"},
    ))
    supervisor = service.AppointmentSupervisor(tmp_path)
    side = _classifier("query", calls)
    supervisor.turn("f-001", "s-normal", "GAURI has fever", "en-IN", side_question=side)
    second = supervisor.turn("f-001", "s-normal", "day after tomorrow 10 am", "en-IN", side_question=side)
    third = supervisor.turn("f-001", "s-normal", "yes", "en-IN", side_question=side)
    assert calls == [], "a turn that brings booking details must not pay for a classifier call"
    assert second["draft"]["date"] == "2026-08-22"
    assert third["state"] == "READY_TO_SUBMIT"


def test_new_symptom_stays_in_the_booking_even_with_weather_words(tmp_path, monkeypatch):
    """"she is panting in this heat" brings a symptom: booking, not weather."""
    calls = []
    supervisor = _booked(monkeypatch, tmp_path, "s-heat", {
        "entities": {**_BOOKING, "symptoms": ["fever", "panting"]},
    })
    result = supervisor.turn("f-001", "s-heat", "she is panting in this heat", "en-IN",
                             side_question=_classifier("weather", calls))
    assert calls == []
    assert "side_question" not in result
    assert result["draft"]["symptoms"] == ["fever", "panting"]


def test_question_with_no_database_answer_carries_on_as_a_booking_turn(tmp_path, monkeypatch):
    calls = []
    supervisor = _booked(monkeypatch, tmp_path, "s-noanswer", {"entities": dict(_BOOKING)})
    result = supervisor.turn("f-001", "s-noanswer", "hmm", "en-IN", side_question=_classifier("query", calls))
    assert calls == ["hmm"]
    assert "side_question" not in result
    assert result["state"] == "CONFIRMING"
    assert result["draft"]["date"] == "2026-08-22"


def test_classifier_saying_appointment_carries_on_as_a_booking_turn(tmp_path, monkeypatch):
    """A changed date on a booking that already has one is checked (it may
    be "today" inside a question); the classifier keeps a real correction
    in the booking."""
    supervisor = _booked(monkeypatch, tmp_path, "s-fix", {"entities": {**_BOOKING, "date": "2026-08-23"}})
    result = supervisor.turn("f-001", "s-fix", "make it the 23rd", "en-IN", side_question=lambda text: None)
    assert "side_question" not in result
    assert result["draft"]["date"] == "2026-08-23"


def test_without_a_classifier_the_old_behaviour_is_unchanged(tmp_path, monkeypatch):
    supervisor = _booked(monkeypatch, tmp_path, "s-old", {"entities": {**_BOOKING, "date": "2026-08-20"}})
    result = supervisor.turn("f-001", "s-old", "what's the weather in Pune today?", "en-IN")
    assert "side_question" not in result
    assert result["draft"]["date"] == "2026-08-20", "old behaviour (kill switch off): the date is taken"


def test_reminder_names_what_the_booking_still_needs(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "process_text_input", _extraction(
        {"entities": {"animal_name": "GAURI", "issue": "fever", "symptoms": ["fever"], "date": "2026-08-22"}},
        {"entities": {"animal_name": "GAURI", "issue": "fever", "symptoms": ["fever"], "date": "2026-08-22"}},
    ))
    monkeypatch.setattr(service, "process_query", lambda query, farmer_id: {
        "answer": "You have 14 goats.", "sql": "SELECT 1", "data": [{"n": 14}],
    })
    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("f-001", "s-remind", "GAURI has fever, day after tomorrow", "en-IN")
    result = supervisor.turn("f-001", "s-remind", "how many goats do I have?", "hi-IN",
                             side_question=_classifier("query", []))
    assert result["reminder"].startswith("आपकी अपॉइंटमेंट बुकिंग अभी खुली है")
    assert result["reminder"].endswith(supervisor._message("hi-IN", "yes_missing", field=supervisor._message("hi-IN", "missing_time")))
    assert supervisor.reminder("f-001", "s-remind", "hi-IN") == result["reminder"]


# ---- registration ------------------------------------------------------------

def _registration(tmp_path, entities_by_call):
    sup = AnimalRegistrationSupervisor(tmp_path)
    calls = iter(entities_by_call)
    sup._extract = lambda draft, text: next(calls, {})
    return sup


def test_count_question_mid_registration_is_answered_and_draft_kept(tmp_path, monkeypatch):
    """Live: "how many sheep do I have?" mid-registration was ignored and
    the same question was asked again."""
    monkeypatch.setattr(reg_service, "process_query", lambda query, farmer_id: {
        "answer": "You have 7 sheep.", "sql": "SELECT COUNT(*) ...", "data": [{"n": 7}],
    })
    calls = []
    sup = _registration(tmp_path, [{"species": "goat", "sex": "male"}, {}])
    sup.turn("f-001", "r-count", "a male goat", include_audio=False, side_question=_classifier("query", calls))
    result = sup.turn("f-001", "r-count", "how many sheep do I have?", include_audio=False,
                      side_question=_classifier("query", calls))
    assert calls == ["how many sheep do I have?"]
    assert result["side_question"] == "query"
    assert result["side_answer"] == "You have 7 sheep."
    assert result["draft"] == {"species": "goat", "sex": "male"}
    assert result["reminder"].startswith("Your new animal registration is still open.")
    assert "response_audio_base64" not in result


def test_registration_answers_never_call_the_classifier(tmp_path, monkeypatch):
    calls = []
    sup = _registration(tmp_path, [{"species": "goat"}, {"sex": "female"}, {"field_unknown": True}])
    side = _classifier("query", calls)
    sup.turn("f-001", "r-normal", "goat", include_audio=False, side_question=side)
    sup.turn("f-001", "r-normal", "female", include_audio=False, side_question=side)
    sup.turn("f-001", "r-normal", "not sure", include_audio=False, side_question=side)
    assert calls == []


def test_registration_without_a_classifier_is_unchanged(tmp_path, monkeypatch):
    sup = _registration(tmp_path, [{"species": "goat"}, {}])
    sup.turn("f-001", "r-old", "goat", include_audio=False)
    result = sup.turn("f-001", "r-old", "how many sheep do I have?", include_audio=False)
    assert "side_question" not in result
    assert result["draft"] == {"species": "goat"}



def test_question_read_as_no_at_readback_also_gets_the_reminder(tmp_path, monkeypatch):
    """Live (te, ml): "which breed is GAURI?" at the readback came back with
    confirmation_signal="no"; the old probe answered it with no word about
    the open booking. From the router it now gets the reminder too."""
    supervisor = _booked(monkeypatch, tmp_path, "s-no-probe", {
        "entities": dict(_BOOKING), "confirmation_signal": "no",
    })
    monkeypatch.setattr(service, "process_query", lambda query, farmer_id: {
        "answer": "GAURI is a Sirohi goat.", "sql": "SELECT 1", "data": [{"breed": "Sirohi"}],
    })
    result = supervisor.turn("f-001", "s-no-probe", "which breed is GAURI?", "en-IN",
                             side_question=_classifier("query", []))
    assert result["side_question"] == "query"
    assert result["side_answer"] == "GAURI is a Sirohi goat."
    assert "still open" in result["reminder"]
    assert result["draft"]["date"] == "2026-08-22"
