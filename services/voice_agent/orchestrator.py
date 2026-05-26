import re
from difflib import get_close_matches
from typing import Any, Dict, List, Optional

from services.llm_service.bedrock_adapter import call_bedrock
from services.voice_agent.extractor import normalize_entities
from services.voice_agent.session_store import get_session, update_session
from services.voice_agent.transcribe import transcribe_audio
from storage import load_animals


INTENT_TABLE_MAP = {
    "FETCH_ANIMAL_DETAILS": ["animals"],
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
    has_animal_context = any(
        x in t for x in ["animal", "goat", "sheep", "cow", "buffalo", "cattle", "tag"]
    )

    if any(x in t for x in ["get details", "show details", "details of"]) and has_animal_context:
        return "FETCH_ANIMAL_DETAILS"
    if any(x in t for x in ["update animal", "existing animal", "update details", "edit animal"]):
        return "UPDATE_ANIMAL"
    if any(x in t for x in ["appointment", "doctor", "vet"]):
        return "CREATE_APPOINTMENT"
    if "book" in t and any(x in t for x in ["appointment", "doctor", "vet"]):
        return "CREATE_APPOINTMENT"
    if has_animal_context and any(x in t for x in ["add", "register", "new animal", "add details"]):
        return "CREATE_ANIMAL"
    if has_animal_context and any(
        x in t for x in ["details about my animal", "details about animal", "animal details"]
    ):
        return "CREATE_ANIMAL"
    if any(x in t for x in ["sick", "not eating", "fever", "problem", "injury"]):
        return "LOG_HEALTH"
    return None


def _extract_quick_entities(text: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    t = (text or "").lower()

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

    if not entities.get("feeding_details"):
        feeding_details = _extract_feeding_details(t)
        if feeding_details:
            entities["feeding_details"] = feeding_details

    if not entities.get("issue"):
        issue = _extract_issue(t)
        if issue:
            entities["issue"] = issue

    if not entities.get("duration"):
        duration = _extract_duration(t)
        if duration:
            entities["duration"] = duration

    if not entities.get("severity"):
        severity = _extract_severity(t)
        if severity:
            entities["severity"] = severity

    if not entities.get("current_medication"):
        current_medication = _extract_current_medication(t)
        if current_medication:
            entities["current_medication"] = current_medication

    if not entities.get("temperature_c"):
        temperature_c = _extract_temperature_c(t)
        if temperature_c is not None:
            entities["temperature_c"] = temperature_c

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
    entities.setdefault("feeding_details", animal.feeding_details)
    entities.setdefault("farmer_id", animal.farmer_id)
    entities.setdefault("animal_record_mode", "existing")

    return entities


def _extract_animal_record_mode(text: str) -> Optional[str]:
    t = (text or "").lower()
    existing_markers = [
        "existing",
        "old animal",
        "already present",
        "already existing",
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

    word_to_num = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }

    m_age_num = re.search(r"\bage\s*(?:is|:)?\s*(\d{1,2}(?:\.\d+)?)\b", t)
    if m_age_num:
        try:
            return float(m_age_num.group(1))
        except ValueError:
            return None

    m_age_word = re.search(r"\bage\s*(?:is|:)?\s*(zero|one|two|three|four|five|six|seven|eight|nine|ten)\b", t)
    if m_age_word:
        return float(word_to_num[m_age_word.group(1)])

    m = re.search(r"\b(\d{1,2}(?:\.\d+)?)\s*(?:years?|yrs?)\b", t)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None

    m_word_years = re.search(
        r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:years?|yrs?)\b",
        t,
    )
    if m_word_years:
        return float(word_to_num[m_word_years.group(1)])

    single_num = re.fullmatch(r"\d{1,2}(?:\.\d+)?", t.strip())
    if single_num:
        try:
            return float(single_num.group(0))
        except ValueError:
            return None

    single_word = re.fullmatch(
        r"zero|one|two|three|four|five|six|seven|eight|nine|ten",
        t.strip(),
    )
    if single_word:
        return float(word_to_num[single_word.group(0)])

    return None


def _extract_feeding_details(text: str) -> Optional[str]:
    t = (text or "").lower().strip()

    if "not feeding" in t:
        return "not feeding"

    explicit = re.search(r"\b(?:feeding\s*details?|feed\s*details?)\s*(?:is|are|:)?\s*(.+)$", t)
    if explicit:
        value = explicit.group(1).strip(" .,")
        return value or None

    if any(marker in t for marker in ["feed", "fodder", "silage", "hay", "concentrate"]):
        if len(t) <= 120:
            return t.strip(" .,")

    return None


def _extract_issue(text: str) -> Optional[str]:
    t = (text or "").lower().strip()

    explicit = re.search(
        r"\b(?:issue|problem|symptom|complaint)\s*(?:is|:)?\s*(.+?)(?:,|\bduration\b|\bseverity\b|\bdate\b|\btime\b|\bmedication\b|\bmedicine\b|$)",
        t,
    )
    if explicit:
        value = explicit.group(1).strip(" .,")
        return value or None

    symptom_phrases = [
        "not eating",
        "fever",
        "cough",
        "diarrhea",
        "loose motion",
        "vomit",
        "injury",
        "limping",
        "weakness",
        "not feeding",
    ]
    hits = [p for p in symptom_phrases if p in t]
    if hits:
        return ", ".join(hits)

    return None


def _extract_duration(text: str) -> Optional[str]:
    t = (text or "").lower().strip()

    m_duration = re.search(r"\bduration\s*(?:is|:)?\s*(\d+\s*(?:hours?|days?|weeks?|months?))\b", t)
    if m_duration:
        return m_duration.group(1).strip()

    m_since = re.search(r"\bsince\s+([a-z0-9\s-]+)$", t)
    if m_since:
        return f"since {m_since.group(1).strip(' .,')}"

    m_for = re.search(r"\bfor\s+(\d+\s*(?:hours?|days?|weeks?|months?))\b", t)
    if m_for:
        return m_for.group(1).strip()

    return None


def _extract_severity(text: str) -> Optional[str]:
    t = (text or "").lower()
    for level in ["mild", "moderate", "severe"]:
        if re.search(rf"\b{level}\b", t):
            return level
    return None


def _extract_current_medication(text: str) -> Optional[str]:
    t = (text or "").lower().strip()

    if any(x in t for x in ["no medicine", "not on medicine", "none", "no medication"]):
        return "none"

    m = re.search(r"\b(?:medicine|medication|drug|treatment)\s*(?:is|:)?\s*(.+)$", t)
    if m:
        value = m.group(1).strip(" .,")
        return value or None

    m_given = re.search(r"\bgiven\s+(.+)$", t)
    if m_given and any(x in t for x in ["tablet", "injection", "syrup", "medicine"]):
        value = m_given.group(1).strip(" .,")
        return value or None

    return None


def _extract_temperature_c(text: str) -> Optional[float]:
    t = (text or "").lower()
    m = re.search(r"\b(\d{2,3}(?:\.\d+)?)\s*(?:°?\s*c|celsius)\b", t)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None

    m_f = re.search(r"\b(\d{2,3}(?:\.\d+)?)\s*(?:°?\s*f|fahrenheit)\b", t)
    if m_f:
        try:
            f = float(m_f.group(1))
            return round((f - 32.0) * 5.0 / 9.0, 1)
        except ValueError:
            return None

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
    t = re.sub(r"\b([ap])\s*\.\s*m\.?\b", r"\1m", t)

    am_pm = re.search(r"\b([01]?\d|2[0-3])(?::([0-5]\d))?\s*(a\.?m\.?|p\.?m\.?)\b", t)
    if am_pm:
        hour = int(am_pm.group(1))
        minute = int(am_pm.group(2) or "0")
        meridiem = am_pm.group(3).replace(".", "")
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

    if ("animal id" in first_q or "animal name" in first_q) and not entities.get("animal_id"):
        loose_id_match = re.fullmatch(r"[a-z0-9-]+", t)
        if loose_id_match:
            entities["animal_id"] = loose_id_match.group(0)

    if ("details to update" in first_q or "animal name" in first_q) and not entities.get("animal_name"):
        extracted_name = _extract_animal_name(t)
        if extracted_name:
            entities["animal_name"] = extracted_name

    if ("details to update" in first_q or "feeding details" in first_q) and not entities.get("feeding_details"):
        feeding_details = _extract_feeding_details(t)
        if feeding_details:
            entities["feeding_details"] = feeding_details

    return entities


def _sync_animal_intent(intent: Optional[str], entities: Dict[str, Any]) -> Optional[str]:
    if intent not in {"CREATE_ANIMAL", "UPDATE_ANIMAL", "FETCH_ANIMAL_DETAILS"}:
        return intent

    if intent == "FETCH_ANIMAL_DETAILS":
        return intent

    mode = entities.get("animal_record_mode")
    if mode == "existing":
        return "UPDATE_ANIMAL"
    if mode == "new":
        return "CREATE_ANIMAL"
    return intent


def _canonicalize_entities(intent: Optional[str], entities: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(entities or {})

    if not out.get("sex"):
        for key in ["gender", "animal_gender"]:
            value = out.get(key)
            if isinstance(value, str) and value.strip():
                out["sex"] = value.strip().lower()
                break

    if not out.get("animal_name"):
        for key in ["name", "animal", "tag_or_name"]:
            value = out.get(key)
            if isinstance(value, str) and value.strip():
                out["animal_name"] = value.strip()
                break

    if not out.get("age_years"):
        for key in ["age", "animal_age"]:
            value = out.get(key)
            if value not in (None, ""):
                parsed = _extract_age_years(str(value))
                if parsed is not None:
                    out["age_years"] = parsed
                    break

    if intent in {"CREATE_ANIMAL", "UPDATE_ANIMAL"} and not out.get("feeding_details"):
        symptom = out.get("symptom")
        if isinstance(symptom, str) and symptom.strip() and "feed" in symptom.lower():
            out["feeding_details"] = symptom.strip().lower()

    if intent in {"CREATE_ANIMAL", "UPDATE_ANIMAL"}:
        for key in [
            "gender",
            "animal_gender",
            "name",
            "animal",
            "tag",
            "age",
            "animal_age",
            "symptom",
            "symptoms",
        ]:
            out.pop(key, None)

    return out


def _starts_new_request(text: str) -> bool:
    t = (text or "").lower().strip()
    if len(t) < 8:
        return False

    markers = [
        "i want to",
        "i need to",
        "please",
        "add details",
        "animal details",
        "get details",
        "show details",
        "update",
        "book a vet",
        "book an appointment",
        "book appointment",
        "appointment for",
        "already present animal",
        "existing animal",
        "new animal",
        "my animal",
    ]
    return any(m in t for m in markers)


def _animal_missing_fields(intent: str, entities: Dict[str, Any]) -> List[str]:
    if intent == "FETCH_ANIMAL_DETAILS":
        if not entities.get("animal_id") and not entities.get("animal_name"):
            return ["animal_identifier"]
        return []

    mode = entities.get("animal_record_mode")
    if not mode:
        return ["new_or_existing"]

    if mode == "existing":
        missing: List[str] = []
        if not entities.get("animal_id") and not entities.get("animal_name"):
            missing.append("animal_identifier")
        has_update = any(
            entities.get(k) not in (None, "")
            for k in ["species", "sex", "breed", "age_years", "feeding_details"]
        )
        if not has_update:
            missing.append("fields_to_update")
        return missing

    # Default to create/new flow
    missing = []
    for field in ["animal_name", "species", "sex", "breed", "age_years", "feeding_details"]:
        if entities.get(field) in (None, ""):
            missing.append(field)
    return missing


def _appointment_missing_fields(entities: Dict[str, Any]) -> List[str]:
    missing: List[str] = []

    if not entities.get("animal_id") and not entities.get("animal_name"):
        missing.append("animal_identifier")
    if not entities.get("issue"):
        missing.append("issue")
    if not entities.get("duration"):
        missing.append("duration")
    if not entities.get("severity"):
        missing.append("severity")
    if entities.get("current_medication") in (None, ""):
        missing.append("current_medication")
    if not entities.get("date"):
        missing.append("date")
    if not entities.get("time"):
        missing.append("time")

    return missing


def _build_appointment_followup(missing_fields: List[str]) -> str:
    labels = {
        "animal_identifier": "animal ID or animal name/tag",
        "issue": "issue/symptoms",
        "duration": "duration",
        "severity": "severity (mild/moderate/severe)",
        "current_medication": "current medication (or 'none')",
        "date": "appointment date",
        "time": "appointment time",
    }
    details = [labels[m] for m in missing_fields if m in labels]
    if not details:
        return "Please share appointment details."
    return "Please provide: " + ", ".join(details) + "."


def _build_animal_followup(missing_fields: List[str]) -> str:
    labels = {
        "new_or_existing": "whether this is a new animal registration or an existing animal update",
        "animal_identifier": "animal ID or animal name/tag",
        "fields_to_update": "the details to update (species, sex, breed, age in years, feeding details)",
        "animal_name": "animal name or tag",
        "species": "species",
        "sex": "sex (male/female)",
        "breed": "breed",
        "age_years": "age in years",
        "feeding_details": "feeding details",
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
    elif intent == "FETCH_ANIMAL_DETAILS":
        missing_fields = _animal_missing_fields(intent, entities)
        if missing_fields:
            questions.append("Please provide: animal ID or animal name/tag.")
    elif intent == "LOG_HEALTH":
        if not entities.get("symptoms"):
            questions.append("What symptoms are you observing?")
    elif intent == "CREATE_APPOINTMENT":
        missing_fields = _appointment_missing_fields(entities)
        if missing_fields:
            questions.append(_build_appointment_followup(missing_fields))
    return questions


def process_text_input(text: str, session_id: str = "default") -> Dict[str, Any]:
    normalized_text = _normalize_text(text)

    session = get_session(session_id)
    entities = dict(session.get("entities") or {})
    pending_questions = list(session.get("pending_questions") or [])
    session_intent = session.get("intent")
    detected_intent = _detect_intent_rule(normalized_text)

    if not pending_questions and detected_intent and detected_intent != session_intent:
        entities = {}
        session_intent = None

    if not pending_questions and _starts_new_request(normalized_text):
        entities = {}
        session_intent = None

    llm_raw = None
    confidence = 0.0
    intent = session_intent or detected_intent
    llm_followups: List[str] = []
    llm_missing_fields: List[str] = []

    # Best-effort LLM enrichment
    try:
        llm_response = call_bedrock(
            normalized_text,
            context={
                "intent": session_intent,
                "entities": entities,
                "pending_questions": pending_questions,
            },
        )
        llm_raw = llm_response.get("_raw")
        confidence = float(llm_response.get("confidence", 0.0) or 0.0)
        llm_followups = [str(x).strip() for x in (llm_response.get("follow_up_questions") or []) if str(x).strip()]
        llm_missing_fields = [str(x).strip() for x in (llm_response.get("missing_fields") or []) if str(x).strip()]
        llm_intent = llm_response.get("intent")
        if llm_intent and (not intent or confidence >= 0.55):
            intent = llm_intent
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
    entities = _canonicalize_entities(intent, entities)

    followups = _generate_followups(intent, entities)

    # Agentic enhancement: if deterministic rules are satisfied but LLM still asks
    # for fields, include one compact follow-up to handle free-form user phrasing.
    if not followups and llm_followups and llm_missing_fields:
        followups = [llm_followups[0]]

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
