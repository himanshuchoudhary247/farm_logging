"""orchestrator.py has no regex/keyword extractors — call_bedrock() is the
sole source of intent + entities for any input, in any language or
phrasing. These tests stub call_bedrock with the JSON shape a real LLM call
would return and verify orchestrator's session bookkeeping: entity merge,
animal-profile prefill, alias canonicalization, missing-field detection,
follow-up generation, and intent transitions."""
import datetime

from models import Animal
from services.voice_agent import orchestrator
from services.voice_agent.session_store import clear_session


def _llm(intent=None, entities=None, confidence=0.9, unavailable_fields=None, follow_up_questions=None):
    """Build a stub call_bedrock() that returns a fixed LLM-shaped response."""
    def _stub(_text: str, **kwargs):
        return {
            "intent": intent,
            "entities": entities or {},
            "confidence": confidence,
            "unavailable_fields": unavailable_fields or [],
            "follow_up_questions": follow_up_questions or [],
            "missing_fields": [],
        }
    return _stub


def test_appointment_single_turn_llm_extracts_date_and_time(monkeypatch):
    tomorrow_iso = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        intent="CREATE_APPOINTMENT",
        entities={"date": "tomorrow", "time": "17:00"},
    ))

    session_id = "test-appointment-single"
    clear_session(session_id)

    out = orchestrator.process_text_input(
        "book a vet appointment tomorrow at 5 pm", session_id=session_id
    )

    assert out["intent"] == "CREATE_APPOINTMENT"
    assert out["entities"]["date"] == tomorrow_iso
    assert out["entities"]["time"] == "17:00"
    assert out["follow_up_questions"] == [
        "Please provide: animal ID or animal name/tag, issue/symptoms, duration, severity (mild/moderate/severe), current medication (or 'none')."
    ]
    assert out["complete"] is False


def test_appointment_followups_are_resolved_over_turns(monkeypatch):
    session_id = "test-appointment-followup"
    clear_session(session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent="CREATE_APPOINTMENT"))
    first = orchestrator.process_text_input("book a vet appointment", session_id=session_id)
    assert first["follow_up_questions"] == [
        "Please provide: animal ID or animal name/tag, issue/symptoms, duration, severity (mild/moderate/severe), current medication (or 'none'), appointment date, appointment time."
    ]

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={"date": "tomorrow"}))
    second = orchestrator.process_text_input("tomorrow", session_id=session_id)
    expected_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    assert second["entities"]["date"] == expected_date
    assert len(second["follow_up_questions"]) == 1
    assert "appointment time" in second["follow_up_questions"][0]
    assert "issue/symptoms" in second["follow_up_questions"][0]
    assert second["complete"] is False

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={
        "time": "17:00", "animal_name": "chutki", "issue": "fever",
        "duration": "2 days", "severity": "severe", "current_medication": "none",
    }))
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
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        intent="LOG_HEALTH",
        entities={"animal_id": "a-f-001-2", "symptoms": ["not eating"], "duration": "since yesterday"},
    ))
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
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        intent="CREATE_APPOINTMENT",
        entities={"animal_name": "chutki"},
    ))
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
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent="CREATE_ANIMAL"))

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
    session_id = "test-animal-fields-followup"
    clear_session(session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent="CREATE_ANIMAL"))
    first = orchestrator.process_text_input(
        "i want to add details about my animal", session_id=session_id
    )
    assert first["follow_up_questions"] == [
        "Please provide: whether this is a new animal registration or an existing animal update."
    ]

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={"animal_record_mode": "new"}))
    second = orchestrator.process_text_input("new", session_id=session_id)
    assert second["follow_up_questions"] == [
        "Please provide: animal name or tag, species, sex (male/female), breed, age in years, feeding details."
    ]

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={"species": "goat", "sex": "male"}))
    third = orchestrator.process_text_input("goat male", session_id=session_id)
    assert third["entities"]["species"] == "goat"
    assert third["entities"]["sex"] == "male"
    assert third["follow_up_questions"] == [
        "Please provide: animal name or tag, breed, age in years, feeding details."
    ]
    assert third["complete"] is False


def test_existing_animal_update_with_id_and_fields_completes(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        intent="UPDATE_ANIMAL",
        entities={
            "animal_id": "a-f-001-2", "animal_record_mode": "existing",
            "breed": "jamunapari", "age_years": 4.0,
            "feeding_details": "dry fodder twice daily",
        },
    ))
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


def test_non_animal_text_with_no_intent_asks_nothing(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent=None))

    session_id = "test-non-animal-book"
    clear_session(session_id)
    out = orchestrator.process_text_input(
        "i want to add details about my book", session_id=session_id
    )

    assert out["intent"] is None
    assert out["follow_up_questions"] == []
    assert out["complete"] is False


def test_existing_flow_identifier_only_then_asks_update_fields(monkeypatch):
    session_id = "test-existing-id-only"
    clear_session(session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        intent="UPDATE_ANIMAL", entities={"animal_record_mode": "existing"},
    ))
    first = orchestrator.process_text_input(
        "existing animal", session_id=session_id
    )
    assert first["intent"] == "UPDATE_ANIMAL"
    assert first["follow_up_questions"] == [
        "Please provide: animal ID or animal name/tag, the details to update (species, sex, breed, age in years, feeding details)."
    ]

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={"animal_id": "1234"}))
    second = orchestrator.process_text_input("1234", session_id=session_id)
    assert second["entities"]["animal_id"] == "1234"
    assert second["follow_up_questions"] == [
        "Please provide: the details to update (species, sex, breed, age in years, feeding details)."
    ]


def test_age_years_numeric_from_llm_is_accepted(monkeypatch):
    session_id = "test-age-word-number"
    clear_session(session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent="CREATE_ANIMAL"))
    orchestrator.process_text_input("i want to add details about my animal", session_id=session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={"animal_record_mode": "new"}))
    orchestrator.process_text_input("new animal", session_id=session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={
        "species": "goat", "animal_name": "anshul", "sex": "female",
        "breed": "abc", "feeding_details": "not feeding",
    }))
    turn = orchestrator.process_text_input(
        "animal is goat, name is anshul, sex is female, breed is abc, feeding details not feeding",
        session_id=session_id,
    )
    assert turn["follow_up_questions"] == ["Please provide: age in years."]

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={"age_years": 4.0}))
    turn2 = orchestrator.process_text_input("four years", session_id=session_id)
    assert turn2["entities"]["age_years"] == 4.0
    assert turn2["follow_up_questions"] == []
    assert turn2["complete"] is True


def test_animal_details_phrase_triggers_create_animal_intent(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent="CREATE_ANIMAL"))

    session_id = "test-animal-details-phrase"
    clear_session(session_id)
    out = orchestrator.process_text_input("i had details about my animal", session_id=session_id)

    assert out["intent"] == "CREATE_ANIMAL"


def test_create_animal_canonicalizes_noisy_alias_entities(monkeypatch):
    def _stub_noisy_llm(_: str, **kwargs):
        return {
            "intent": "CREATE_ANIMAL",
            "entities": {
                "gender": "female",
                "age": "4 years",
                "name": "anshul",
                "symptom": "not feeding",
            },
        }

    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_noisy_llm)

    session_id = "test-canonicalize-aliases"
    clear_session(session_id)
    out = orchestrator.process_text_input(
        "new animal goat breed abc", session_id=session_id
    )

    assert out["intent"] == "CREATE_ANIMAL"
    assert out["entities"]["sex"] == "female"
    assert out["entities"]["animal_name"] == "anshul"
    assert "gender" not in out["entities"]
    assert "age" not in out["entities"]
    assert "name" not in out["entities"]
    assert "symptom" not in out["entities"]


def test_new_request_after_complete_resets_animal_state(monkeypatch):
    session_id = "test-new-request-reset"
    clear_session(session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent="CREATE_ANIMAL"))
    orchestrator.process_text_input("i want to add details about my animal", session_id=session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={"animal_record_mode": "new"}))
    orchestrator.process_text_input("new animal", session_id=session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={
        "animal_name": "anshul", "species": "goat", "sex": "female",
        "breed": "abc", "age_years": 4.0, "feeding_details": "dry fodder",
    }))
    done = orchestrator.process_text_input(
        "name is anshul, goat female, breed abc, age 4 years, feeding details dry fodder",
        session_id=session_id,
    )
    assert done["complete"] is True

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        intent="UPDATE_ANIMAL", entities={"animal_record_mode": "existing"}, confidence=0.9,
    ))
    next_out = orchestrator.process_text_input(
        "i want to add details about already present animal", session_id=session_id
    )
    assert next_out["intent"] == "UPDATE_ANIMAL"
    assert next_out["complete"] is False
    assert next_out["follow_up_questions"] == [
        "Please provide: animal ID or animal name/tag, the details to update (species, sex, breed, age in years, feeding details)."
    ]


def test_switching_from_animal_update_to_appointment_resets_intent(monkeypatch):
    session_id = "test-intent-switch-to-appointment"
    clear_session(session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        intent="UPDATE_ANIMAL",
        entities={"animal_id": "a-f-001-99", "animal_record_mode": "existing", "breed": "alpha beta"},
        unavailable_fields=["feeding_details"],
    ))
    done = orchestrator.process_text_input(
        "existing animal id a-f-001-99, update breed to alpha beta and feeding details not available",
        session_id=session_id,
    )
    assert done["intent"] == "UPDATE_ANIMAL"
    assert done["complete"] is True

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        intent="CREATE_APPOINTMENT", entities={"animal_name": "charlie"}, confidence=0.9,
    ))
    out = orchestrator.process_text_input(
        "book an appointment for charlie", session_id=session_id
    )
    assert out["intent"] == "CREATE_APPOINTMENT"
    assert out["follow_up_questions"] == [
        "Please provide: issue/symptoms, duration, severity (mild/moderate/severe), current medication (or 'none'), appointment date, appointment time."
    ]
    assert out["complete"] is False


def test_appointment_time_from_llm_is_24_hour(monkeypatch):
    session_id = "test-appointment-dotted-pm"
    clear_session(session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent="CREATE_APPOINTMENT"))
    first = orchestrator.process_text_input("book a vet appointment", session_id=session_id)
    assert first["intent"] == "CREATE_APPOINTMENT"

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={
        "animal_name": "charlie", "issue": "fever", "duration": "2 days",
        "severity": "mild", "current_medication": "none",
        "date": "tomorrow", "time": "17:00",
    }))
    second = orchestrator.process_text_input(
        "for animal name charlie issue fever duration 2 days mild no medicine tomorrow 5 p.m.",
        session_id=session_id,
    )
    assert second["entities"]["time"] == "17:00"
    assert second["follow_up_questions"] == []
    assert second["complete"] is True


def test_fetch_animal_details_intent_requires_identifier(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent="FETCH_ANIMAL_DETAILS"))

    session_id = "test-fetch-animal"
    clear_session(session_id)
    out = orchestrator.process_text_input("get details of my animal", session_id=session_id)

    assert out["intent"] == "FETCH_ANIMAL_DETAILS"
    assert out["follow_up_questions"] == ["Please provide: animal ID or animal name/tag."]
    assert out["complete"] is False


def test_llm_confident_intent_is_adopted(monkeypatch):
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
                "time": "17:00",
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


def test_unavailable_fields_from_llm_skip_remaining_new_animal_fields(monkeypatch):
    session_id = "test-not-available-new-animal"
    clear_session(session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent="CREATE_ANIMAL"))
    orchestrator.process_text_input("i want to add details about my animal", session_id=session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={"animal_record_mode": "new"}))
    orchestrator.process_text_input("new", session_id=session_id)

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(entities={
        "animal_name": "anshul", "species": "goat", "sex": "female",
    }))
    third = orchestrator.process_text_input(
        "animal name is anshul, species goat, sex female", session_id=session_id
    )
    assert third["follow_up_questions"] == [
        "Please provide: breed, age in years, feeding details."
    ]

    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        unavailable_fields=["breed", "age_years", "feeding_details"],
    ))
    final = orchestrator.process_text_input("not available", session_id=session_id)
    assert final["complete"] is True
    assert final["follow_up_questions"] == []
    assert "breed" in (final["entities"].get("unavailable_fields") or [])
    assert "age_years" in (final["entities"].get("unavailable_fields") or [])
    assert "feeding_details" in (final["entities"].get("unavailable_fields") or [])


def test_unavailable_severity_completes_appointment(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        intent="CREATE_APPOINTMENT",
        entities={
            "animal_name": "charlie", "issue": "fever", "duration": "2 days",
            "current_medication": "none", "date": "tomorrow", "time": "17:00",
        },
        unavailable_fields=["severity"],
    ))

    session_id = "test-not-available-appointment"
    clear_session(session_id)

    out = orchestrator.process_text_input(
        "book appointment for animal name charlie, issue fever, duration 2 days, severity not available, no medicine, tomorrow at 5 pm",
        session_id=session_id,
    )
    assert out["intent"] == "CREATE_APPOINTMENT"
    assert out["complete"] is True
    assert out["follow_up_questions"] == []
    assert "severity" in (out["entities"].get("unavailable_fields") or [])


def test_native_script_passed_through_verbatim(monkeypatch):
    """No normalization/translation happens before the LLM call — whatever
    the farmer said reaches call_bedrock byte-for-byte, in any script."""
    seen = {"text": None}

    def _stub_llm(text: str, **kwargs):
        seen["text"] = text
        return {"intent": "CREATE_APPOINTMENT", "entities": {}, "confidence": 0.9}

    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_llm)

    session_id = "test-hi-native"
    clear_session(session_id)
    raw = "कल शाम 5 बजे चार्ली के लिए अपॉइंटमेंट बुक करो"
    out = orchestrator.process_text_input(raw, session_id=session_id)

    assert out["meta"]["working_text_en"] == raw
    assert seen["text"] == raw
    assert out["intent"] == "CREATE_APPOINTMENT"


def test_kannada_script_passed_through_verbatim(monkeypatch):
    seen = {"text": None}

    def _stub_llm(text: str, **kwargs):
        seen["text"] = text
        return {"intent": "CREATE_ANIMAL", "entities": {}, "confidence": 0.8}

    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_llm)

    session_id = "test-kn-native"
    clear_session(session_id)
    raw = "ನನ್ನ ಪ್ರಾಣಿಯ ವಿವರಗಳನ್ನು ಸೇರಿಸಿ"
    out = orchestrator.process_text_input(raw, session_id=session_id)

    assert out["meta"]["working_text_en"] == raw
    assert seen["text"] == raw
    assert out["intent"] == "CREATE_ANIMAL"


def test_telugu_script_passed_through_verbatim(monkeypatch):
    seen = {"text": None}

    def _stub_llm(text: str, **kwargs):
        seen["text"] = text
        return {"intent": "UPDATE_ANIMAL", "entities": {}, "confidence": 0.8}

    monkeypatch.setattr(orchestrator, "call_bedrock", _stub_llm)

    session_id = "test-te-native"
    clear_session(session_id)
    raw = "ఇప్పటికే ఉన్న జంతువు వివరాలు మార్చాలి"
    out = orchestrator.process_text_input(raw, session_id=session_id)

    assert out["meta"]["working_text_en"] == raw
    assert seen["text"] == raw
    assert out["intent"] == "UPDATE_ANIMAL"


def test_weather_alert_intent_requires_location(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(intent="WEATHER_ALERT"))

    session_id = "test-weather-followup"
    clear_session(session_id)
    out = orchestrator.process_text_input("give me weather alert", session_id=session_id)

    assert out["intent"] == "WEATHER_ALERT"
    assert out["follow_up_questions"] == ["Please provide: pin code or location for weather alert."]
    assert out["complete"] is False


def test_weather_alert_with_pin_completes(monkeypatch):
    monkeypatch.setattr(orchestrator, "call_bedrock", _llm(
        intent="WEATHER_ALERT",
        entities={"weather_location": "560001", "forecast_days": 3},
    ))

    session_id = "test-weather-complete"
    clear_session(session_id)
    out = orchestrator.process_text_input("weather alert for 560001 next 3 days", session_id=session_id)

    assert out["intent"] == "WEATHER_ALERT"
    assert out["entities"]["weather_location"] == "560001"
    assert out["entities"]["forecast_days"] == 3
    assert out["complete"] is True


def test_llm_exception_keeps_session_intact(monkeypatch):
    """Bedrock errors must not crash the turn — session keeps its state and
    the caller gets a well-formed (if unhelpful) response."""
    def _raise(_: str, **kwargs):
        raise RuntimeError("boto3 timeout")

    monkeypatch.setattr(orchestrator, "call_bedrock", _raise)

    session_id = "test-llm-error"
    clear_session(session_id)
    out = orchestrator.process_text_input("book an appointment", session_id=session_id)

    assert out["intent"] is None
    assert out["entities"] == {}
    assert out["complete"] is False
