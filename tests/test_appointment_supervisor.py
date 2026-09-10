from __future__ import annotations

import pytest

from services.appointment_supervisor import service


def test_turn_confirm_and_submit_state_machine(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id: {
            "entities": {
                "animal_identifier": "Lakshmi",
                "issue": "foot swelling",
                "date": "2026-08-25",
                "time": "11:30",
            }
        },
    )
    supervisor = service.AppointmentSupervisor(tmp_path)

    first = supervisor.turn("demo-farmer", "session-1", "Lakshmi has foot swelling on August 25 at 11:30", "en-IN")
    assert first["state"] == "CONFIRMING"
    assert first["missing_fields"] == []

    with pytest.raises(ValueError, match="final confirmation"):
        supervisor.submit("demo-farmer", "session-1")

    ready = supervisor.confirm("demo-farmer", "session-1", "yes")
    assert ready["state"] == "READY_TO_SUBMIT"


def test_correction_keeps_draft_open(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id: {"entities": {"animal_identifier": "Lakshmi", "issue": "fever"}},
    )
    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-2", "Lakshmi has fever", "hi-IN")
    corrected = supervisor.confirm("demo-farmer", "session-2", "no")

    assert corrected["state"] == "CORRECTING"
    assert corrected["response_text"]
    assert corrected["language"] == "hi-IN"


def test_hindi_turn_uses_llm_extracted_entities(tmp_path, monkeypatch):
    """No regex fallback exists — process_text_input (backed by call_bedrock)
    is the only source of entities for any language, including Hindi."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id: {
            "entities": {
                "animal_name": "सीमा",
                "issue": "lethargy",
                "symptoms": ["lethargy", "not eating"],
            }
        },
    )
    supervisor = service.AppointmentSupervisor(tmp_path)

    result = supervisor.turn(
        "demo-farmer",
        "session-hi",
        "इसका नाम सीमा है इसके खाना पीना बंद कर दिया सोई सोई रही है",
        "hi-IN",
    )

    assert result["draft"]["animal_name"] == "सीमा"
    assert result["draft"]["issue"] == "lethargy"
    assert "not eating" in result["draft"]["symptoms"]
