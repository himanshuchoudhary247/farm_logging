"""Booking for an animal registered through Chocolate after it was also
created in main_backend (FLOKIQ_SYNC_ANIMALS).

merge_app_animals keeps main_backend's copy, with main_backend's id. Found in
local testing: the extraction step named the animal by its LOCAL record's id
(the orchestrator's stored-animal prefill), so "danwwe" was reported as not
found and asked again in a loop. Real storage here, as in the app-animal
booking test in test_appointment_supervisor.py."""
from __future__ import annotations

import pytest

import storage
from services.appointment_supervisor import service

FARMER = "demo-farmer"
MAIN_ID = "71deccfc-3bc3-4a7c-9b5c-fbb59cfe534e"


@pytest.fixture
def booking(tmp_path, monkeypatch):
    monkeypatch.setenv("FARMER_CHAT_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    monkeypatch.setenv("VOICE_SESSIONS_DIR", str(tmp_path / "voice_sessions"))
    local = storage.append_animal(farmer_id=FARMER, tag_or_name="danwwe", species="goat", sex="male", breed="Osmanabadi")
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "_try_mid_draft_escape", lambda text, farmer_id, session_id, language: None)
    monkeypatch.setattr(service, "_today_ist", lambda: __import__("datetime").date(2026, 8, 20))
    monkeypatch.setattr(
        service.flokiq_sync, "get_farm_animals",
        lambda farmer_id: [{"id": MAIN_ID, "uniqueAnimalId": "danwwe", "species": "goat", "sex": "male",
                            "breed": "Osmanabadi", "status": "active"}],
    )
    monkeypatch.setattr(
        service, "generate_health_recommendation",
        lambda **k: {"diagnosis_suggestion": "", "potential_ailments": [], "first_aid_advice": ""},
    )
    monkeypatch.setattr(service, "append_ai_health_log", lambda **k: None)
    monkeypatch.setattr(service.flokiq_sync, "create_health_log", lambda **k: None)
    monkeypatch.setattr(service.flokiq_sync, "create_appointment", lambda **k: None)
    return service.AppointmentSupervisor(tmp_path), local


def _extraction(monkeypatch, entities):
    monkeypatch.setattr(service, "process_text_input",
                        lambda text, session_id, pending_questions_override=None: {"entities": dict(entities)})


def test_local_id_from_the_extraction_still_finds_the_synced_animal(booking, monkeypatch):
    sup, local = booking
    # What the booking form's "animal: danwwe" turned into: the prefill set
    # the local record's id next to the name.
    _extraction(monkeypatch, {"animal_id": local.id, "animal_name": "danwwe", "issue": "fever",
                              "date": "2026-09-20", "time": "11:00"})

    first = sup.turn(FARMER, "s1", "animal: danwwe; problem: Fever; date: 2026-09-20; time: 11:00", "en-IN",
                     include_audio=False)

    assert first["draft"]["animal_identifier"] == "danwwe"
    assert first["draft"]["animal_id"] == MAIN_ID
    assert first["missing_fields"] == []
    sup.confirm(FARMER, "s1", "yes", include_audio=False)
    assert sup.submit(FARMER, "s1", include_audio=False)["status"] == "submitted"


def test_the_name_alone_still_works(booking, monkeypatch):
    sup, _ = booking
    _extraction(monkeypatch, {"animal_name": "danwwe", "issue": "fever", "date": "2026-09-20", "time": "11:00"})
    first = sup.turn(FARMER, "s2", "danwwe fever 20 Sept 11 am", "en-IN", include_audio=False)
    assert first["draft"]["animal_id"] == MAIN_ID


def test_an_unknown_id_is_left_as_it_was():
    animals = [type("A", (), {"id": MAIN_ID, "tag_or_name": "danwwe"})()]
    assert service._merged_reference("not-an-animal", [], animals) == "not-an-animal"
    assert service._merged_reference("DANWWE", [], animals) == "DANWWE"
