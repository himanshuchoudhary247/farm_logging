"""The add-animal form's Register button is read without the model
(services/common/form_reply.py). Seen live: "abc · goat · Ganjam · female"
-> "Please provide the breed" again and again, in Malayalam and English."""
from __future__ import annotations

import pytest

from services.animal_registration import service
from services.animal_registration.service import AnimalRegistrationSupervisor
from services.common.form_reply import parse_form_reply

FARMER = "24cdd479-7ce8-4951-91cb-e295f8a2b0ff"
SESSION = "24666232-6a23-4471-9fef-0c89e366ddbe"


@pytest.fixture
def sup(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "_try_mid_draft_escape", lambda text, farmer_id, session_id, language: None)
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [])
    s = AnimalRegistrationSupervisor(tmp_path)
    s.calls = []
    s._extract = lambda draft, text: s.calls.append(text) or {}
    return s


@pytest.mark.parametrize("language,breed", [("ml-IN", "Ganjam"), ("en-IN", "Ghumusari"), ("hi-IN", "Assam Hill"),
                                            ("ta-IN", "Osmanabadi")])
def test_the_form_fills_id_species_breed_and_sex_without_the_model(sup, language, breed):
    # Exactly what the app sends when Register is tapped (flokiquser lib/a2ui.ts actionToChatText).
    r = sup.turn(FARMER, SESSION, f"animal ID: ee-1; species: goat; breed: {breed}; sex: female", language,
                 include_audio=False)
    assert sup.calls == [], "no model call for the form"
    assert r["draft"]["breed"] == breed and r["draft"]["species"] == "goat"
    assert r["draft"]["sex"] == "female" and r["draft"]["unique_animal_id"] == "ee-1"
    assert r["missing_fields"] == []


def test_a_breed_of_the_other_species_is_still_refused(sup):
    r = sup.turn(FARMER, SESSION, "animal ID: ee-2; species: sheep; breed: Jamunapari; sex: male", include_audio=False)
    assert not r["draft"].get("breed") and "breed" in r["missing_fields"]


def test_a_form_with_only_some_fields_keeps_what_was_given(sup):
    sup.turn(FARMER, SESSION, "animal ID: ee-3; species: goat; sex: female", include_audio=False)
    r = sup.turn(FARMER, SESSION, "species: goat; breed: Osmanabadi", include_audio=False)
    assert r["draft"]["breed"] == "Osmanabadi" and r["draft"]["sex"] == "female" and r["missing_fields"] == []
    assert sup.calls == []


@pytest.mark.parametrize("text", ["ee goat ganjam female", "breed: Ganjam", "my goat is Ganjam; she is 2 years old",
                                  "animal ID: 12; colour: brown"])
def test_anything_else_goes_to_the_model_as_before(sup, text):
    sup.turn(FARMER, SESSION, text, include_audio=False)
    assert sup.calls == [text]


def test_parse_form_reply_shape():
    keys = {"animal ID": "unique_animal_id", "breed": "breed"}
    assert parse_form_reply("Animal ID: 7; BREED: Sirohi", keys) == {"unique_animal_id": "7", "breed": "Sirohi"}
    assert parse_form_reply("animal ID: 7", keys) is None
    # An empty field is skipped, the rest is still read (deep review).
    assert parse_form_reply("animal ID: 7; breed:", keys) == {"unique_animal_id": "7"}
    assert parse_form_reply("animal ID: ; breed:", keys) is None
    assert parse_form_reply("", keys) is None


def test_a_value_that_is_not_allowed_is_logged(sup, caplog):
    with caplog.at_level("INFO"):
        sup.turn(FARMER, SESSION, "animal ID: ee-9; species: dragon; sex: robot", include_audio=False)
    assert "animal registration species rejected (not a known species): 'dragon'" in caplog.text
    assert "animal registration sex rejected (not a known value): 'robot'" in caplog.text
    assert "dropped=sex,species" in caplog.text and "source=app" in caplog.text


def test_form_shape_tells_the_app_from_a_typed_look_alike():
    from services.common.form_reply import form_shape

    keys = service._FORM_KEYS
    assert form_shape("animal ID: 7; species: goat; sex: female", keys) == "app"
    assert form_shape("sex: female; animal ID: 7", keys) == "typed"
    assert form_shape("Animal id: 7; species: goat", keys) == "typed"
