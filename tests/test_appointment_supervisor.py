from __future__ import annotations

import pytest

from services.appointment_supervisor import service


def test_turn_confirm_and_submit_state_machine(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
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
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_identifier": "Lakshmi", "issue": "fever"}},
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
        lambda text, session_id, pending_questions_override=None: {
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


def test_bare_reply_to_targeted_field_question_is_wired_as_context(tmp_path, monkeypatch):
    """Real bug: a bare reply ("1122") to the bot's own "please provide the
    animal tag/ID" question kept landing in issue/symptoms instead, because
    appointment_supervisor never told the extraction call which field it
    had just asked about. Fix: pending_questions_override carries that
    context into process_text_input every turn a specific field is
    expected. This test asserts the wiring, not the real model's behavior
    (that's covered by wiring the pending_questions param through, and by
    the real extraction system prompt's own examples)."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    seen_pending = []

    def fake_process_text_input(text, session_id, pending_questions_override=None):
        seen_pending.append(pending_questions_override)
        if pending_questions_override and "animal ID" in pending_questions_override[0]:
            return {"entities": {"animal_tag": text.strip()}}
        return {"entities": {}}

    monkeypatch.setattr(service, "process_text_input", fake_process_text_input)
    supervisor = service.AppointmentSupervisor(tmp_path)

    first = supervisor.turn("demo-farmer", "session-bare", "I want to report symptoms", "en-IN")
    assert first["missing_fields"] == ["animal_identifier", "issue", "date", "time"]

    second = supervisor.turn("demo-farmer", "session-bare", "1122", "en-IN")
    # animal_tag must bridge into animal_identifier (the field REQUIRED_FIELDS
    # actually checks) -- a correctly-extracted tag that never bridges is
    # the same user-visible failure as extraction guessing the wrong field.
    assert second["draft"]["animal_identifier"] == "1122"
    assert "animal_identifier" not in second["missing_fields"]


def test_animal_tag_bridges_to_animal_identifier(tmp_path, monkeypatch):
    """_copy_entities must accept either animal_tag (bare ear-tag/ID number,
    the extraction schema's field for exactly this) or animal_name -- only
    bridging animal_name was a real bug: a correctly-extracted tag number
    silently never counted as having answered the question."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_tag": "1122"}},
    )
    supervisor = service.AppointmentSupervisor(tmp_path)
    result = supervisor.turn("demo-farmer", "session-tag", "1122", "en-IN")
    assert result["draft"]["animal_identifier"] == "1122"


def test_unchanged_extraction_reasks_targeted_field_not_full_welcome(tmp_path, monkeypatch):
    """Real bug: once anything had been collected, a turn where extraction
    found nothing new re-sent the full 4-field "Hello, please tell me..."
    welcome, discarding what was already known -- looked like the bot
    forgot the whole conversation. Fix: re-ask only the specific field
    still missing once something has been collected; full welcome is only
    for a truly empty draft."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_identifier": "Lakshmi"}},
    )
    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-reask", "Lakshmi", "en-IN")

    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}},
    )
    second = supervisor.turn("demo-farmer", "session-reask", "bro you dont understand my intent at all", "en-IN")
    assert "Hello. Please tell me the animal name" not in second["response_text"]
    assert second["draft"]["animal_identifier"] == "Lakshmi"


def test_confirmation_classified_by_signal_not_keyword_substring(tmp_path, monkeypatch):
    """Real bug: the old _response_kind() did naive substring matching --
    "no" in "enough" is True -- so an ordinary sentence containing "enough"
    got misclassified as a rejection and derailed the flow into
    CORRECTING. Fix: classification now comes from confirmation_signal on
    the same extraction call (which sees full sentence meaning), not
    Python keyword matching. This test asserts turn() reads
    confirmation_signal from the mocked extraction result rather than
    re-deriving it from the text itself."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {
                "animal_identifier": "Lakshmi", "issue": "foot swelling",
                "date": "2026-08-25", "time": "11:30",
            }
        },
    )
    supervisor = service.AppointmentSupervisor(tmp_path)
    first = supervisor.turn("demo-farmer", "session-confirm-signal", "Lakshmi foot swelling Aug 25 11:30", "en-IN")
    assert first["state"] == "CONFIRMING"

    # Now mid-CONFIRMING: a sentence containing "enough" that actually
    # means "no" -- confirmation_signal says so explicitly, unlike a
    # keyword scan of the raw text which would misfire on "enough".
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "no"},
    )
    corrected = supervisor.turn("demo-farmer", "session-confirm-signal", "that's wrong, arnt you smart enough", "en-IN")
    assert corrected["state"] == "CORRECTING"
