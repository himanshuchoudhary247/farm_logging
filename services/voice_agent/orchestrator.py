import time
import logging
from difflib import get_close_matches
from typing import Any, Dict, List, Optional

_log = logging.getLogger("orchestrator")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

from services.llm_service.bedrock_adapter import call_bedrock
from services.voice_agent.extractor import normalize_entities
from services.voice_agent.session_store import get_session, update_session
from services.voice_agent.transcribe import transcribe_audio
from storage import load_animals

# No regex or keyword rules parse user input in this module. The farmer can
# phrase a request in any language, script, or word order — call_bedrock()
# (services/llm_service/bedrock_adapter.py) is the single extraction engine
# for intent + every entity. Everything below this point only reshapes,
# validates, and merges the LLM's structured output; it never re-reads the
# raw text.

INTENT_TABLE_MAP = {
    "WEATHER_ALERT": ["weather_alerts"],
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


def _mark_fields_unavailable(entities: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    unavailable = entities.get("unavailable_fields") or []
    if not isinstance(unavailable, list):
        unavailable = []
    merged = set(str(x) for x in unavailable)
    for field in fields:
        merged.add(field)
    entities["unavailable_fields"] = sorted(merged)
    return entities


def _has_value_or_unavailable(entities: Dict[str, Any], field: str) -> bool:
    value = entities.get(field)
    if value not in (None, "", []):
        return True
    unavailable = entities.get("unavailable_fields") or []
    return field in unavailable


def _prefill_animal_details(entities: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich a farmer's known animal profile once the LLM has identified an
    animal_id, animal_name, or animal_tag. Matches by exact id/name and falls
    back to fuzzy name matching (difflib) — no text scanning, this only
    compares already-extracted entity values against stored records."""
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

    animal_id = str(entities.get("animal_id") or "").strip().lower()
    animal_name = str(entities.get("animal_name") or entities.get("animal_tag") or "").strip().lower()

    match = None
    if animal_id:
        match = next((a for a in animals if a.id.lower() == animal_id), None)
    if not match and animal_name:
        by_name = {a.tag_or_name.lower(): a for a in animals}
        match = by_name.get(animal_name)
        if not match:
            fuzzy = get_close_matches(animal_name, list(by_name.keys()), n=1, cutoff=0.75)
            if fuzzy:
                match = by_name[fuzzy[0]]

    if not match:
        return entities

    species_hint = str(entities.get("species") or "").strip().lower()
    if species_hint and match.species.lower() != species_hint:
        return entities

    entities.setdefault("animal_id", match.id)
    entities["animal_name"] = match.tag_or_name
    entities.setdefault("species", match.species)
    entities.setdefault("breed", match.breed)
    entities.setdefault("age_years", match.age_years)
    entities.setdefault("feeding_details", match.feeding_details)
    entities.setdefault("farmer_id", match.farmer_id)
    entities.setdefault("animal_record_mode", "existing")

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
    """Fold alias keys an LLM might emit (gender/age/name/symptom) onto the
    canonical schema. Pure dict reshaping, no text parsing."""
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
                try:
                    out["age_years"] = float(value)
                    break
                except (TypeError, ValueError):
                    continue

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


def _weather_missing_fields(entities: Dict[str, Any]) -> List[str]:
    if entities.get("weather_location"):
        return []
    return ["weather_location"]


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
            _has_value_or_unavailable(entities, k)
            for k in ["species", "sex", "breed", "age_years", "feeding_details"]
        )
        if not has_update:
            missing.append("fields_to_update")
        return missing

    # Default to create/new flow
    missing = []
    for field in ["animal_name", "species", "sex", "breed", "age_years", "feeding_details"]:
        if not _has_value_or_unavailable(entities, field):
            missing.append(field)
    return missing


def _appointment_missing_fields(entities: Dict[str, Any]) -> List[str]:
    missing: List[str] = []

    if not entities.get("animal_id") and not entities.get("animal_name"):
        missing.append("animal_identifier")
    if not _has_value_or_unavailable(entities, "issue"):
        missing.append("issue")
    if not _has_value_or_unavailable(entities, "duration"):
        missing.append("duration")
    if not _has_value_or_unavailable(entities, "severity"):
        missing.append("severity")
    if not _has_value_or_unavailable(entities, "current_medication"):
        missing.append("current_medication")
    if not _has_value_or_unavailable(entities, "date"):
        missing.append("date")
    if not _has_value_or_unavailable(entities, "time"):
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
    elif intent == "WEATHER_ALERT":
        missing_fields = _weather_missing_fields(entities)
        if missing_fields:
            questions.append("Please provide: pin code or location for weather alert.")
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
    t0 = time.time()
    working_text = text or ""

    session = get_session(session_id)
    entities = dict(session.get("entities") or {})
    pending_questions = list(session.get("pending_questions") or [])
    session_intent = session.get("intent")

    t_llm_start = time.time()
    try:
        llm_response = call_bedrock(
            working_text,
            context={
                "intent": session_intent,
                "entities": entities,
                "pending_questions": pending_questions,
            },
        )
    except Exception as exc:
        import traceback
        _log.warning("LLM extraction failed: %s\n%s", exc, traceback.format_exc())
        llm_response = {}
    llm_ms = (time.time() - t_llm_start) * 1000

    llm_raw = llm_response.get("_raw")
    confidence = float(llm_response.get("confidence", 0.0) or 0.0)
    llm_intent = llm_response.get("intent")
    llm_entities = llm_response.get("entities") or {}
    llm_unavailable = llm_response.get("unavailable_fields") or []

    # Adopt the LLM's intent. Mid-flow (an open follow-up question), only
    # switch on high confidence so a stray word doesn't derail an in-progress
    # booking; otherwise the LLM is free to set/replace the session intent.
    intent = session_intent
    if llm_intent and llm_intent != session_intent:
        if not pending_questions or confidence >= 0.55:
            intent = llm_intent
            if not pending_questions:
                entities = {}
    elif not intent:
        intent = llm_intent

    entities.update(llm_entities)
    if llm_unavailable:
        entities = _mark_fields_unavailable(entities, list(llm_unavailable))

    entities = _prefill_animal_details(entities)
    entities = normalize_entities(entities)
    intent = _sync_animal_intent(intent, entities)
    entities = _canonicalize_entities(intent, entities)

    followups = _generate_followups(intent, entities)

    # If deterministic rules are satisfied but the LLM still flagged a
    # follow-up, surface its (free-form, correctly-phrased) question.
    llm_followups = [str(x).strip() for x in (llm_response.get("follow_up_questions") or []) if str(x).strip()]
    if not followups and llm_followups:
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

    total_ms = (time.time() - t0) * 1000
    _log.info(
        "LATENCY process_text_input total=%.0fms llm=%.0fms session=%s",
        total_ms, llm_ms, session_id,
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
            "raw_text": text,
            "working_text_en": working_text,
            "confidence": confidence,
            "session_id": session_id,
        },
        "timing": {
            "total_ms": round(total_ms),
            "llm_ms": round(llm_ms),
        },
        "_raw": llm_raw,
    }


def process_voice(audio_bytes: bytes, session_id: str = "default") -> Dict[str, Any]:
    text = transcribe_audio(audio_bytes)
    return process_text_input(text, session_id=session_id)
