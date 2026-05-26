import re
from difflib import get_close_matches
from typing import Any, Dict, List, Optional

from services.llm_service.bedrock_adapter import call_bedrock
from services.voice_agent.extractor import normalize_entities
from services.voice_agent.session_store import get_session, update_session
from services.voice_agent.transcribe import transcribe_audio
from storage import load_animals


INTENT_TABLE_MAP = {
    "CREATE_ANIMAL": ["animals"],
    "UPDATE_ANIMAL": ["animals"],
    "LOG_HEALTH": ["health_logs", "animals_health_records"],
    "CREATE_APPOINTMENT": ["appointments"],
}


def _resolve_tables(intent: Optional[str]) -> List[str]:
    if not intent:
        return []
    return INTENT_TABLE_MAP.get(intent, [])


def _normalize_text(text: str) -> str:
    if not text:
        return text
    t = text.lower().strip()
    replacements = {
        "coat": "goat",
        "route": "goat",
        "boat": "goat",
    }
    for src, dst in replacements.items():
        t = t.replace(src, dst)
    return t


def _detect_intent_rule(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(x in t for x in ["update animal", "existing animal", "update details", "edit animal"]):
        return "UPDATE_ANIMAL"
    if any(x in t for x in ["add", "register", "new animal", "add details"]):
        return "CREATE_ANIMAL"
    if any(x in t for x in ["sick", "not eating", "fever", "problem", "injury"]):
        return "LOG_HEALTH"
    if any(x in t for x in ["appointment", "doctor", "vet", "book"]):
        return "CREATE_APPOINTMENT"
    return None


def _extract_quick_entities(text: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    t = (text or "").lower()

    if not entities.get("animal_record_mode"):
        mode = _extract_animal_record_mode(t)
        if mode:
            entities["animal_record_mode"] = mode

    if not entities.get("animal_name"):
        name = _extract_animal_name(t)
        if name:
            entities["animal_name"] = name

    if not entities.get("breed"):
        breed = _extract_breed(t)
        if breed:
            entities["breed"] = breed

    if not entities.get("age_years"):
        age_years = _extract_age_years(t)
        if age_years is not None:
            entities["age_years"] = age_years

    if not entities.get("species"):
        for species in ["goat", "sheep", "cow", "buffalo"]:
            if species in t:
                entities["species"] = species
                break

    if not entities.get("sex"):
        if "female" in t:
            entities["sex"] = "female"
        elif "male" in t:
            entities["sex"] = "male"

    if "not eating" in t:
        symptoms = entities.get("symptoms") or []
        if isinstance(symptoms, str):
            symptoms = [symptoms]
        if "not eating" not in symptoms:
            symptoms.append("not eating")
        entities["symptoms"] = symptoms

    if not entities.get("date"):
        date = _extract_date(t)
        if date:
            entities["date"] = date

    if not entities.get("time"):
        time = _extract_time(t)
        if time:
            entities["time"] = time

    # Explicit id mention implies an existing animal update flow.
    if not entities.get("animal_id"):
        id_match = re.search(r"\b(?:animal\s*id|id)\s*(?:is|:)?\s*([a-z0-9-]+)\b", t)
        if id_match:
            entities["animal_id"] = id_match.group(1)
            entities.setdefault("animal_record_mode", "existing")

    return entities


def _contains_exact_token(text: str, token: str) -> bool:
    if not token:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(token.lower())}(?![a-z0-9])", text) is not None


def _prefill_animal_details(text: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    t = (text or "").lower()
    preferred_farmer_id = entities.get("farmer_id")

    try:
        animals = load_animals()
    except Exception:
        return entities

    if preferred_farmer_id:
        scoped = [a for a in animals if a.farmer_id == preferred_farmer_id]
        if scoped:
            animals = scoped

    if not animals:
        return entities

    candidates = []
    existing_animal_id = str(entities.get("animal_id") or "").strip().lower()
    existing_animal_name = str(entities.get("animal_name") or "").strip().lower()

    for animal in animals:
        aid = animal.id.lower()
        name = animal.tag_or_name.lower()
        if existing_animal_id and aid == existing_animal_id:
            candidates.append(animal)
            continue
        if existing_animal_name and name == existing_animal_name:
            candidates.append(animal)
            continue
        if _contains_exact_token(t, aid) or _contains_exact_token(t, name):
            candidates.append(animal)

    if not candidates:
        id_match = re.search(r"\b(?:animal\s*id|id)\s*(?:is|:)?\s*([a-z0-9-]+)\b", t)
        if id_match:
            id_token = id_match.group(1)
            candidates = [a for a in animals if a.id.lower() == id_token]

    if not candidates:
        name_match = re.search(r"\b(?:animal\s*name|name|tag)\s*(?:is|:)?\s*([a-z0-9-]+)\b", t)
        if name_match:
            name_token = name_match.group(1)
            by_name = {a.tag_or_name.lower(): a for a in animals}
            if name_token in by_name:
                candidates = [by_name[name_token]]
            else:
                fuzzy = get_close_matches(name_token, list(by_name.keys()), n=1, cutoff=0.75)
                if fuzzy:
                    candidates = [by_name[fuzzy[0]]]

    if not candidates:
        return entities

    species_hint = str(entities.get("species") or "").strip().lower()
    if species_hint:
        species_filtered = [a for a in candidates if a.species.lower() == species_hint]
        if species_filtered:
            candidates = species_filtered

    unique_candidates: Dict[str, Any] = {a.id: a for a in candidates}
    if len(unique_candidates) != 1:
        return entities

    animal = list(unique_candidates.values())[0]
    entities.setdefault("animal_id", animal.id)
    entities["animal_name"] = animal.tag_or_name
    entities.setdefault("species", animal.species)
    entities.setdefault("breed", animal.breed)
    entities.setdefault("age_years", animal.age_years)
    entities.setdefault("farmer_id", animal.farmer_id)
    entities.setdefault("animal_record_mode", "existing")

    return entities


def _extract_animal_record_mode(text: str) -> Optional[str]:
    t = (text or "").lower()
    existing_markers = [
        "existing",
        "old animal",
        "update",
        "change",
        "edit",
        "already registered",
    ]
    new_markers = ["new", "new animal", "register", "add new", "new registration"]

    if any(marker in t for marker in existing_markers):
        return "existing"
    if any(marker in t for marker in new_markers):
        return "new"
    return None


def _extract_animal_name(text: str) -> Optional[str]:
    t = (text or "").lower().strip()
    m = re.search(r"\b(?:animal\s*name|name|tag)\s*(?:is|:)?\s*([a-z0-9-]+)\b", t)
    if m:
        return m.group(1)
    return None


def _extract_breed(text: str) -> Optional[str]:
    t = (text or "").lower().strip()
    m = re.search(r"\bbreed\s*(?:is|:|to)?\s*([a-z][a-z0-9-]*)\b", t)
    if m:
        return m.group(1)
    return None


def _extract_age_years(text: str) -> Optional[float]:
    t = (text or "").lower()
    m = re.search(r"\b(\d{1,2}(?:\.\d+)?)\s*(?:years?|yrs?)\b", t)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _extract_date(text: str) -> Optional[str]:
    t = (text or "").lower()
    for token in ["today", "tomorrow", "yesterday"]:
        if re.search(rf"\b{token}\b", t):
            return token

    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
    if iso_match:
        return iso_match.group(1)

    return None


def _extract_time(text: str) -> Optional[str]:
    t = (text or "").lower()

    am_pm = re.search(r"\b([01]?\d|2[0-3])(?::([0-5]\d))?\s*(am|pm)\b", t)
    if am_pm:
        hour = int(am_pm.group(1))
        minute = int(am_pm.group(2) or "0")
        meridiem = am_pm.group(3)
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"

    hh_mm = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
    if hh_mm:
        hour = int(hh_mm.group(1))
        minute = int(hh_mm.group(2))
        return f"{hour:02d}:{minute:02d}"

    return None


def _apply_followup_answer(
    text: str,
    intent: Optional[str],
    pending_questions: List[str],
    entities: Dict[str, Any],
) -> Dict[str, Any]:
    t = (text or "").lower().strip()
    if not pending_questions:
        return entities

    first_q = pending_questions[0].lower()

    if "type of animal" in first_q and not entities.get("species"):
        for species in ["goat", "sheep", "cow", "buffalo"]:
            if species in t:
                entities["species"] = species
                break

    if "male or female" in first_q and not entities.get("sex"):
        if "female" in t:
            entities["sex"] = "female"
        elif "male" in t:
            entities["sex"] = "male"

    if intent == "LOG_HEALTH" and "symptoms" in first_q and not entities.get("symptoms"):
        entities["symptoms"] = [text.strip()] if text.strip() else []

    if "date" in first_q and not entities.get("date"):
        date = _extract_date(t)
        if date:
            entities["date"] = date

    if "time" in first_q and not entities.get("time"):
        time = _extract_time(t)
        if time:
            entities["time"] = time

    if "new animal registration" in first_q and not entities.get("animal_record_mode"):
        mode = _extract_animal_record_mode(t)
        if mode:
            entities["animal_record_mode"] = mode

    return entities


def _sync_animal_intent(intent: Optional[str], entities: Dict[str, Any]) -> Optional[str]:
    mode = entities.get("animal_record_mode")
    if mode == "existing":
        return "UPDATE_ANIMAL"
    if mode == "new":
        return "CREATE_ANIMAL"
    if intent not in {"CREATE_ANIMAL", "UPDATE_ANIMAL"}:
        return intent
    return intent


def _animal_missing_fields(intent: str, entities: Dict[str, Any]) -> List[str]:
    mode = entities.get("animal_record_mode")
    if not mode:
        return ["new_or_existing"]

    if mode == "existing":
        missing: List[str] = []
        if not entities.get("animal_id") and not entities.get("animal_name"):
            missing.append("animal_identifier")
        has_update = any(
            entities.get(k) not in (None, "") for k in ["species", "sex", "breed", "age_years"]
        )
        if not has_update:
            missing.append("fields_to_update")
        return missing

    # Default to create/new flow
    missing = []
    for field in ["animal_name", "species", "sex", "breed", "age_years"]:
        if entities.get(field) in (None, ""):
            missing.append(field)
    return missing


def _build_animal_followup(missing_fields: List[str]) -> str:
    labels = {
        "new_or_existing": "whether this is a new animal registration or an existing animal update",
        "animal_identifier": "animal ID or animal name/tag",
        "fields_to_update": "the details to update (species, sex, breed, age in years)",
        "animal_name": "animal name or tag",
        "species": "species",
        "sex": "sex (male/female)",
        "breed": "breed",
        "age_years": "age in years",
    }
    details = [labels[m] for m in missing_fields if m in labels]
    if not details:
        return "Please share the missing animal details."
    return "Please provide: " + ", ".join(details) + "."


def _generate_followups(intent: Optional[str], entities: Dict[str, Any]) -> List[str]:
    if not intent:
        return []

    questions: List[str] = []
    if intent in {"CREATE_ANIMAL", "UPDATE_ANIMAL"}:
        missing_fields = _animal_missing_fields(intent, entities)
        if missing_fields:
            questions.append(_build_animal_followup(missing_fields))
    elif intent == "LOG_HEALTH":
        if not entities.get("symptoms"):
            questions.append("What symptoms are you observing?")
    elif intent == "CREATE_APPOINTMENT":
        missing_date = not entities.get("date")
        missing_time = not entities.get("time")
        if missing_date and missing_time:
            questions.append("What date and time should the appointment be?")
        elif missing_date:
            questions.append("What date should the appointment be?")
        elif missing_time:
            questions.append("What time should the appointment be?")
    return questions


def process_text_input(text: str, session_id: str = "default") -> Dict[str, Any]:
    normalized_text = _normalize_text(text)

    session = get_session(session_id)
    entities = dict(session.get("entities") or {})
    pending_questions = list(session.get("pending_questions") or [])

    llm_raw = None
    confidence = 0.0
    intent = session.get("intent") or _detect_intent_rule(normalized_text)

    # Best-effort LLM enrichment
    try:
        llm_response = call_bedrock(normalized_text)
        llm_raw = llm_response.get("_raw")
        confidence = float(llm_response.get("confidence", 0.0) or 0.0)
        if not intent:
            intent = llm_response.get("intent")
        llm_entities = llm_response.get("entities", {}) or {}
        entities.update(llm_entities)
    except Exception:
        # Keep deterministic flow even if LLM is unavailable
        pass

    # Merge quick entities and direct follow-up answers
    entities = _extract_quick_entities(normalized_text, entities)
    entities = _prefill_animal_details(normalized_text, entities)
    entities = _apply_followup_answer(normalized_text, intent, pending_questions, entities)
    entities = normalize_entities(entities)
    intent = _sync_animal_intent(intent, entities)

    followups = _generate_followups(intent, entities)
    complete = bool(intent) and len(followups) == 0
    tables = _resolve_tables(intent)

    update_session(
        session_id,
        {
            "intent": intent,
            "entities": entities,
            "pending_questions": followups,
        },
    )

    return {
        "intent": intent,
        "target_tables": tables,
        "entities": entities,
        "disambiguation": {
            "required": len(followups) > 0,
            "questions": followups,
            "options": {},
        },
        "follow_up_questions": followups,
        "complete": complete,
        "meta": {
            "raw_text": normalized_text,
            "confidence": confidence,
            "session_id": session_id,
        },
        "_raw": llm_raw,
    }


def process_voice(audio_bytes: bytes, session_id: str = "default") -> Dict[str, Any]:
    text = transcribe_audio(audio_bytes)
    return process_text_input(text, session_id=session_id)
