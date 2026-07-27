from __future__ import annotations

import json as _json
import logging
import os
import re as _re
import time
from datetime import datetime
from typing import Any, Optional

from llm.adapters import TextAdapter, get_text_adapter
from services.farmer_onboarding_service.models import (
    FARM_FIELDS,
    FARMER_FIELDS,
)

log = logging.getLogger("onboarding.extraction")

_FIELD_QUESTIONS: dict[str, str] = {
    "aadharNo": "What is your Aadhar number?",
    "gender": "What is your gender?",
    "fatherOrSpouseName": "What is your father's or spouse's name?",
    "alternateMobile": "Do you have an alternate mobile number?",
    "address_1": "What is your residential address?",
    "city": "Which city do you live in?",
    "state": "Which state are you from?",
    "pincode": "What is your pincode?",
    "dob": "What is your date of birth?",
    "education": "What is your highest education?",
    "occupation": "What is your occupation?",
    "farmingExperience": "How many years of farming experience do you have?",
    "landHolding": "How much land do you hold (in acres/hectares)?",
    "religion": "What is your religion?",
    "caste": "What is your caste category?",
    "panNo": "Do you have a PAN card? What is your PAN number?",
    "farmName": "What is your farm name?",
    "email": "What is your email address?",
    "phone": "What is your phone number?",
    "farmPhone": "What is your farm phone number?",
    "alternatePhone": "Do you have an alternate phone number for the farm?",
    "address": "What is your farm's address?",
    "farmCity": "Which city is your farm in?",
    "district": "Which district is your farm in?",
    "farmPincode": "What is your farm's pincode?",
    "farmState": "Which state is your farm in?",
    "totalAnimalCapacity": "How many animals can your farm hold?",
    "currentAnimalCount": "How many animals do you currently have?",
    "sheepCount": "How many sheep do you have?",
    "goatCount": "How many goats do you have?",
}

_LANG_INSTRUCTIONS = {
    "hi": "Ask the next question in Hindi (हिंदी). Use Devanagari script.",
    "kn": "Ask the next question in Kannada (ಕನ್ನಡ). Use Kannada script.",
    "te": "Ask the next question in Telugu (తెలుగు). Use Telugu script.",
    "en": "Ask the next question in English.",
    "mix": "Ask the next question in Hinglish (Hindi + English, Latin script).",
    "mix-hi": "Ask the next question in Hinglish (Hindi + English, Latin script).",
    "mix-kn": "Ask in Kannada + English mix.",
    "mix-te": "Ask in Telugu + English mix.",
}


# ── Deterministic validation ────────────────────────────────────

_VALIDATORS: dict[str, tuple[str, object]] = {
    "aadharNo": ("string", r"^\d{12}$"),
    "phone": ("string", r"^\d{10}$"),
    "alternateMobile": ("string", r"^\d{10}$"),
    "pincode": ("string", r"^\d{6}$"),
    "email": ("string", r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    "dob": ("date", None),
    "gender": ("enum", ["male", "female", "other"]),
    "hasPanCard": ("enum", ["yes", "no", "true", "false"]),
    "hasGovernmentId": ("enum", ["yes", "no", "true", "false"]),
}

# Fields where value MUST be purely numeric; extract digits from natural-language noise
_NUMERIC_FIELDS = {"farmingExperience", "landHolding", "totalAnimalCapacity", "currentAnimalCount", "sheepCount", "goatCount"}


def _validate(field: str, value: Any) -> str | None:
    """Return error message if invalid, None if OK."""
    rule = _VALIDATORS.get(field)
    if rule is None:
        return None
    kind, spec = rule
    s = str(value).strip().lower() if value is not None else ""
    if kind == "string" and spec:
        if not _re.match(spec, s):
            return f"Invalid {field}: expected {spec}"
    if kind == "enum" and spec:
        if s not in spec:
            return f"Invalid {field}: must be one of {spec}"
    if kind == "date":
        try:
            datetime.strptime(s[:10], "%Y-%m-%d")
        except (ValueError, IndexError):
            return "Invalid date: use YYYY-MM-DD format"
    return None


def _resolve_section(field: str, farmer_missing: list[str], farm_missing: list[str], hint: Optional[str] = None) -> str:
    """Determine section for a field. Only ambiguous if field exists in both FarmerDetails and FarmDetails."""
    if hint:
        return hint
    if field in FARMER_FIELDS and field not in FARM_FIELDS:
        return "farmer"
    if field in FARM_FIELDS and field not in FARMER_FIELDS:
        return "farm"
    if field in farmer_missing and field not in farm_missing:
        return "farmer"
    if field in farm_missing and field not in farmer_missing:
        return "farm"
    return "farmer"


def _validate_merged(farmer: dict, farm: dict) -> tuple[dict, dict, list[str]]:
    """Return (farmer_with_errors_as_empty, fields_with_errors)."""
    error_fields = []
    for section, fields in [("farmer", farmer), ("farm", farm)]:
        for fname, val in list(fields.items()):
            err = _validate(fname, val)
            if err:
                log.info("VALIDATION_FAIL field=%s value=%r reason=%s", fname, val, err)
                error_fields.append(fname)
                if section == "farmer":
                    farmer[fname] = ""
                else:
                    farm[fname] = ""
    return farmer, farm, error_fields


def _clean_numeric(raw: str) -> str:
    """Strip non-digit noise from a numeric field value (e.g. '20 years' -> '20')."""
    digits = _re.sub(r"[^\d]", "", raw)
    return digits if digits else raw


_SKIP_KEYWORDS = {"skip", "next", "dont know", "don't know",
                  "na", "n/a", "not applicable", "i don't know", "i dont know",
                  "unknown", "not sure", "pass", "कोई नहीं", "पता नहीं",
                  "नहीं पता", "skip karo", "aage badho", "ಬಿಟ್ಟು", "ಗೊತ್ತಿಲ್ಲ",
                  "తెలియదు", "వద్దు"}


def _is_skip(text: str) -> bool:
    t = text.strip().lower().rstrip(".!?")
    return t in _SKIP_KEYWORDS or len(t.split()) <= 2 and any(w in _SKIP_KEYWORDS for w in t.split())


# ── Helpers ──────────────────────────────────────────────────────

def _has_value(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str) and not v.strip():
        return False
    return True


def _all_missing(section: dict, fields: list[str]) -> list[str]:
    return [f for f in fields if not _has_value(section.get(f))]


_LLM_SYSTEM = """You are a farmer onboarding assistant for a livestock farm management system in India.
Extract farmer personal details and farm details from the conversation.
Return ONLY valid JSON. No markdown, no backticks."""


_DEFAULT_ADAPTER: Optional[TextAdapter] = None


def _adapter() -> TextAdapter:
    global _DEFAULT_ADAPTER
    if _DEFAULT_ADAPTER is None:
        try:
            _DEFAULT_ADAPTER = get_text_adapter()
        except Exception:
            from llm.adapters import BedrockAdapter
            _DEFAULT_ADAPTER = BedrockAdapter(
                model_id=(os.environ.get("LLM_MODEL_ID") or "mistral.mistral-large-2402-v1:0"),
                region=os.environ.get("AWS_REGION") or "ap-south-1",
            )
    return _DEFAULT_ADAPTER


def extract(
    text: str,
    existing: Optional[dict] = None,
    language: str = "en",
    adapter: Optional[TextAdapter] = None,
    current_field: Optional[str] = None,
    current_section: Optional[str] = None,
) -> dict[str, Any]:
    """Extract fields from user utterance."""
    t0 = time.time()
    llm = adapter or _adapter()
    prev = existing or {}
    prev_farmer = prev.get("farmer", {})
    prev_farm = prev.get("farm", {})

    log.info("EXTRACT_START text=%r current_field=%s language=%s prev_farmer_keys=%d", text, current_field, language, len(prev_farmer))

    # Handle skip keywords
    if _is_skip(text):
        filled_farmer = {k: v for k, v in prev_farmer.items() if _has_value(v)}
        filled_farm = {k: v for k, v in prev_farm.items() if _has_value(v)}
        still_missing_farmer = _all_missing(filled_farmer, FARMER_FIELDS)
        still_missing_farm = _all_missing(filled_farm, FARM_FIELDS)
        still_missing = still_missing_farmer + still_missing_farm
        log.info("EXTRACT_SKIP remaining=%d", len(still_missing))
        if still_missing:
            next_f = still_missing[0]
            return {
                "farmer": filled_farmer,
                "farm": filled_farm,
                "missing_fields": still_missing,
                "follow_up_question": _FIELD_QUESTIONS.get(next_f, f"Please tell me: {next_f}"),
                "complete": False,
                "confidence": None,
                "confirm_fields": [],
            }
        return {
            "farmer": filled_farmer, "farm": filled_farm,
            "missing_fields": [], "follow_up_question": None, "complete": True,
            "confidence": None, "confirm_fields": [],
        }

    filled_farmer = {k: v for k, v in prev_farmer.items() if _has_value(v)}
    filled_farm = {k: v for k, v in prev_farm.items() if _has_value(v)}

    missing_farmer = _all_missing(filled_farmer, FARMER_FIELDS)
    missing_farm = _all_missing(filled_farm, FARM_FIELDS)
    all_missing = missing_farmer + missing_farm

    lang_code = language or "en"
    lang_instruction = _LANG_INSTRUCTIONS.get(
        lang_code,
        _LANG_INSTRUCTIONS.get(lang_code.replace("mix-", "mix"), "Ask the next question in English."),
    )

    current_field_hint = f" (currently asking about: {current_field})" if current_field else ""
    prompt = f"""The farmer said: "{text}"{current_field_hint}

Already collected — Farmer personal:
{_json.dumps(filled_farmer, ensure_ascii=False, indent=2)}

Already collected — Farm details:
{_json.dumps(filled_farm, ensure_ascii=False, indent=2)}

Still needed: {_json.dumps(all_missing, ensure_ascii=False)}

Extract ALL fields you can identify from the farmer's message. CRITICAL RULES:
- Store values in English/numeric only. Accept what the farmer says as their answer.
- If the farmer provides info for multiple fields, extract ALL of them (not just one).
- aadharNo, panNo, phone, pincode → strings
- landHolding, animal counts, capacity → numbers  
- dob → YYYY-MM-DD
- name and fatherOrSpouseName → accept ANY non-empty string as valid, even a single word
- If only one field is still missing and the farmer says a short word/phrase, treat it as the answer for that field
- hasPanCard: Set to "yes" if farmer provides a panNo or says "I have a PAN card". Set to "no" if they say "I don't have" or "no PAN card".
- religion and caste: Extract whenever the farmer mentions these (e.g. "I follow X", "I belong to X category"). Do not skip them.
- FARM FIELDS are prefixed: farmName, farmPhone, farmCity, farmState, farmPincode.
  Farmer personal fields are UNPREFIXED: name, phone, city, state, pincode.
  Example: farm "pincode 302001" goes to farm.farmPincode, not farmer.pincode.
  Never use unprefixed field names in the farm object. Never use prefixed names in the farmer object.
- 6-digit numbers near address/city/farm context are farmPincode, not farmer pincode.
- {lang_instruction}
- follow_up_question: Ask for the single most important STILL-MISSING field. If none remain, set to null.

Return JSON only:
- farmer: all extracted farmer fields (or empty object)
- farm: all extracted farm fields (or empty object)
- follow_up_question: next question string, or null if all done"""

    t_llm = time.time()
    try:
        raw = llm.complete(messages=[{"role": "user", "content": prompt}], system=_LLM_SYSTEM)
        parsed = _json.loads(raw.strip())
        llm_ok = True
    except Exception as e:
        log.warning("LLM_PARSE_FAIL error=%s raw=%r", e, raw if 'raw' in dir() else "N/A")
        parsed = {}
        llm_ok = False
    t_llm_elapsed = time.time() - t_llm

    extracted_farmer = parsed.get("farmer", {})
    extracted_farm = parsed.get("farm", {})
    llm_fq = parsed.get("follow_up_question")

    # Remap common LLM mistakes: unprefixed farm fields and prefixed farmer fields
    _FARM_PREFIX_REMAP = {"name": "farmName", "city": "farmCity", "state": "farmState", "pincode": "farmPincode", "phone": "farmPhone"}
    for old_k, new_k in list(_FARM_PREFIX_REMAP.items()):
        if old_k in extracted_farm and old_k not in FARMER_FIELDS:
            extracted_farm[new_k] = extracted_farm.pop(old_k)
            log.info("REMAP_FARM_FIELD %s -> %s", old_k, new_k)
        if new_k in extracted_farmer:
            extracted_farmer[new_k.replace("farm", "farm ")]  # drop silently
            del extracted_farmer[new_k]
            log.info("REMAP_FARMER_DROP %s", new_k)

    log.info("LLM_DONE ok=%s elapsed=%.2fs extracted_farmer_keys=%d extracted_farm_keys=%d",
             llm_ok, t_llm_elapsed, len(extracted_farmer), len(extracted_farm))

    merged_farmer = dict(filled_farmer)
    for k, v in extracted_farmer.items():
        if _has_value(v):
            merged_farmer[k] = v
            log.info("MERGE_LLM section=farmer field=%s value=%r", k, v)

    merged_farm = dict(filled_farm)
    for k, v in extracted_farm.items():
        if _has_value(v):
            merged_farm[k] = v
            log.info("MERGE_LLM section=farm field=%s value=%r", k, v)

    # ── Fallback: if current_field is still missing after LLM, fill it from raw text ──
    text_stripped = text.strip()
    still_farmer = _all_missing(merged_farmer, FARMER_FIELDS)
    still_farm = _all_missing(merged_farm, FARM_FIELDS)
    still_missing_after_llm = still_farmer + still_farm
    cf_missing_in_own_section = (
        current_section == "farmer" and current_field in still_farmer
    ) or (
        current_section == "farm" and current_field in still_farm
    ) or (
        current_section is None and current_field in still_missing_after_llm
    )
    if _has_value(text_stripped) and current_field and cf_missing_in_own_section:
        target = current_field
        cleaned = text_stripped
        # Strip common conversational prefixes for cleaner values
        for prefix in ["my name is ", "i am ", "my father's name is ", "my farm is called ",
                       "my farm is at ", "i live at ", "my number is ", "my date of birth is ",
                       "i have completed ", "i work as a ", "i follow ", "i belong to ",
                       "i have ", "my aadhar is ", "my pan is "]:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        if target in _NUMERIC_FIELDS:
            cleaned = _clean_numeric(cleaned)
        sec = _resolve_section(target, still_farmer, still_farm, current_section)
        if sec == "farmer":
            merged_farmer[target] = cleaned
        else:
            merged_farm[target] = cleaned
        log.info("FALLBACK_CURRENT_FIELD section=%s field=%s value=%r raw=%r", sec, target, cleaned, text_stripped)
    elif not extracted_farmer and not extracted_farm:
        # Full LLM miss — assign to first missing field
        if _has_value(text_stripped):
            still = _all_missing(merged_farmer, FARMER_FIELDS) + _all_missing(merged_farm, FARM_FIELDS)
            target = current_field if current_field in still else (still or [None])[0]
            if target:
                cleaned = text_stripped
                for prefix in ["my name is ", "i am ", "my father's name is ", "my farm is called ",
                               "my farm is at ", "i live at ", "my number is ", "my date of birth is ",
                               "i have completed ", "i work as a ", "i follow ", "i belong to ",
                               "i have ", "my aadhar is ", "my pan is "]:
                    if cleaned.lower().startswith(prefix):
                        cleaned = cleaned[len(prefix):].strip()
                        break
                if target in _NUMERIC_FIELDS:
                    cleaned = _clean_numeric(cleaned)
                sec = _resolve_section(target, still_farmer, still_farm, current_section)
                if sec == "farmer":
                    merged_farmer[target] = cleaned
                else:
                    merged_farm[target] = cleaned
                log.info("FALLBACK_FIRST_MISSING section=%s field=%s value=%r", sec, target, cleaned)

    # ── Pre-clean certain fields before validation ──
    for section, fields in [("farmer", merged_farmer), ("farm", merged_farm)]:
        for fname, val in list(fields.items()):
            if not _has_value(val):
                continue
            cleaned = str(val)
            # Strip trailing punctuation
            cleaned = cleaned.rstrip(".,;!? ")
            # Strip location suffixes from city/district/state
            if fname in ("city", "farmCity", "district", "state", "farmState"):
                for suffix in ("city", "district", "state", "village", "town"):
                    if cleaned.lower().endswith(" " + suffix):
                        cleaned = cleaned[:-(len(suffix) + 1)]
            # farmCity: strip trailing district (e.g. "Delhi, Bikaner" -> "Delhi")
            if fname == "farmCity" and ", " in cleaned:
                cleaned = cleaned.split(", ")[0].strip()
            if cleaned != str(val):
                log.info("CLEAN_SUFFIX section=%s field=%s before=%r after=%r", section, fname, val, cleaned)
                fields[fname] = cleaned
                val = cleaned
            # Strip dashes/spaces from aadharNo
            if fname == "aadharNo":
                cleaned = _re.sub(r"[\s\-]", "", str(val))
                if cleaned != str(val):
                    log.info("CLEAN_AADHAR field=%s before=%r after=%r", fname, val, cleaned)
                    fields[fname] = cleaned
            # Strip dashes/spaces from phone/pincode too
            if fname in ("phone", "farmPhone", "alternateMobile", "pincode"):
                cleaned = _re.sub(r"[\s\-]", "", str(val))
                if cleaned != str(val):
                    log.info("CLEAN_PHONE_PIN field=%s before=%r after=%r", fname, val, cleaned)
                    fields[fname] = cleaned
            # Clean numeric fields: extract digits
            if fname in _NUMERIC_FIELDS:
                raw_s = str(val).strip()
                cleaned = _clean_numeric(raw_s)
                if cleaned != raw_s:
                    log.info("CLEAN_NUMERIC field=%s before=%r after=%r", fname, raw_s, cleaned)
                    fields[fname] = cleaned

    # ── Auto-infer hasPanCard / hasGovernmentId from related fields ──
    if _has_value(merged_farmer.get("panNo")) and not _has_value(merged_farmer.get("hasPanCard")):
        merged_farmer["hasPanCard"] = "yes"
        log.info("AUTO_INFER hasPanCard=yes from panNo")
    if _has_value(merged_farmer.get("aadharNo")) and not _has_value(merged_farmer.get("hasGovernmentId")):
        merged_farmer["hasGovernmentId"] = "yes"
        log.info("AUTO_INFER hasGovernmentId=yes from aadharNo")

    # ── Post-process: fix misplaced pincode ──
    if not _has_value(merged_farm.get("farmPincode")) and _has_value(merged_farmer.get("pincode")):
        # If the farm section has any farm-specific fields but farmPincode is missing,
        # and the farmer section has a pincode, it's likely misplaced
        farm_indicators = ["farmName", "farmPhone", "farmCity", "farmState"]
        if any(_has_value(merged_farm.get(f)) for f in farm_indicators):
            # Check if farmer has few personal identifiers filled (no farmer context in text)
            farmer_indicators = ["fatherOrSpouseName", "gender", "dob", "address_1"]
            farmer_filled = sum(1 for f in farmer_indicators if _has_value(filled_farmer.get(f)))
            if farmer_filled <= 1:
                val = merged_farmer.pop("pincode")
                merged_farm["farmPincode"] = val
                log.info("RECOVER_FARM_PINCODE moved=%s from farmer.pincode to farm.farmPincode", val)
    # Reverse: farmer pincode ended up as farmPincode
    if not _has_value(merged_farmer.get("pincode")) and _has_value(merged_farm.get("farmPincode")):
        farmer_indicators = ["name", "fatherOrSpouseName", "gender", "dob", "address_1"]
        farmer_filled = sum(1 for f in farmer_indicators if _has_value(filled_farmer.get(f)))
        if farmer_filled >= 3 and not any(_has_value(merged_farm.get(f)) for f in ["farmName", "farmCity", "farmState"]):
            val = merged_farm.pop("farmPincode")
            merged_farmer["pincode"] = val
            log.info("RECOVER_FARMER_PINCODE moved=%s from farm.farmPincode to farmer.pincode", val)

    # ── Deterministic validation: clear invalid values so we re-ask ──
    merged_farmer, merged_farm, error_fields = _validate_merged(merged_farmer, merged_farm)

    still_missing_farmer = _all_missing(merged_farmer, FARMER_FIELDS)
    still_missing_farm = _all_missing(merged_farm, FARM_FIELDS)
    still_missing = still_missing_farmer + still_missing_farm

    log.info("EXTRACT_RESULT extracted_farmer=%d extracted_farm=%d errors=%d still_missing=%d elapsed=%.2fs",
             len([k for k, v in merged_farmer.items() if _has_value(v)]),
             len([k for k, v in merged_farm.items() if _has_value(v)]),
             len(error_fields), len(still_missing), time.time() - t0)

    # ── Compute confidence ──
    filled_now = len([k for k, v in merged_farmer.items() if _has_value(v)]) + len([k for k, v in merged_farm.items() if _has_value(v)])
    filled_before = len([k for k, v in filled_farmer.items() if _has_value(v)]) + len([k for k, v in filled_farm.items() if _has_value(v)])
    total_new = filled_now - filled_before
    prob_errors = len(error_fields)
    is_complete = not still_missing
    if is_complete and not prob_errors:
        confidence = 1.0
    elif prob_errors > 0:
        confidence = max(0.1, 1.0 - (prob_errors * 0.3))
    elif total_new == 0:
        confidence = 0.8
    else:
        confidence = min(1.0, 0.6 + (total_new * 0.08))
    confidence = max(0.0, min(1.0, confidence))

    confirm_fields = []
    if confidence < 0.8:
        if _has_value(merged_farmer.get("pincode")): confirm_fields.append("pincode")
        if _has_value(merged_farmer.get("city")): confirm_fields.append("city")
        if _has_value(merged_farmer.get("state")): confirm_fields.append("state")
        if _has_value(merged_farmer.get("name")): confirm_fields.append("name")
        if _has_value(merged_farmer.get("phone")): confirm_fields.append("phone")
        if _has_value(merged_farm.get("farmPincode")): confirm_fields.append("farmPincode")
        if _has_value(merged_farm.get("farmCity")): confirm_fields.append("farmCity")
        if _has_value(merged_farm.get("farmName")): confirm_fields.append("farmName")
        confirm_fields = confirm_fields[:2]

    if not still_missing:
        return {
            "farmer": merged_farmer,
            "farm": merged_farm,
            "missing_fields": [],
            "follow_up_question": None,
            "complete": True,
            "confidence": confidence,
            "confirm_fields": confirm_fields,
        }

    if error_fields:
        next_f = error_fields[0]
    elif llm_fq:
        llm_field = _infer_field_from_question(llm_fq, still_missing)
        next_f = llm_field if llm_field else still_missing[0]
    else:
        next_f = still_missing[0]

    question = _FIELD_QUESTIONS.get(next_f, f"Please tell me: {next_f}")

    return {
        "farmer": merged_farmer,
        "farm": merged_farm,
        "missing_fields": still_missing,
        "follow_up_question": question,
        "complete": False,
        "confidence": confidence,
        "confirm_fields": confirm_fields,
    }


def _infer_field_from_question(question: str, missing_fields: list[str]) -> str | None:
    """Match an LLM-generated follow-up question back to one of the missing fields."""
    q = question.lower()
    # Direct field name match in question
    for f in missing_fields:
        if f.lower().replace("_", "") in q.replace(" ", "").replace("_", ""):
            return f
    # Keyword-based mapping
    keyword_map = {
        "aadhar": "aadharNo", "adhar": "aadharNo", "aadhaar": "aadharNo",
        "father": "fatherOrSpouseName", "spouse": "fatherOrSpouseName",
        "husband": "fatherOrSpouseName", "gender": "gender", "sex": "gender",
        "phone": "phone", "mobile": "phone", "contact": "phone",
        "email": "email", "address": "address_1",
        "city": "city", "state": "state", "pincode": "pincode", "pin": "pincode",
        "education": "education", "occupation": "occupation",
        "experience": "farmingExperience", "land": "landHolding",
        "name": "name", "pancard": "panNo", "pan": "panNo",
        "religion": "religion", "caste": "caste",
        "farm": "farmName", "animal": "totalAnimalCapacity",
    }
    for kw, field in keyword_map.items():
        if kw in q:
            if field in missing_fields:
                return field
    return None


_QUALITY_SYSTEM = """You are a QA reviewer for a farmer onboarding system.
Review the collected farmer and farm data for quality issues.
Return JSON with issues (if any) or empty array."""


def quality_check(
    farmer: dict,
    farm: dict,
    language: str = "en",
    adapter: Optional[TextAdapter] = None,
) -> dict[str, Any]:
    """Review final data for quality issues. Returns dict with 'issues' and 'passed'."""
    merged = {}
    merged.update(farmer)
    merged.update(farm)

    filled = {k: v for k, v in merged.items() if v not in (None, "", 0, "0")}
    if not filled:
        return {"passed": True, "issues": [], "summary": "No data collected yet"}

    llm = adapter or _adapter()
    prompt = f"""Review this farmer onboarding data for quality issues:

{_json.dumps(filled, ensure_ascii=False, indent=2)}

Check for these issues:
1. **Name mismatch**: farmer name vs farm name — are they suspiciously identical?
2. **Phone overlap**: farmer phone same as farm phone?
3. **Aadhar validity**: is aadharNo 12 digits?
4. **PIN code**: is pincode 6 digits?
5. **Phone format**: are phone numbers 10 digits?
6. **Date of birth**: is dob a valid date (YYYY-MM-DD)?
7. **Empty critical fields**: are name, phone, aadharNo, city, state missing?
8. **Suspicious values**: does any field contain conversational noise (e.g. "my name is", "i am", etc.)?

Return JSON:
- issues: array of {{"field": "...", "severity": "error"|"warning", "message": "..."}}
- passed: true if no errors (warnings OK)
- summary: one-line overall assessment"""

    try:
        raw = llm.complete(messages=[{"role": "user", "content": prompt}], system=_QUALITY_SYSTEM)
        parsed = _json.loads(raw.strip())
    except Exception:
        parsed = {}

    issues = parsed.get("issues", [])
    passed = parsed.get("passed", len(issues) == 0)
    summary = parsed.get("summary", f"{len(issues)} issue(s) found")

    log.info("QUALITY_CHECK filled=%d issues=%d passed=%s summary=%s", len(filled), len(issues), passed, summary)
    for iss in issues:
        log.warning("QUALITY_ISSUE field=%s severity=%s message=%s", iss.get("field"), iss.get("severity"), iss.get("message"))

    return {
        "passed": passed,
        "issues": issues,
        "summary": summary,
    }
