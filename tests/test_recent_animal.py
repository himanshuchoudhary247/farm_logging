""""What breed is KAALI?" then "she is limping, book a vet for her": the
booking asked for the animal again (found by evals layer 3, en/hi). The
router keeps the one stored animal a farm-data question was about for the
next turn only, and a new booking started on that turn uses it when it
names no animal itself."""
from __future__ import annotations

import datetime as _dt

import pytest

pytest.importorskip("google.adk")

from services.appointment_supervisor import service
from services.chat_orchestrator import adk_router
from services.common.name_match import find_name_mentions

_ANIMALS = [type("Animal", (), {"id": f"a-{n.lower()}", "tag_or_name": n, "species": "goat"})()
            for n in ("GAURI", "MOTI", "KAALI", "TAG-001-1")]


@pytest.fixture
def router(monkeypatch):
    """Classifier, agents and the session store faked; the recent-animal
    logic itself is the real code."""
    store = {}
    monkeypatch.setattr(adk_router, "get_session", lambda key: dict(store.get(key, {})))
    monkeypatch.setattr(adk_router, "update_session", lambda key, data: store.setdefault(key, {}).update(data))
    monkeypatch.setattr(adk_router, "animals_for_farmer", lambda farmer_id: _ANIMALS)
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.delenv("CHAT_RECENT_ANIMAL", raising=False)
    calls = {"recent": []}

    def turn(farmer_id, session_id, text, language, include_audio=True, side_question=None, recent_animal=None):
        calls["recent"].append(recent_animal)
        return {"response_text": "booking", "state": "COLLECTING", "response_audio_base64": None}

    monkeypatch.setattr(adk_router._appointment_supervisor, "turn", turn)
    return calls


def _say(monkeypatch, intent, text, answer=""):
    async def classify(_text):
        return intent

    monkeypatch.setattr(adk_router, "_classify_intent_async", classify)
    monkeypatch.setattr(adk_router, "process_query_adk",
                        lambda query, farmer_id, session_id=None, app_language=None: {"answer": answer, "sql": "S", "data": [1]})
    monkeypatch.setattr(adk_router, "_run_weather",
                        lambda *a, **k: {"agent": "weather_alert", "reply_text": "sunny"})
    return adk_router.route_turn_adk("f-001", "s-1", text, "hi-IN")


def test_booking_right_after_a_question_about_one_animal_gets_that_animal(monkeypatch, router):
    _say(monkeypatch, "query", "KAALI की नस्ल क्या है?", "KAALI की नस्ल Jamunapari है।")
    _say(monkeypatch, "appointment", "वो लंगड़ा रही है, उसके लिए कल सुबह 10 बजे डॉक्टर बुक करो")
    assert router["recent"] == ["KAALI"]


def test_name_in_another_script_counts(monkeypatch, router):
    _say(monkeypatch, "query", "गौरी की नस्ल क्या है?", "यह सिरोही बकरी है।")
    _say(monkeypatch, "appointment", "उसके लिए डॉक्टर चाहिए")
    assert router["recent"] == ["GAURI"]


def test_the_name_lasts_one_turn_only(monkeypatch, router):
    _say(monkeypatch, "query", "what breed is KAALI?", "KAALI is a Jamunapari goat.")
    _say(monkeypatch, "weather", "how is the weather in Pune?")
    _say(monkeypatch, "appointment", "book a vet for her tomorrow")
    assert router["recent"] == [None]


def test_two_animals_named_keeps_none(monkeypatch, router):
    _say(monkeypatch, "query", "what breed are GAURI and MOTI?", "Both are Sirohi goats.")
    _say(monkeypatch, "appointment", "book a vet for her tomorrow")
    assert router["recent"] == [None]


def test_question_with_no_animal_keeps_none(monkeypatch, router):
    _say(monkeypatch, "query", "how many goats do I have?", "You have 14 goats.")
    _say(monkeypatch, "appointment", "book a vet tomorrow")
    assert router["recent"] == [None]


def test_kill_switch(monkeypatch, router):
    monkeypatch.setenv("CHAT_RECENT_ANIMAL", "0")
    _say(monkeypatch, "query", "what breed is KAALI?", "KAALI is a Jamunapari goat.")
    _say(monkeypatch, "appointment", "book a vet for her tomorrow")
    assert router["recent"] == [None]


def test_exact_names_are_found_only_when_asked():
    names = ["GAURI", "KAALI"]
    assert find_name_mentions("KAALI ki nasal", names) == []
    assert [m.name for m in find_name_mentions("KAALI ki nasal", names, include_exact=True)] == ["KAALI"]


# ---- the booking side ----------------------------------------------------------

@pytest.fixture
def booking(monkeypatch):
    monkeypatch.setenv("VOICE_SESSIONS_MEMORY", "1")
    monkeypatch.setattr(service, "process_query", lambda query, farmer_id: {"answer": None, "sql": None, "data": None})
    monkeypatch.setattr(service, "_today_ist", lambda: _dt.date(2026, 8, 20))
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: _ANIMALS)


def _extract(monkeypatch, entities):
    monkeypatch.setattr(service, "process_text_input",
                        lambda text, session_id, pending_questions_override=None: {"entities": dict(entities)})


def test_booking_with_no_animal_uses_the_recent_one(tmp_path, monkeypatch, booking):
    _extract(monkeypatch, {"issue": "limping", "symptoms": ["limping"], "date": "2026-08-21", "time": "10:00"})
    result = service.AppointmentSupervisor(tmp_path).turn(
        "f-001", "b-1", "she is limping, book a vet for her tomorrow at 10 am", "en-IN", recent_animal="KAALI")
    assert result["draft"]["animal_identifier"] == "KAALI"
    assert result["draft"]["animal_id"] == "a-kaali"
    assert "KAALI" in result["response_text"], "the readback shows it so the farmer can correct it"


def test_an_animal_the_farmer_names_wins(tmp_path, monkeypatch, booking):
    _extract(monkeypatch, {"animal_name": "GAURI", "issue": "fever", "symptoms": ["fever"]})
    result = service.AppointmentSupervisor(tmp_path).turn(
        "f-001", "b-2", "GAURI has fever", "en-IN", recent_animal="KAALI")
    assert result["draft"]["animal_identifier"] == "GAURI"


def test_no_recent_animal_asks_as_before(tmp_path, monkeypatch, booking):
    _extract(monkeypatch, {"issue": "limping", "symptoms": ["limping"]})
    result = service.AppointmentSupervisor(tmp_path).turn("f-001", "b-3", "she is limping", "en-IN")
    assert not result["draft"].get("animal_identifier")
    assert "animal_identifier" in result["missing_fields"]
    