"""The farmer changes their mind in the middle of a flow (found by evals
layer 4, all 7 languages):
- a "yes"/"no" that also gives a new value is a correction, never a
  confirmation of the old value (APPOINTMENT_CORRECTION_WITH_YES);
- a question about ANOTHER animal does not replace the booked animal
  (APPOINTMENT_OTHER_ANIMAL_QUESTION_CHECK);
- a cancel that also asks for something else is followed by that request
  (CHAT_CANCEL_THEN_ROUTE);
- a booking request during a registration (and the reverse) switches flow
  (CHAT_FLOW_SWITCH).

The fake extraction below behaves like the real process_text_input: it
merges this turn's values into the session entity cache and returns the
merged entities, so values from earlier turns come back on every turn."""
from __future__ import annotations

import datetime as _dt

import pytest

from services.animal_registration import service as reg_service
from services.appointment_supervisor import service
from services.voice_agent.session_store import get_session, update_session

_ANIMALS = [type("Animal", (), {"id": f"a-{n.lower()}", "tag_or_name": n, "species": "goat"})()
            for n in ("GAURI", "MOTI", "KAALI")]
_BOOKING = {"animal_name": "GAURI", "issue": "fever", "symptoms": ["fever"], "date": "2026-08-22", "time": "10:00"}


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("VOICE_SESSIONS_MEMORY", "1")
    for name in ("APPOINTMENT_CORRECTION_WITH_YES", "APPOINTMENT_OTHER_ANIMAL_QUESTION_CHECK"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(service, "process_query", lambda query, farmer_id: {"answer": None, "sql": None, "data": None})
    monkeypatch.setattr(service, "_today_ist", lambda: _dt.date(2026, 8, 20))
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: _ANIMALS)
    monkeypatch.setattr(reg_service, "process_query", lambda query, farmer_id: {"answer": None, "sql": None, "data": None})
    monkeypatch.setattr(reg_service, "synthesize_speech", lambda text, target_lang=None: (None, None))


def _extraction(monkeypatch, *turns):
    """One (llm_entities, confirmation_signal) per call, merged into the
    session cache the way process_text_input does it."""
    results = iter(turns)

    def fake(text, session_id, pending_questions_override=None):
        llm_entities, signal = next(results)
        entities = dict(get_session(session_id).get("entities") or {})
        entities.update(llm_entities)
        update_session(session_id, {"entities": entities, "intent": "CREATE_APPOINTMENT"})
        return {"entities": entities, "intent": "CREATE_APPOINTMENT", "confirmation_signal": signal}

    monkeypatch.setattr(service, "process_text_input", fake)


def _readback(monkeypatch, tmp_path, session, *later):
    _extraction(monkeypatch, (dict(_BOOKING), None), *later)
    supervisor = service.AppointmentSupervisor(tmp_path)
    first = supervisor.turn("f-001", session, "GAURI has fever, day after tomorrow 10 am", "en-IN")
    assert first["state"] == "CONFIRMING" and first["missing_fields"] == []
    return supervisor


# ---- a "yes" that carries a new value ----------------------------------------

def test_going_back_to_the_first_date_with_a_yes_is_applied_not_confirmed(tmp_path, monkeypatch):
    supervisor = _readback(monkeypatch, tmp_path, "s-back",
                           ({"date": "2026-08-23"}, "no"),   # "no, make it the 23rd"
                           ({"date": "2026-08-22"}, "yes"))  # "no wait, the 22nd was right, keep it"
    changed = supervisor.turn("f-001", "s-back", "no, make it the 23rd", "en-IN")
    assert changed["draft"]["date"] == "2026-08-23"
    back = supervisor.turn("f-001", "s-back", "no wait, the 22nd was right, keep it", "en-IN")
    assert back["state"] == "CONFIRMING", "read back again, not 'would you like to submit?'"
    assert back["draft"]["date"] == "2026-08-22"
    assert "2026-08-22" in back["response_text"]


def test_a_plain_yes_still_moves_on(tmp_path, monkeypatch):
    """The cache repeats every booking value on every turn; that must not
    look like a change, or the readback would repeat forever."""
    supervisor = _readback(monkeypatch, tmp_path, "s-yes", ({}, "yes"))
    result = supervisor.turn("f-001", "s-yes", "yes", "en-IN")
    assert result["state"] == "READY_TO_SUBMIT"


def test_a_changed_time_at_submit_is_read_back_not_submitted(tmp_path, monkeypatch):
    supervisor = _readback(monkeypatch, tmp_path, "s-submit", ({}, "yes"), ({"time": "16:00"}, "yes"))
    assert supervisor.turn("f-001", "s-submit", "yes", "en-IN")["state"] == "READY_TO_SUBMIT"
    result = supervisor.turn("f-001", "s-submit", "yes, but make it 4 pm", "en-IN")
    assert result["state"] == "CONFIRMING"
    assert result["draft"]["time"] == "16:00"
    assert not supervisor._load("s-submit", "f-001", "en-IN").get("submitted")


def test_correction_with_yes_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("APPOINTMENT_CORRECTION_WITH_YES", "0")
    supervisor = _readback(monkeypatch, tmp_path, "s-off", ({"date": "2026-08-23"}, "yes"))
    result = supervisor.turn("f-001", "s-off", "yes, the 23rd", "en-IN")
    assert result["state"] == "READY_TO_SUBMIT", "old behaviour: the yes wins"


# ---- cancel with new details --------------------------------------------------

def test_cancel_says_whether_the_message_also_brought_a_new_booking(tmp_path, monkeypatch):
    supervisor = _readback(monkeypatch, tmp_path, "s-c1",
                           ({"animal_name": "MOTI", "issue": "limping", "symptoms": ["limping"], "time": "11:00"}, "cancel"))
    restart = supervisor.turn("f-001", "s-c1", "forget all this, MOTI is limping, vet at 11 am", "en-IN")
    assert restart["state"] == "CANCELLED" and restart["cancel_with_details"] is True

    supervisor = _readback(monkeypatch, tmp_path, "s-c2", ({}, "cancel"))
    plain = supervisor.turn("f-001", "s-c2", "cancel it", "en-IN")
    assert plain["state"] == "CANCELLED" and plain["cancel_with_details"] is False


def test_fresh_start_does_not_cancel_the_new_booking_again(tmp_path, monkeypatch):
    new = {"animal_name": "MOTI", "issue": "limping", "symptoms": ["limping"], "date": "2026-08-21", "time": "11:00"}
    supervisor = _readback(monkeypatch, tmp_path, "s-fresh", (new, "cancel"), (new, "cancel"))
    supervisor.turn("f-001", "s-fresh", "forget all this, MOTI is limping, vet tomorrow 11 am", "en-IN")
    result = supervisor.turn("f-001", "s-fresh", "forget all this, MOTI is limping, vet tomorrow 11 am", "en-IN",
                             fresh_start=True)
    assert result["state"] != "CANCELLED"
    assert result["draft"]["animal_identifier"] == "MOTI"
    assert result["draft"]["time"] == "11:00"


# ---- a question about another animal -----------------------------------------

def _classifier(label, calls):
    def side_question(text):
        calls.append(text)
        return label
    return side_question


def test_question_about_another_animal_keeps_the_booked_animal(tmp_path, monkeypatch):
    calls = []
    supervisor = _readback(monkeypatch, tmp_path, "s-q", ({"animal_name": "KAALI"}, None))
    monkeypatch.setattr(service, "process_query", lambda query, farmer_id: {
        "answer": "KAALI is a Jamunapari goat.", "sql": "SELECT ...", "data": [{"breed": "Jamunapari"}]})
    result = supervisor.turn("f-001", "s-q", "which breed is KAALI?", "en-IN", side_question=_classifier("query", calls))
    assert calls == ["which breed is KAALI?"]
    assert result["side_question"] == "query"
    assert result["side_answer"] == "KAALI is a Jamunapari goat."
    draft = supervisor._load("s-q", "f-001", "en-IN")
    assert draft["draft"]["animal_identifier"] == "GAURI"
    assert get_session("f-001:s-q")["entities"]["animal_name"] == "GAURI", "the question left no trace in the cache"


def test_a_real_change_of_animal_still_changes_it(tmp_path, monkeypatch):
    supervisor = _readback(monkeypatch, tmp_path, "s-chg", ({"animal_name": "KAALI"}, None))
    result = supervisor.turn("f-001", "s-chg", "not GAURI, it is KAALI", "en-IN",
                             side_question=_classifier("appointment", []))
    assert result["draft"]["animal_identifier"] == "KAALI"


def test_other_animal_question_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("APPOINTMENT_OTHER_ANIMAL_QUESTION_CHECK", "0")
    calls = []
    supervisor = _readback(monkeypatch, tmp_path, "s-aq0", ({"animal_name": "KAALI"}, None))
    result = supervisor.turn("f-001", "s-aq0", "which breed is KAALI?", "en-IN", side_question=_classifier("query", calls))
    assert calls == [], "old behaviour: no classifier call"
    assert result["draft"]["animal_identifier"] == "KAALI"


def test_registration_request_during_a_booking_is_handed_to_the_router(tmp_path, monkeypatch):
    supervisor = _readback(monkeypatch, tmp_path, "s-reg", ({}, None))
    result = supervisor.turn("f-001", "s-reg", "I want to register a new goat", "en-IN",
                             side_question=_classifier("add_animal", []))
    assert result["side_question"] == "add_animal"
    assert supervisor._load("s-reg", "f-001", "en-IN")["draft"]["animal_identifier"] == "GAURI"


def test_booking_request_during_a_registration_is_handed_to_the_router(tmp_path, monkeypatch):
    monkeypatch.setattr(reg_service.AnimalRegistrationSupervisor, "_extract", lambda self, draft, text: {})
    supervisor = reg_service.AnimalRegistrationSupervisor(tmp_path)
    result = supervisor.turn("f-001", "r-1", "leave that, GAURI has fever, I need a vet tomorrow", "en-IN",
                             side_question=_classifier("appointment", []))
    assert result["side_question"] == "appointment"
