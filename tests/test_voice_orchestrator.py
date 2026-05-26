import datetime

from models import Animal
from services.voice_agent import orchestrator
from services.voice_agent.session_store import clear_session


def _stub_bedrock(_: str, **kwargs):
    return {}


def test_appointment_single_turn_extracts_date_and_time(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-appointment-single"
    clear_session(session_id)

    out = orchestrator.process_text_input(
        "book a vet appointment tomorrow at 5 pm", session_id=session_id
    )

    assert out["intent"] == "CREATE_APPOINTMENT"
    assert out["entities"]["date"] == (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    assert out["entities"]["time"] == "17:00"
    assert out["follow_up_questions"] == [
        "Please provide: animal ID or animal name/tag, issue/symptoms, duration, severity (mild/moderate/severe), current medication (or 'none')."
    ]
    assert out["complete"] is False


def test_appointment_followups_are_resolved_over_turns(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-appointment-followup"
    clear_session(session_id)

    first = orchestrator.process_text_input("book a vet appointment", session_id=session_id)
    assert first["follow_up_questions"] == [
        "Please provide: animal ID or animal name/tag, issue/symptoms, duration, severity (mild/moderate/severe), current medication (or 'none'), appointment date, appointment time."
    ]

    second = orchestrator.process_text_input("tomorrow", session_id=session_id)
    expected_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    assert second["entities"]["date"] == expected_date
    assert len(second["follow_up_questions"]) == 1
    assert "appointment time" in second["follow_up_questions"][0]
    assert "issue/symptoms" in second["follow_up_questions"][0]
    assert second["complete"] is False

    third = orchestrator.process_text_input(
        "5 pm for animal name chutki issue fever duration 2 days severe no medicine",
        session_id=session_id,
    )
    assert third["entities"]["time"] == "17:00"
    assert third["entities"]["animal_name"] == "chutki"
    assert third["entities"]["issue"] == "fever"
    assert third["entities"]["duration"] == "2 days"
    assert third["entities"]["severity"] == "severe"
    assert third["entities"]["current_medication"] == "none"
    assert third["follow_up_questions"] == []
    assert third["complete"] is True


def test_animal_id_prefills_profile_details(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)
    monkeypatch.setattr(
        orchestrator,
        "load_animals",
        lambda: [
            Animal(
                id="a-f-001-2",
                farmer_id="f-001",
                species="goat",
                tag_or_name="Lali",
                breed="Sirohi",
                age_years=3,
            )
        ],
    )

    session_id = "test-prefill-id"
    clear_session(session_id)
    out = orchestrator.process_text_input(
        "my goat a-f-001-2 is not eating since yesterday", session_id=session_id
    )

    assert out["entities"]["animal_id"] == "a-f-001-2"
    assert out["entities"]["animal_name"] == "Lali"
    assert out["entities"]["species"] == "goat"
    assert out["entities"]["breed"] == "Sirohi"
    assert out["entities"]["age_years"] == 3
    assert out["entities"]["feeding_details"] == ""


def test_animal_name_prefills_profile_details(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)
    monkeypatch.setattr(
        orchestrator,
        "load_animals",
        lambda: [
            Animal(
                id="a-f-001-3",
                farmer_id="f-001",
                species="goat",
                tag_or_name="Chutki",
                breed="Jamunapari",
                age_years=2.5,
            )
        ],
    )

    session_id = "test-prefill-name"
    clear_session(session_id)
    out = orchestrator.process_text_input(
        "for animal name chutki, book a vet appointment", session_id=session_id
    )

    assert out["entities"]["animal_id"] == "a-f-001-3"
    assert out["entities"]["animal_name"] == "Chutki"
    assert out["entities"]["species"] == "goat"
    assert out["entities"]["breed"] == "Jamunapari"
    assert out["entities"]["age_years"] == 2.5
    assert out["entities"]["feeding_details"] == ""


def test_create_animal_asks_new_or_existing_when_unspecified(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-animal-mode-followup"
    clear_session(session_id)
    out = orchestrator.process_text_input(
        "i want to add details about my animal", session_id=session_id
    )

    assert out["intent"] == "CREATE_ANIMAL"
    assert out["follow_up_questions"] == [
        "Please provide: whether this is a new animal registration or an existing animal update."
    ]
    assert out["complete"] is False


def test_create_animal_collects_all_required_fields_before_complete(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-animal-fields-followup"
    clear_session(session_id)

    first = orchestrator.process_text_input(
        "i want to add details about my animal", session_id=session_id
    )
    assert first["follow_up_questions"] == [
        "Please provide: whether this is a new animal registration or an existing animal update."
    ]

    second = orchestrator.process_text_input("new", session_id=session_id)
    assert second["follow_up_questions"] == [
        "Please provide: animal name or tag, species, sex (male/female), breed, age in years, feeding details."
    ]

    third = orchestrator.process_text_input("goat male", session_id=session_id)
    assert third["entities"]["species"] == "goat"
    assert third["entities"]["sex"] == "male"
    assert third["follow_up_questions"] == [
        "Please provide: animal name or tag, breed, age in years, feeding details."
    ]
    assert third["complete"] is False


def test_existing_animal_update_with_id_and_fields_completes(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)
    monkeypatch.setattr(
        orchestrator,
        "load_animals",
        lambda: [
            Animal(
                id="a-f-001-2",
                farmer_id="f-001",
                species="goat",
                tag_or_name="Lali",
                breed="Sirohi",
                age_years=3,
            )
        ],
    )

    session_id = "test-existing-update"
    clear_session(session_id)
    out = orchestrator.process_text_input(
        "existing animal id a-f-001-2, update breed to jamunapari and age 4 years, feeding details dry fodder twice daily",
        session_id=session_id,
    )

    assert out["intent"] == "UPDATE_ANIMAL"
    assert out["entities"]["animal_id"] == "a-f-001-2"
    assert out["entities"]["breed"] == "jamunapari"
    assert out["entities"]["age_years"] == 4.0
    assert out["entities"]["feeding_details"] == "dry fodder twice daily"
    assert out["follow_up_questions"] == []
    assert out["complete"] is True


def test_non_animal_book_text_does_not_trigger_create_animal(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-non-animal-book"
    clear_session(session_id)
    out = orchestrator.process_text_input(
        "i want to add details about my book", session_id=session_id
    )

    assert out["intent"] is None
    assert out["follow_up_questions"] == []
    assert out["complete"] is False


def test_existing_flow_identifier_only_then_asks_update_fields(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-existing-id-only"
    clear_session(session_id)
    first = orchestrator.process_text_input(
        "existing animal", session_id=session_id
    )
    assert first["intent"] == "UPDATE_ANIMAL"
    assert first["follow_up_questions"] == [
        "Please provide: animal ID or animal name/tag, the details to update (species, sex, breed, age in years, feeding details)."
    ]

    second = orchestrator.process_text_input("1234", session_id=session_id)
    assert second["entities"]["animal_id"] == "1234"
    assert second["follow_up_questions"] == [
        "Please provide: the details to update (species, sex, breed, age in years, feeding details)."
    ]


def test_age_words_and_standalone_number_are_accepted(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-age-word-number"
    clear_session(session_id)

    orchestrator.process_text_input("i want to add details about my animal", session_id=session_id)
    orchestrator.process_text_input("new animal", session_id=session_id)
    turn = orchestrator.process_text_input(
        "animal is goat, name is anshul, sex is female, breed is abc, feeding details not feeding",
        session_id=session_id,
    )
    assert turn["follow_up_questions"] == ["Please provide: age in years."]

    turn2 = orchestrator.process_text_input("four years", session_id=session_id)
    assert turn2["entities"]["age_years"] == 4.0
    assert turn2["follow_up_questions"] == []
    assert turn2["complete"] is True


def test_animal_details_phrase_triggers_create_animal_intent(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-animal-details-phrase"
    clear_session(session_id)
    out = orchestrator.process_text_input("i had details about my animal", session_id=session_id)

    assert out["intent"] == "CREATE_ANIMAL"


def test_create_animal_canonicalizes_noisy_alias_entities(monkeypatch):
    def _stub_noisy_llm(_: str, **kwargs):
        return {
            "entities": {
                "gender": "female",
                "age": "4 years",
                "name": "anshul",
                "symptom": "not feeding",
            }
        }

    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_noisy_llm)

    session_id = "test-canonicalize-aliases"
    clear_session(session_id)
    out = orchestrator.process_text_input(
        "new animal goat breed abc", session_id=session_id
    )

    assert out["intent"] == "CREATE_ANIMAL"
    assert out["entities"]["sex"] == "female"
    assert out["entities"]["age_years"] == 4.0
    assert out["entities"]["animal_name"] == "anshul"
    assert out["entities"]["feeding_details"] == "not feeding"
    assert "gender" not in out["entities"]
    assert "age" not in out["entities"]
    assert "name" not in out["entities"]
    assert "symptom" not in out["entities"]


def test_new_request_after_complete_resets_animal_state(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-new-request-reset"
    clear_session(session_id)

    orchestrator.process_text_input("i want to add details about my animal", session_id=session_id)
    orchestrator.process_text_input("new animal", session_id=session_id)
    done = orchestrator.process_text_input(
        "name is anshul, goat female, breed abc, age 4 years, feeding details dry fodder",
        session_id=session_id,
    )
    assert done["complete"] is True

    next_out = orchestrator.process_text_input(
        "i want to add details about already present animal", session_id=session_id
    )
    assert next_out["intent"] == "UPDATE_ANIMAL"
    assert next_out["complete"] is False
    assert next_out["follow_up_questions"] == [
        "Please provide: animal ID or animal name/tag, the details to update (species, sex, breed, age in years, feeding details)."
    ]


def test_switching_from_animal_update_to_appointment_resets_intent(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-intent-switch-to-appointment"
    clear_session(session_id)

    done = orchestrator.process_text_input(
        "existing animal id a-f-001-99, update breed to alpha beta and feeding details not available",
        session_id=session_id,
    )
    assert done["intent"] == "UPDATE_ANIMAL"
    assert done["complete"] is True

    out = orchestrator.process_text_input(
        "book an appointment for charlie", session_id=session_id
    )
    assert out["intent"] == "CREATE_APPOINTMENT"
    assert out["follow_up_questions"] == [
        "Please provide: animal ID or animal name/tag, issue/symptoms, duration, severity (mild/moderate/severe), current medication (or 'none'), appointment date, appointment time."
    ]
    assert out["complete"] is False


def test_appointment_time_accepts_dotted_pm(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-appointment-dotted-pm"
    clear_session(session_id)

    first = orchestrator.process_text_input("book a vet appointment", session_id=session_id)
    assert first["intent"] == "CREATE_APPOINTMENT"

    second = orchestrator.process_text_input(
        "for animal name charlie issue fever duration 2 days mild no medicine tomorrow 5 p.m.",
        session_id=session_id,
    )
    assert second["entities"]["time"] == "17:00"
    assert second["follow_up_questions"] == []
    assert second["complete"] is True


def test_fetch_animal_details_intent_requires_identifier(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-fetch-animal"
    clear_session(session_id)
    out = orchestrator.process_text_input("get details of my animal", session_id=session_id)

    assert out["intent"] == "FETCH_ANIMAL_DETAILS"
    assert out["follow_up_questions"] == ["Please provide: animal ID or animal name/tag."]
    assert out["complete"] is False


def test_llm_high_confidence_can_override_rule_intent(monkeypatch):
    def _stub(_: str, **kwargs):
        return {
            "intent": "CREATE_APPOINTMENT",
            "entities": {
                "animal_name": "charlie",
                "issue": "fever",
                "duration": "2 days",
                "severity": "mild",
                "current_medication": "none",
                "date": "tomorrow",
                "time": "5 pm",
            },
            "confidence": 0.95,
            "follow_up_questions": [],
            "missing_fields": [],
        }

    monkeypatch.setattr(orchestrator, "call_bedrock", _stub)

    session_id = "test-llm-override"
    clear_session(session_id)
    out = orchestrator.process_text_input("please update my animal", session_id=session_id)

    assert out["intent"] == "CREATE_APPOINTMENT"
