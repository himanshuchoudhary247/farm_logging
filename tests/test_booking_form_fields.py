"""The booking form's Book button and the symptom pills are read without the
model (services/appointment_supervisor/service.py _form_entities /
_symptom_pill_entities). Seen live: the model dropped the date and the
Hindi problem from the form message, and the farmer was asked again."""
from __future__ import annotations

import datetime as _dt

import pytest

from services.appointment_supervisor import service

FARMER = "24cdd479-7ce8-4951-91cb-e295f8a2b0ff"
SESSION = "24666232-6a23-4471-9fef-0c89e366ddbe"


@pytest.fixture
def booking(tmp_path, monkeypatch):
    # Form turns now also write the extraction cache (remember_entities):
    # keep it in this test's own folder.
    monkeypatch.setenv("VOICE_SESSIONS_DIR", str(tmp_path / "voice_sessions"))
    monkeypatch.setattr(service, "_try_mid_draft_escape", lambda text, farmer_id, session_id, language: None)
    monkeypatch.setattr(service, "_today_ist", lambda: _dt.date(2026, 11, 6))
    monkeypatch.setattr(service, "_now_ist", lambda: _dt.datetime(2026, 11, 6, 9, 0))
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "animals_for_farmer",
                        lambda farmer_id: [type("Animal", (), {"id": "a-9", "tag_or_name": "demo tanay"})()])
    sup = service.AppointmentSupervisor(tmp_path)
    sup.calls = []
    sup.replies = []

    def extract(text, session_id, pending_questions_override=None):
        sup.calls.append(text)
        return sup.replies.pop(0) if sup.replies else {"entities": {}}

    monkeypatch.setattr(service, "process_text_input", extract)
    return sup


@pytest.mark.parametrize("language,problem", [("hi-IN", "बुखार"), ("en-IN", "Fever"), ("ta-IN", "காய்ச்சல்")])
def test_the_form_message_fills_every_field_without_the_model(booking, language, problem):
    # Exactly what the app sends when Book is tapped (flokiquser lib/a2ui.ts actionToChatText).
    text = f"animal: demo tanay; problem: {problem}; date: 2026-11-07; time: 12:12"
    r = booking.turn(FARMER, SESSION, text, language)
    assert booking.calls == [], "no model call for the form"
    assert r["draft"]["date"] == "2026-11-07" and r["draft"]["time"] == "12:12"
    assert r["draft"]["issue"] == "fever" and r["draft"]["symptoms"] == ["fever"]
    assert r["draft"]["animal_identifier"] == "demo tanay"
    assert r["state"] == "CONFIRMING" and r["missing_fields"] == []


def test_the_form_with_several_problems_and_a_typed_one(booking):
    r = booking.turn(FARMER, SESSION, "animal: demo tanay; problem: Fever, Limping; other problem: cough; "
                                      "date: 2026-11-07; time: 10:00", "en-IN")
    assert r["draft"]["symptoms"] == ["fever", "limping", "cough"]
    assert booking.calls == []


def test_a_past_date_from_the_form_is_still_refused(booking):
    r = booking.turn(FARMER, SESSION, "animal: demo tanay; problem: Fever; date: 2026-11-01; time: 10:00", "en-IN")
    assert "date" not in r["draft"] or not r["draft"].get("date")
    assert "date" in r["missing_fields"]


def test_a_tapped_symptom_pill_answers_the_problem_question_without_the_model(booking):
    booking.replies.append({"entities": {"animal_name": "demo tanay", "date": "2026-11-07", "time": "12:12"}})
    first = booking.turn(FARMER, SESSION, "book demo tanay tomorrow 12:12", "hi-IN")
    assert first["missing_fields"] == ["issue"]
    calls = len(booking.calls)
    r = booking.turn(FARMER, SESSION, "बुखार", "hi-IN")
    assert len(booking.calls) == calls
    assert r["draft"]["issue"] == "fever" and r["missing_fields"] == []


@pytest.mark.parametrize("text", ["my cow has fever since 2 days", "बुखार है", "kal subah 10 baje",
                                  "animal: demo tanay and fever", "note: something",
                                  "animal: demo tanay; note: fever"])
def test_anything_else_goes_to_the_model_as_before(booking, text):
    booking.turn(FARMER, SESSION, text, "hi-IN")
    assert booking.calls == [text]


def test_the_same_problem_from_the_pill_and_the_box_is_kept_once(booking):
    # Seen live: "demo-1233 · पानी नहीं पी रहा · not drinking" -> "not drinking, not drinking".
    r = booking.turn(FARMER, SESSION, "animal: demo tanay; problem: पानी नहीं पी रहा; other problem: not drinking; "
                                      "date: 2026-11-07; time: 12:12", "hi-IN")
    assert r["draft"]["symptoms"] == ["not drinking"] and r["draft"]["issue"] == "not drinking"


@pytest.mark.parametrize("language", ["hi-IN", "ta-IN", "en-IN"])
def test_the_form_shows_a_stored_problem_as_its_pill_not_in_the_other_box(language):
    from services.a2ui.booking_widget import build_booking_widget

    choices = service._symptom_options(language)["choices"]
    result = {"state": "COLLECTING", "missing_fields": ["date"],
              "draft": {"animal_identifier": "demo tanay", "issue": "not drinking", "symptoms": ["not drinking"]}}
    messages = build_booking_widget(result, language, [], choices)
    data = next(m["updateDataModel"]["value"] for m in messages if "updateDataModel" in m)
    assert data["problem"] == [choices[service._SYMPTOM_KEYS.index("not drinking")]]
    assert data["other_problem"] == ""


def test_the_form_keeps_a_typed_problem_in_the_box():
    from services.a2ui.booking_widget import build_booking_widget

    choices = service._symptom_options("hi-IN")["choices"]
    result = {"state": "COLLECTING", "missing_fields": ["date"],
              "draft": {"animal_identifier": "demo tanay", "issue": "fever, cough"}}
    data = next(m["updateDataModel"]["value"] for m in build_booking_widget(result, "hi-IN", [], choices)
                if "updateDataModel" in m)
    assert data["problem"] == [choices[service._SYMPTOM_KEYS.index("fever")]] and data["other_problem"] == "cough"


# ------------------------------------------------------------------ review fixes

@pytest.fixture
def booking_with_cache(tmp_path, monkeypatch):
    """The real extraction step (process_text_input and its per-session
    entity cache); only the model call itself is stubbed."""
    from services.voice_agent import orchestrator

    monkeypatch.setenv("VOICE_SESSIONS_DIR", str(tmp_path / "voice_sessions"))
    monkeypatch.setattr(service, "_try_mid_draft_escape", lambda text, farmer_id, session_id, language: None)
    monkeypatch.setattr(service, "_today_ist", lambda: _dt.date(2026, 11, 6))
    monkeypatch.setattr(service, "_now_ist", lambda: _dt.datetime(2026, 11, 6, 9, 0))
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "animals_for_farmer",
                        lambda farmer_id: [type("Animal", (), {"id": "a-9", "tag_or_name": "demo tanay"})()])
    replies = []
    monkeypatch.setattr(orchestrator, "call_bedrock", lambda text, context=None: replies.pop(0) if replies else {})
    sup = service.AppointmentSupervisor(tmp_path)
    sup.replies = replies
    return sup


def test_a_date_changed_in_the_form_is_not_brought_back_by_a_later_model_turn(booking_with_cache):
    """Deep review repro: model turn sets the date -> the form changes it
    (no model) -> a later model turn must not bring the old date back."""
    sup = booking_with_cache
    sup.replies.append({"intent": "CREATE_APPOINTMENT", "confidence": 0.9,
                        "entities": {"animal_name": "demo tanay", "issue": "fever", "date": "2026-11-07"}})
    sup.turn(FARMER, SESSION, "demo tanay has fever, tomorrow", "en-IN")
    r = sup.turn(FARMER, SESSION, "animal: demo tanay; problem: Fever; date: 2026-11-09", "en-IN")
    assert r["draft"]["date"] == "2026-11-09"
    sup.replies.append({"intent": "CREATE_APPOINTMENT", "confidence": 0.9, "entities": {"time": "11:00"}})
    r = sup.turn(FARMER, SESSION, "at 11", "en-IN")
    assert r["draft"]["time"] == "11:00"
    assert r["draft"]["date"] == "2026-11-09", "the form's date stays"


def test_an_empty_field_does_not_send_the_whole_form_to_the_model(booking):
    r = booking.turn(FARMER, SESSION, "animal: demo tanay; problem: Fever; other problem: ; date: 2026-11-07; "
                                      "time: 12:12", "en-IN")
    assert booking.calls == []
    assert r["draft"]["date"] == "2026-11-07" and r["draft"]["symptoms"] == ["fever"]


def test_a_semicolon_typed_in_the_other_problem_box_keeps_the_form(booking):
    r = booking.turn(FARMER, SESSION, "animal: demo tanay; problem: Fever; other problem: limping; not eating; "
                                      "date: 2026-11-07; time: 12:12", "en-IN")
    assert booking.calls == []
    assert r["draft"]["symptoms"] == ["fever", "limping; not eating"]
    assert r["draft"]["date"] == "2026-11-07" and r["draft"]["time"] == "12:12"


def test_the_log_says_which_form_values_were_kept_and_which_were_refused(booking, caplog):
    with caplog.at_level("INFO"):
        booking.turn(FARMER, SESSION, "animal: demo tanay; problem: Fever; date: 07/11/2026; time: 12:12", "en-IN")
    assert "appointment form/pill parsed without the model" in caplog.text and "source=app" in caplog.text
    assert "dropped=date" in caplog.text
    assert "appointment date rejected (not a date): '07/11/2026'" in caplog.text


def test_a_typed_look_alike_is_read_but_logged_as_typed(booking, caplog):
    with caplog.at_level("INFO"):
        booking.turn(FARMER, SESSION, "Date: 2026-11-07;animal: demo tanay", "en-IN")
    assert booking.calls == []
    assert "source=typed" in caplog.text


def test_a_time_that_is_not_hh_mm_is_logged(booking, caplog):
    with caplog.at_level("INFO"):
        booking.turn(FARMER, SESSION, "animal: demo tanay; problem: Fever; date: 2026-11-07; time: 10 baje", "en-IN")
    assert "appointment time rejected (not HH:MM): '10 baje'" in caplog.text
