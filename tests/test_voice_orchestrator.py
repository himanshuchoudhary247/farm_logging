import datetime

from models import Animal
from services.voice_agent import orchestrator
from services.voice_agent.session_store import clear_session


def _stub_bedrock(_: str):
    return {}


def test_appointment_single_turn_extracts_date_and_time(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-appointment-single"
    clear_session(session_id)

    out = orchestrator.process_text_input(
        "book a vet appointment tomorrow at 5 pm", session_id=session_id
    )

    expected_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    assert out["intent"] == "CREATE_APPOINTMENT"
    assert out["entities"]["date"] == expected_date
    assert out["entities"]["time"] == "17:00"
    assert out["follow_up_questions"] == []
    assert out["complete"] is True


def test_appointment_followups_are_resolved_over_turns(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_bedrock)

    session_id = "test-appointment-followup"
    clear_session(session_id)

    first = orchestrator.process_text_input("book a vet appointment", session_id=session_id)
    assert first["follow_up_questions"] == ["What date and time should the appointment be?"]

    second = orchestrator.process_text_input("tomorrow", session_id=session_id)
    expected_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    assert second["entities"]["date"] == expected_date
    assert second["follow_up_questions"] == ["What time should the appointment be?"]
    assert second["complete"] is False

    third = orchestrator.process_text_input("5 pm", session_id=session_id)
    assert third["entities"]["time"] == "17:00"
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
        "Please provide: animal name or tag, species, sex (male/female), breed, age in years."
    ]

    third = orchestrator.process_text_input("goat male", session_id=session_id)
    assert third["entities"]["species"] == "goat"
    assert third["entities"]["sex"] == "male"
    assert third["follow_up_questions"] == [
        "Please provide: animal name or tag, breed, age in years."
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
        "existing animal id a-f-001-2, update breed to jamunapari and age 4 years",
        session_id=session_id,
    )

    assert out["intent"] == "UPDATE_ANIMAL"
    assert out["entities"]["animal_id"] == "a-f-001-2"
    assert out["entities"]["breed"] == "jamunapari"
    assert out["entities"]["age_years"] == 4.0
    assert out["follow_up_questions"] == []
    assert out["complete"] is True
