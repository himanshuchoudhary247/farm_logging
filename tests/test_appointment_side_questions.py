"""A question about something else in the middle of a booking, and "show me
my animals" while the animal is asked.

process_text_input is faked the way the real one behaves: it merges this
turn's values into the extraction session (update_session) and returns the
cumulative entities, plus the per-message side_question / wants_options
flags call_bedrock now returns."""
from __future__ import annotations

import datetime as _dt

import pytest

from services.appointment_supervisor import service
from services.common.draft_supervisor import SUPPORTED_LANGUAGES
from services.llm_service import bedrock_adapter
from services.voice_agent import session_store

FARMER = "demo-farmer"
ANIMALS = [type("Animal", (), {"id": f"a-{i}", "tag_or_name": name})() for i, name in enumerate(["Lakshmi", "Kaali", "Moti"])]
WEATHER_ANSWER = {"intent": "weather", "answer": "No rain is expected today."}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_SESSIONS_DIR", str(tmp_path / "voice_sessions"))
    monkeypatch.delenv("APPOINTMENT_SIDE_QUESTION_CHECK", raising=False)
    monkeypatch.setattr(service, "_today_ist", lambda: _dt.date(2026, 8, 20))
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: list(ANIMALS))
    monkeypatch.setattr(service, "_try_mid_draft_escape", lambda text, farmer_id, session_id, language: None)


def _fake_extraction(monkeypatch, turns):
    """turns: one (entities_this_turn, flags) pair per call, in order."""
    calls = iter(turns)

    def fake(text, session_id, pending_questions_override=None):
        new, flags = next(calls)
        session = session_store.get_session(session_id)
        merged = {**(session.get("entities") or {}), **new}
        session_store.update_session(session_id, {"intent": "CREATE_APPOINTMENT", "entities": merged, "pending_questions": []})
        return {"entities": merged, "side_question": False, "wants_options": False, **flags}

    monkeypatch.setattr(service, "process_text_input", fake)


def _count_escape(monkeypatch, answer):
    calls = []

    def fake(text, farmer_id, session_id, language):
        calls.append(text)
        return answer

    monkeypatch.setattr(service, "_try_mid_draft_escape", fake)
    return calls


def _start_booking(sup, session, language="en-IN"):
    """Animal and issue given; the date is asked next."""
    first = sup.turn(FARMER, session, "Lakshmi has fever", language, include_audio=False)
    assert first["missing_fields"] == ["date", "time"]
    return first


def test_weather_question_while_date_asked_is_answered_and_date_not_taken(tmp_path, monkeypatch):
    _fake_extraction(monkeypatch, [
        ({"animal_name": "Lakshmi", "issue": "fever"}, {}),
        ({"date": "today"}, {"side_question": True}),
    ])
    escape_calls = _count_escape(monkeypatch, WEATHER_ANSWER)
    sup = service.AppointmentSupervisor(tmp_path)
    _start_booking(sup, "s-date")
    before = session_store.get_session(f"{FARMER}:s-date")["entities"]

    out = sup.turn(FARMER, "s-date", "Wait, what is the weather today?", "en-IN", include_audio=False)

    assert "date" not in out["draft"]
    assert out["missing_fields"] == ["date", "time"]
    assert out["response_text"].startswith(WEATHER_ANSWER["answer"])
    assert out["response_text"].endswith("Please provide the preferred appointment date.")
    # The app shows prompt_text in the bubble: it must carry the answer too.
    assert out["prompt_text"] == out["response_text"]
    assert len(escape_calls) == 1
    # The extraction session forgets the side question too, so "today" does
    # not come back on the next turn.
    assert session_store.get_session(f"{FARMER}:s-date")["entities"] == before


def test_side_question_leaves_no_value_for_the_next_turn(tmp_path, monkeypatch):
    _fake_extraction(monkeypatch, [
        ({"animal_name": "Lakshmi", "issue": "fever"}, {}),
        ({"date": "today"}, {"side_question": True}),
        ({"date": "2026-08-25"}, {}),
    ])
    _count_escape(monkeypatch, WEATHER_ANSWER)
    sup = service.AppointmentSupervisor(tmp_path)
    _start_booking(sup, "s-next")
    sup.turn(FARMER, "s-next", "Wait, what is the weather today?", "en-IN", include_audio=False)

    out = sup.turn(FARMER, "s-next", "25 August", "en-IN", include_audio=False)
    assert out["draft"]["date"] == "2026-08-25"
    assert out["missing_fields"] == ["time"]


def test_weather_question_while_time_asked_does_not_set_the_time(tmp_path, monkeypatch):
    _fake_extraction(monkeypatch, [
        ({"animal_name": "Lakshmi", "issue": "fever"}, {}),
        ({"date": "2026-08-25"}, {}),
        ({"time": "19:00"}, {"side_question": True}),
    ])
    _count_escape(monkeypatch, WEATHER_ANSWER)
    sup = service.AppointmentSupervisor(tmp_path)
    _start_booking(sup, "s-time")
    sup.turn(FARMER, "s-time", "25 August", "en-IN", include_audio=False)

    out = sup.turn(FARMER, "s-time", "Will it rain at 7 PM?", "en-IN", include_audio=False)
    assert "time" not in out["draft"]
    assert out["missing_fields"] == ["time"]
    assert out["response_text"].endswith("Please provide the preferred appointment time.")
    assert out["prompt_text"].startswith(WEATHER_ANSWER["answer"])


def test_marked_side_question_without_an_answer_keeps_the_old_behaviour(tmp_path, monkeypatch):
    # The model marked "today?" as a side question, but nothing could
    # answer it: the value is kept, as before, and the escape is not asked
    # a second time for the same text.
    _fake_extraction(monkeypatch, [
        ({"animal_name": "Lakshmi", "issue": "fever"}, {}),
        ({"date": "today"}, {"side_question": True}),
    ])
    escape_calls = _count_escape(monkeypatch, None)
    sup = service.AppointmentSupervisor(tmp_path)
    _start_booking(sup, "s-fallback")

    out = sup.turn(FARMER, "s-fallback", "today?", "en-IN", include_audio=False)
    assert out["draft"]["date"] == "today"
    assert out["missing_fields"] == ["time"]
    assert len(escape_calls) == 1


def test_kill_switch_off_restores_the_earlier_behaviour(tmp_path, monkeypatch):
    monkeypatch.setenv("APPOINTMENT_SIDE_QUESTION_CHECK", "off")
    _fake_extraction(monkeypatch, [
        ({"animal_name": "Lakshmi", "issue": "fever"}, {}),
        ({"date": "today"}, {"side_question": True}),
    ])
    escape_calls = _count_escape(monkeypatch, WEATHER_ANSWER)
    sup = service.AppointmentSupervisor(tmp_path)
    _start_booking(sup, "s-off")

    out = sup.turn(FARMER, "s-off", "Wait, what is the weather today?", "en-IN", include_audio=False)
    assert out["draft"]["date"] == "today"
    assert escape_calls == []


def test_cancel_wins_over_a_side_question_flag(tmp_path, monkeypatch):
    _fake_extraction(monkeypatch, [
        ({"animal_name": "Lakshmi", "issue": "fever"}, {}),
        ({}, {"side_question": True, "confirmation_signal": "cancel"}),
    ])
    escape_calls = _count_escape(monkeypatch, WEATHER_ANSWER)
    sup = service.AppointmentSupervisor(tmp_path)
    _start_booking(sup, "s-cancel")

    out = sup.turn(FARMER, "s-cancel", "forget it, cancel", "en-IN", include_audio=False)
    assert out["state"] == "CANCELLED"
    assert escape_calls == []


def test_side_question_at_the_final_readback_asks_for_confirmation_again(tmp_path, monkeypatch):
    _fake_extraction(monkeypatch, [
        ({"animal_name": "Lakshmi", "issue": "fever", "date": "2026-08-25", "time": "11:00"}, {}),
        ({}, {"side_question": True}),
    ])
    _count_escape(monkeypatch, WEATHER_ANSWER)
    sup = service.AppointmentSupervisor(tmp_path)
    first = sup.turn(FARMER, "s-readback", "Lakshmi fever 25 August 11 am", "en-IN", include_audio=False)
    assert first["state"] == "CONFIRMING" and first["missing_fields"] == []

    out = sup.turn(FARMER, "s-readback", "will it rain tomorrow?", "en-IN", include_audio=False)
    assert out["state"] == "CONFIRMING"
    assert out["draft"]["date"] == "2026-08-25"
    assert out["response_text"].startswith(WEATHER_ANSWER["answer"])
    assert "I understood:" in out["response_text"]
    # The readback is confirmed with the yes/no buttons, as after any readback.
    assert out["prompt_text"] is None


def test_side_question_when_ready_to_submit_asks_to_submit_again(tmp_path, monkeypatch):
    _fake_extraction(monkeypatch, [
        ({"animal_name": "Lakshmi", "issue": "fever", "date": "2026-08-25", "time": "11:00"}, {}),
        ({}, {"side_question": True}),
    ])
    _count_escape(monkeypatch, WEATHER_ANSWER)
    sup = service.AppointmentSupervisor(tmp_path)
    sup.turn(FARMER, "s-ready", "Lakshmi fever 25 August 11 am", "en-IN", include_audio=False)
    assert sup.confirm(FARMER, "s-ready", "yes", include_audio=False)["state"] == "READY_TO_SUBMIT"

    out = sup.turn(FARMER, "s-ready", "how many goats do I have?", "en-IN", include_audio=False)
    assert out["state"] == "READY_TO_SUBMIT"
    assert out["response_text"].endswith("Would you like to submit this appointment?")
    assert out["prompt_text"] == out["response_text"]


def test_side_question_before_anything_is_given_repeats_the_welcome(tmp_path, monkeypatch):
    _fake_extraction(monkeypatch, [({}, {"side_question": True})])
    _count_escape(monkeypatch, WEATHER_ANSWER)
    sup = service.AppointmentSupervisor(tmp_path)

    out = sup.turn(FARMER, "s-welcome", "what is the weather today?", "en-IN", include_audio=False)
    assert out["response_text"].endswith(sup._message("en-IN", "welcome"))


def test_show_options_lists_the_farmers_animals(tmp_path, monkeypatch):
    _fake_extraction(monkeypatch, [
        ({"issue": "fever"}, {}),
        ({}, {"wants_options": True}),
    ])
    sup = service.AppointmentSupervisor(tmp_path)
    first = sup.turn(FARMER, "s-opts", "my animal has fever", "en-IN", include_audio=False)
    assert first["missing_fields"][0] == "animal_identifier"

    out = sup.turn(FARMER, "s-opts", "I don't remember the name, can you show me options?", "en-IN", include_audio=False)
    assert out["options"]["choices"] == ["Lakshmi", "Kaali", "Moti"]
    assert "Lakshmi, Kaali, Moti" in out["response_text"]
    assert out["prompt_text"] == out["response_text"]
    assert out["draft"]["issue"] == "fever"
    assert "animal_identifier" in out["missing_fields"]

    # Picking one of the choices then books for it, as a typed name would.
    _fake_extraction(monkeypatch, [({"animal_name": "Kaali"}, {})])
    picked = sup.turn(FARMER, "s-opts", "Kaali", "en-IN", include_audio=False)
    assert picked["draft"]["animal_identifier"] == "Kaali"
    assert picked["draft"]["animal_id"] == "a-1"


def test_show_options_with_no_animals_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [])
    _fake_extraction(monkeypatch, [({}, {"wants_options": True})])
    sup = service.AppointmentSupervisor(tmp_path)

    out = sup.turn(FARMER, "s-none", "show me my animals", "en-IN", include_audio=False)
    assert out["response_text"] == sup._message("en-IN", "no_animals_yet")
    assert out["prompt_text"] == out["response_text"]
    assert "options" not in out


def test_show_options_is_ignored_once_the_animal_is_known(tmp_path, monkeypatch):
    _fake_extraction(monkeypatch, [
        ({"animal_name": "Lakshmi", "issue": "fever"}, {}),
        ({}, {"wants_options": True}),
    ])
    sup = service.AppointmentSupervisor(tmp_path)
    _start_booking(sup, "s-known")

    out = sup.turn(FARMER, "s-known", "show options", "en-IN", include_audio=False)
    assert out["draft"]["animal_identifier"] == "Lakshmi"
    assert out.get("options", {}).get("choices") != ["Lakshmi", "Kaali", "Moti"]


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_every_language_has_the_new_messages(tmp_path, monkeypatch, language):
    _fake_extraction(monkeypatch, [
        ({"issue": "fever"}, {}),
        ({}, {"wants_options": True}),
        ({"date": "today"}, {"side_question": True}),
    ])
    _count_escape(monkeypatch, WEATHER_ANSWER)
    sup = service.AppointmentSupervisor(tmp_path)
    sup.turn(FARMER, "s-lang", "fever", language, include_audio=False)

    listed = sup.turn(FARMER, "s-lang", "options", language, include_audio=False)
    assert "Lakshmi, Kaali, Moti" in listed["response_text"]
    assert "{" not in listed["response_text"]

    answered = sup.turn(FARMER, "s-lang", "weather today?", language, include_audio=False)
    assert answered["response_text"].startswith(WEATHER_ANSWER["answer"])
    assert "date" not in answered["draft"]

    for key in ("animal_choices", "no_animals_yet"):
        assert sup._message(language, key, animals="X")


def test_call_bedrock_returns_the_flags_outside_entities(monkeypatch):
    monkeypatch.setattr(bedrock_adapter.BedrockTextAdapter, "__init__", lambda self, task=None: None)
    monkeypatch.setattr(
        bedrock_adapter.BedrockTextAdapter, "converse_with_tool",
        lambda self, **kw: {"tool_input": {"date": "today", "side_question": True, "wants_options": False}, "text": None},
    )
    out = bedrock_adapter.call_bedrock("wait, what is the weather today?", context={"pending_questions": ["appointment date"]})
    assert out["side_question"] is True
    assert out["wants_options"] is False
    assert "side_question" not in out["entities"]
    assert "wants_options" not in out["entities"]


def test_call_bedrock_defaults_the_flags_to_false(monkeypatch):
    monkeypatch.setattr(bedrock_adapter.BedrockTextAdapter, "__init__", lambda self, task=None: None)
    monkeypatch.setattr(
        bedrock_adapter.BedrockTextAdapter, "converse_with_tool",
        lambda self, **kw: {"tool_input": {"time": "10:00"}, "text": None},
    )
    out = bedrock_adapter.call_bedrock("10 am", context={"pending_questions": ["appointment time"]})
    assert out["side_question"] is False
    assert out["wants_options"] is False
