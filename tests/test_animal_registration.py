"""Tests for the conversational animal-registration agent. Mocks
AnimalRegistrationSupervisor._extract (instance-level, matching this
suite's established convention of mocking at the LLM boundary rather than
the network -- see test_appointment_supervisor.py's process_text_input
mocking) so the suite stays deterministic and makes no live Bedrock calls."""
from __future__ import annotations

import threading

import pytest

from services.animal_registration.service import AnimalRegistrationSupervisor


def _mock_extract(sup, entities_by_call):
    """entities_by_call: list of dicts, one per turn, returned in order."""
    calls = iter(entities_by_call)
    sup._extract = lambda draft, text: next(calls, {})


def test_required_field_collection_then_submit(tmp_path, monkeypatch):
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [])
    appended = {}

    def fake_append_animal(**kwargs):
        appended.update(kwargs)
        return type("Animal", (), {**kwargs, "id": "new-a-1", "tag_or_name": kwargs["tag_or_name"], "model_dump": lambda self: {**kwargs, "id": "new-a-1"}})()

    monkeypatch.setattr("services.animal_registration.service.append_animal", fake_append_animal)

    sup = AnimalRegistrationSupervisor(tmp_path)
    _mock_extract(sup, [
        {"species": "goat"},
        {"unique_animal_id": "REGTEST-1"},
        {"breed": "Jamunapari", "sex": "male"},
        {"wants_to_skip_optional": True},
    ])

    sup.turn("f-001", "s1", "register a goat", include_audio=False)
    sup.turn("f-001", "s1", "REGTEST-1", include_audio=False)
    r3 = sup.turn("f-001", "s1", "Jamunapari male", include_audio=False)
    assert r3["state"] == "COLLECTING_OPTIONAL", "all required fields just completed -- next stop is the optional phase, not confirm"

    r4 = sup.turn("f-001", "s1", "no thats all", include_audio=False)
    assert r4["state"] == "CONFIRMING"
    assert "REGTEST-1" in r4["response_text"]
    assert "Jamunapari" in r4["response_text"]

    result = sup.confirm("f-001", "s1", "yes", include_audio=False)
    assert result["status"] == "submitted"
    assert appended["tag_or_name"] == "REGTEST-1"
    assert appended["species"] == "goat"
    assert appended["breed"] == "Jamunapari"
    assert appended["sex"] == "male"


def test_no_repetition_of_previously_captured_fields(tmp_path, monkeypatch):
    """The exact behavior explicitly requested: turn 3 (adding a 5th of 5
    optional-phase fields) must not restate fields captured in turns 1-2."""
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [])
    monkeypatch.setattr("services.animal_registration.service.append_animal", lambda **kwargs: None)

    sup = AnimalRegistrationSupervisor(tmp_path)
    _mock_extract(sup, [
        {"unique_animal_id": "NOREPEAT-1", "species": "goat", "breed": "Jamunapari", "sex": "male"},
        {"initial_weight_kg": "25"},
        {"current_location": "North Field"},
        {"wants_to_skip_optional": True},
    ])

    r1 = sup.turn("f-001", "s2", "NOREPEAT-1 goat Jamunapari male", include_audio=False)
    assert r1["state"] == "COLLECTING_OPTIONAL"
    assert "NOREPEAT-1" not in r1["response_text"]  # first arrival: generic explanation, no field dump at all

    r2 = sup.turn("f-001", "s2", "weight 25", include_audio=False)
    assert "25" in r2["response_text"]
    assert "NOREPEAT-1" not in r2["response_text"]
    assert "Jamunapari" not in r2["response_text"]

    r3 = sup.turn("f-001", "s2", "location North Field", include_audio=False)
    assert "North Field" in r3["response_text"]
    assert "25" not in r3["response_text"], "turn 3 must not repeat turn 2's weight"
    assert "NOREPEAT-1" not in r3["response_text"], "turn 3 must not repeat turn 1's fields"

    # The full summary appears exactly once, at the final confirm step.
    r4 = sup.turn("f-001", "s2", "no thats all", include_audio=False)
    assert r4["state"] == "CONFIRMING"
    for expected in ("NOREPEAT-1", "Jamunapari", "25", "North Field"):
        assert expected in r4["response_text"]


def test_breed_species_mismatch_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [])

    sup = AnimalRegistrationSupervisor(tmp_path)
    _mock_extract(sup, [
        {"species": "goat"},
        {"breed": "Kashmir Merino"},  # a real sheep breed, not a goat breed
    ])

    sup.turn("f-001", "s3", "register a goat", include_audio=False)
    result = sup.turn("f-001", "s3", "breed Kashmir Merino", include_audio=False)
    assert "Kashmir Merino" in result["response_text"]
    assert result["draft"].get("breed") is None, "an invalid breed for the given species must not be stored"


def test_valid_breed_matched_to_canonical_name(tmp_path, monkeypatch):
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [])

    sup = AnimalRegistrationSupervisor(tmp_path)
    _mock_extract(sup, [
        {"species": "sheep"},
        {"breed": "nali"},  # lowercase, should still match "Nali"
    ])

    sup.turn("f-001", "s4", "register a sheep", include_audio=False)
    result = sup.turn("f-001", "s4", "breed nali", include_audio=False)
    assert result["draft"].get("breed") == "Nali"


def test_duplicate_tag_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    existing_animal = type("Animal", (), {"id": "a-1", "tag_or_name": "EXISTING-1"})()
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [existing_animal])

    sup = AnimalRegistrationSupervisor(tmp_path)
    _mock_extract(sup, [{"unique_animal_id": "existing-1"}])  # different case, same tag

    result = sup.turn("f-001", "s5", "ID is existing-1", include_audio=False)
    assert "already registered" in result["response_text"]
    assert result["draft"].get("unique_animal_id") is None


def test_field_unknown_accepts_fallback_breed(tmp_path, monkeypatch):
    """Real bug found live (peer session testing the UI, 2026-09-22): a
    farmer who genuinely doesn't know their animal's breed had no way to
    proceed -- every turn produced the byte-identical "Please provide the
    breed." with no escape. field_unknown must unblock the flow."""
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [])

    sup = AnimalRegistrationSupervisor(tmp_path)
    _mock_extract(sup, [
        {"unique_animal_id": "UNK-1", "species": "goat", "sex": "male"},
        {"field_unknown": True},
    ])

    sup.turn("f-001", "s8", "UNK-1 goat male", include_audio=False)
    result = sup.turn("f-001", "s8", "no idea", include_audio=False)
    assert result["state"] == "COLLECTING_OPTIONAL", "an explicit don't-know must unblock the required-field phase, not loop"
    assert result["draft"]["breed"]


def test_breed_mismatch_does_not_drop_sibling_fields_from_same_turn(tmp_path, monkeypatch):
    """Real bug found live: _copy_entities used to `return` the instant a
    breed guess failed to match, silently dropping every other field
    extracted in that same turn (sex, unique_animal_id, ...). A single
    turn stating several fields plus a bad breed guess must still apply
    the good fields."""
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [])

    sup = AnimalRegistrationSupervisor(tmp_path)
    _mock_extract(sup, [{
        "unique_animal_id": "SIB-1", "species": "goat", "sex": "male", "breed": "Not A Real Breed",
    }])

    result = sup.turn("f-001", "s9", "SIB-1 goat male, breed is Not A Real Breed", include_audio=False)
    assert "Not A Real Breed" in result["response_text"]
    assert result["draft"].get("breed") is None
    assert result["draft"].get("unique_animal_id") == "SIB-1", "sibling field must survive a breed mismatch in the same turn"
    assert result["draft"].get("sex") == "male", "sibling field must survive a breed mismatch in the same turn"


def test_duplicate_id_detected_even_alongside_a_breed_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    existing_animal = type("Animal", (), {"id": "a-1", "tag_or_name": "DUP-1"})()
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [existing_animal])

    sup = AnimalRegistrationSupervisor(tmp_path)
    _mock_extract(sup, [{"unique_animal_id": "dup-1", "species": "goat", "breed": "Not A Real Breed"}])

    result = sup.turn("f-001", "s10", "dup-1 goat, breed Not A Real Breed", include_audio=False)
    assert "already registered" in result["response_text"], "duplicate ID must still surface even when the same turn also has a breed error"
    assert result["draft"].get("unique_animal_id") is None


def test_optional_phase_does_not_let_a_stray_reply_clobber_the_captured_id(tmp_path, monkeypatch):
    """Real bug found live: once required fields were done, a bare
    ambiguous word got guessed as a *new* unique_animal_id and silently
    overwrote the already-correct one. Must require an explicit
    corrects_identity signal to change it past that point."""
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [])

    sup = AnimalRegistrationSupervisor(tmp_path)
    _mock_extract(sup, [
        {"unique_animal_id": "GOOD-1", "species": "goat", "breed": "Jamunapari", "sex": "male"},
        {"unique_animal_id": "Stray"},  # no corrects_identity -- must be ignored
        {"unique_animal_id": "Fixed-1", "corrects_identity": True},  # explicit -- must apply
    ])

    sup.turn("f-001", "s11", "GOOD-1 goat Jamunapari male", include_audio=False)
    r2 = sup.turn("f-001", "s11", "Stray", include_audio=False)
    assert r2["draft"]["unique_animal_id"] == "GOOD-1", "a stray guess without corrects_identity must not overwrite the captured ID"

    r3 = sup.turn("f-001", "s11", "actually change the ID to Fixed-1", include_audio=False)
    assert r3["draft"]["unique_animal_id"] == "Fixed-1", "an explicit correction with corrects_identity must be allowed through"


def test_cancel_mid_registration(tmp_path, monkeypatch):
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [])

    sup = AnimalRegistrationSupervisor(tmp_path)
    _mock_extract(sup, [
        {"species": "goat"},
        {"confirmation_signal": "cancel"},
    ])

    sup.turn("f-001", "s6", "register a goat", include_audio=False)
    result = sup.turn("f-001", "s6", "never mind, cancel", include_audio=False)
    assert result["state"] == "CANCELLED"
    with pytest.raises(ValueError, match="already been submitted"):
        sup.confirm("f-001", "s6", "yes", include_audio=False)


def test_concurrent_turns_do_not_lose_transcript_entries(tmp_path, monkeypatch):
    """Same concurrency-safety design as appointment_supervisor's own RLock
    fix (a real lost-update race the code review found) -- verify it here
    too, applied from day one rather than needing a follow-up fix."""
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [])

    sup = AnimalRegistrationSupervisor(tmp_path)
    sup._extract = lambda draft, text: {}

    threads = [
        threading.Thread(target=sup.turn, args=("f-001", "s7", "hello"), kwargs={"include_audio": False})
        for _ in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive(), "a turn() call hung -- possible deadlock"

    draft = sup._load("s7", "f-001", "en-IN")
    assert len(draft["transcript_history"]) == 5, "every concurrent turn's transcript entry must survive"


def test_extract_tells_model_when_confirming(tmp_path, monkeypatch):
    """The confirmation_signal guidance only works if the model is told a
    confirm question was asked. Checks the CONFIRMING phase hint actually
    reaches the model's context, without any live Bedrock call."""
    captured = {}

    class FakeAdapter:
        def __init__(self, task=None):
            pass

        def converse_with_tool(self, messages, tool_spec, system=None, tool_choice_name=None):
            captured["context"] = messages[0]["content"]
            return {"tool_input": {}}

    monkeypatch.setattr("services.animal_registration.service.BedrockTextAdapter", FakeAdapter)

    sup = AnimalRegistrationSupervisor(tmp_path)
    draft = sup._fresh("s12", "f-001", "en-IN")
    draft["state"] = "CONFIRMING"
    draft["draft"] = {"unique_animal_id": "C-1", "species": "goat", "breed": "Jamunapari", "sex": "male"}

    sup._extract(draft, "there's no problem, go ahead")
    assert "PHASE: confirming" in captured["context"]
