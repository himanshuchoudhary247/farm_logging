import os
import json
import time
import logging
from enum import Enum
from pathlib import Path
import boto3
from botocore.config import Config
from typing import Optional, Dict, Any

_log = logging.getLogger("bedrock")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_BEDROCK_CONFIG = Config(
    max_pool_connections=10,
    connect_timeout=2,
    read_timeout=30,
    retries={"max_attempts": 2, "mode": "adaptive"},
)

_bedrock_client = None
_bedrock_model = None
_llm_config_cache: Optional[dict] = None


class TaskTier(str, Enum):
    EXTRACTION = "extraction"
    EXTRACTION_ALT = "extraction_alt"
    GENERATION = "generation"
    LONG_FORM = "long_form"


def _load_llm_config() -> dict:
    """Load config/llm.yaml once. Env LLM_CONFIG_PATH overrides."""
    global _llm_config_cache
    if _llm_config_cache is not None:
        return _llm_config_cache
    try:
        import yaml
        path = os.getenv("LLM_CONFIG_PATH") or str(Path(__file__).resolve().parents[2] / "config" / "llm.yaml")
        with open(path, encoding="utf-8") as f:
            _llm_config_cache = yaml.safe_load(f) or {}
    except Exception as exc:
        _log.warning("llm config load failed: %s", exc)
        _llm_config_cache = {}
    return _llm_config_cache


def model_for_task(task: TaskTier) -> Dict[str, Any]:
    """Resolve (id, max_tokens, temperature) for a task tier.

    Precedence: BEDROCK_MODEL_<TIER> env > config/llm.yaml models.<tier> >
    legacy BEDROCK_MODEL_ID env > mistral-large fallback.
    """
    tier = task.value.upper()
    cfg = (_load_llm_config().get("models") or {}).get(task.value) or {}
    model_id = (
        os.getenv(f"BEDROCK_MODEL_{tier}")
        or cfg.get("id")
        or os.getenv("BEDROCK_MODEL_ID")
        or "mistral.mistral-large-3-675b-instruct"
    )
    max_tokens = int(os.getenv(f"BEDROCK_MAX_TOKENS_{tier}", cfg.get("max_tokens", 256)))
    temperature = float(os.getenv(f"BEDROCK_TEMP_{tier}", cfg.get("temperature", 0)))
    return {"id": model_id, "max_tokens": max_tokens, "temperature": temperature}


def _get_client():
    global _bedrock_client, _bedrock_model
    if _bedrock_client is None:
        _bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            config=_BEDROCK_CONFIG,
        )
        _bedrock_model = os.getenv("BEDROCK_MODEL_ID") or (
            (_load_llm_config().get("models") or {}).get("extraction", {}).get("id")
            or "mistral.mistral-large-3-675b-instruct"
        )
    return _bedrock_client, _bedrock_model


class BedrockTextAdapter:
    """Bedrock Converse client with per-task model resolution.

    Pass task=TaskTier.EXTRACTION|GENERATION|LONG_FORM to pick model + limits
    from config/llm.yaml. Omit task for legacy default behavior.
    """

    def __init__(self, task: Optional[TaskTier] = None):
        self.client, default_model = _get_client()
        if task is not None:
            spec = model_for_task(task)
            self.model_id = spec["id"]
            self.max_tokens = spec["max_tokens"]
            self.temperature = spec["temperature"]
            self.task = task.value
        else:
            self.model_id = default_model
            self.max_tokens = 256
            self.temperature = 0.0
            self.task = "legacy"

    def complete(self, messages, system=None):
        # Always route through the unified Converse API — Anthropic, Nova,
        # DeepSeek, OpenAI (India Geo), Cohere, Mistral all support it and
        # return the same response shape (output.message.content[].text).
        req = {
            "modelId": self.model_id,
            "messages": [
                {"role": m.get("role", "user"), "content": [{"text": m["content"]}]}
                for m in messages
            ],
            "inferenceConfig": {
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            },
        }
        if system:
            req["system"] = [{"text": system}]

        t0 = time.time()
        resp = self.client.converse(**req)
        content = resp.get("output", {}).get("message", {}).get("content", [])
        result = content[0].get("text", "") if content and isinstance(content, list) else ""
        usage = resp.get("usage") or {}
        _log.info(
            "LATENCY bedrock task=%s model=%s ms=%.0f in_tok=%s out_tok=%s",
            self.task, self.model_id, (time.time() - t0) * 1000,
            usage.get("inputTokens"), usage.get("outputTokens"),
        )
        return result

    def converse_with_tool(self, messages, tool_spec, system=None, tool_choice_name=None):
        """Bedrock Converse with a forced tool call. Returns the parsed tool
        input dict directly, so callers never have to parse JSON out of text.

        Verified working on DeepSeek V3, Nova Micro, Ministral 14B 2026-09-13.
        tool_choice_name forces the named tool via toolChoice.tool; omit to
        allow the model to choose any provided tool via toolChoice.any.
        """
        req = {
            "modelId": self.model_id,
            "messages": [
                {"role": m.get("role", "user"), "content": [{"text": m["content"]}]}
                for m in messages
            ],
            "inferenceConfig": {
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            },
            "toolConfig": {
                "tools": [{"toolSpec": tool_spec}],
                "toolChoice": (
                    {"tool": {"name": tool_choice_name}} if tool_choice_name
                    else {"any": {}}
                ),
            },
        }
        if system:
            req["system"] = [{"text": system}]

        t0 = time.time()
        resp = self.client.converse(**req)
        content = resp.get("output", {}).get("message", {}).get("content", []) or []
        tool_use = next((c["toolUse"] for c in content if "toolUse" in c), None)
        usage = resp.get("usage") or {}
        _log.info(
            "LATENCY bedrock task=%s model=%s ms=%.0f in_tok=%s out_tok=%s stop=%s tool=%s",
            self.task, self.model_id, (time.time() - t0) * 1000,
            usage.get("inputTokens"), usage.get("outputTokens"),
            resp.get("stopReason"), tool_use["name"] if tool_use else None,
        )
        # Also return any text the model emitted alongside the tool call
        # (some models put the follow-up question there).
        text = next((c["text"] for c in content if "text" in c), None)
        return {
            "tool_name": tool_use["name"] if tool_use else None,
            "tool_input": tool_use.get("input") if tool_use else {},
            "text": text,
            "stop_reason": resp.get("stopReason"),
        }


# ---- Voice Extraction Wrapper ----
# This is the ONLY extraction path for voice turns — orchestrator.py has no
# regex/rule-based fallback parser. Since 2026-09-13 (commit adding tool-use)
# extraction runs through a Bedrock Converse tool call rather than
# JSON-in-text, so the schema lives in _EXTRACTION_TOOL_SPEC below (typed,
# enum-validated) instead of a system-prompt string.

def build_prompt(text: str, context: Optional[Dict[str, Any]] = None) -> str:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    session_intent = None
    session_entities = {}
    pending_questions = []
    if context:
        session_intent = context.get("intent")
        session_entities = context.get("entities") or {}
        pending_questions = context.get("pending_questions") or []

    # FarmHerd is India-only (ap-south-1). UTC is 5:30h behind IST, so
    # midnight-5:30am IST calls would get "today"/"tomorrow" computed one
    # calendar day early if this used UTC — confirmed live: at 2026-09-11
    # 03:44 IST, UTC clock still read 2026-09-10.
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    tomorrow = (today + timedelta(days=1)).isoformat()

    return f"""User: "{text}"
Context: intent={json.dumps(session_intent)} entities={json.dumps(session_entities, ensure_ascii=False)} pending={json.dumps(pending_questions, ensure_ascii=False)}
Today: {today.isoformat()} Tomorrow: {tomorrow}
Extract intent+entities. Return ONLY JSON."""


# Bedrock Converse tool spec for extraction. The model calls this tool with
# already-typed arguments — no JSON-in-text to parse, no _safe_json_parse
# strategies, no _coerce_confidence/_coerce_list shims. Verified working on
# DeepSeek V3, Nova Micro, and Ministral 14B via converse toolConfig.
_EXTRACTION_TOOL_SPEC = {
    "name": "record_farmer_intent",
    "description": (
        "Record everything the farmer stated in this turn. Populate ONLY the "
        "fields the farmer actually stated (or, for short follow-up answers, "
        "the field the pending question was asking about). Never invent "
        "values. issue/symptoms should be short English phrases even when "
        "the farmer spoke another language; animal_name and animal_tag stay "
        "in the farmer's original script."
    ),
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": ["WEATHER_ALERT", "FETCH_ANIMAL_DETAILS", "CREATE_ANIMAL",
                             "UPDATE_ANIMAL", "LOG_HEALTH", "CREATE_APPOINTMENT"],
                    "description": (
                        "CREATE_ANIMAL / UPDATE_ANIMAL are ONLY for registering or editing "
                        "an animal's profile record (name, breed, age). Any request for a "
                        "vet, treatment, or vaccine is CREATE_APPOINTMENT even if the word "
                        "'appointment' is never spoken."
                    ),
                },
                "animal_id": {
                    "type": "string",
                    "description": (
                        "Internal system record id the farmer read out, e.g. 'a-f-001-2'. "
                        "Use this ONLY when the value looks like an internal id format "
                        "(letters+numbers+dashes). For a bare number or a physical ear-tag "
                        "number, use animal_tag instead, not this field."
                    ),
                },
                "animal_name": {"type": "string"},
                "animal_tag": {
                    "type": "string",
                    "description": (
                        "The physical ear-tag number the farmer reads off the animal "
                        "(digits, e.g. '1234'). Use this whenever the farmer says a word "
                        "meaning 'tag' or 'tag number' followed by digits, in any language "
                        "(e.g. Tamil 'டேக் எண் 1234', Hindi 'टैग नंबर 1234')."
                    ),
                },
                "animal_record_mode": {"type": "string", "enum": ["new", "existing"]},
                "species": {
                    "type": "string",
                    "enum": ["goat", "sheep", "cow", "buffalo", "chicken"],
                    "description": (
                        "Only set this when the farmer's words name an animal type. Native-"
                        "script vocabulary for each value, so a bare single word in any of "
                        "these languages still maps correctly: "
                        "cow: गाय (hi), ఆవు (te), பசு (ta), ಹಸು (kn), പശു (ml). "
                        "goat: बकरी (hi), మేక (te), ஆடு (ta), ಆಡು (kn), ആട് (ml). "
                        "sheep: भेड़ (hi), గొర్రె (te), செம்மறியாடு (ta), ಕುರಿ (kn), "
                        "ചെമ്മരിയാട് (ml). "
                        "buffalo: भैंस (hi), గేదె (te), எருமை (ta), ಎಮ್ಮೆ (kn), എരുമ (ml). "
                        "chicken: मुर्गी (hi), కోడి (te), கோழி (ta), ಕೋಳಿ (kn), കോഴി (ml). "
                        "Do NOT guess a species when no animal word is present at all — a "
                        "phrase like 'call a vet' or 'need an appointment' with no animal "
                        "named must leave this field empty, not default to any species."
                    ),
                },
                "sex": {"type": "string", "enum": ["male", "female"]},
                "breed": {"type": "string"},
                "age_years": {"type": "number"},
                "feeding_details": {"type": "string"},
                "issue": {"type": "string", "description": "Short English phrase, e.g. 'fever'"},
                "symptoms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Array of short English phrases: 'fever', 'not eating', 'wound', "
                        "'swelling', 'limping', 'lethargy', 'not drinking', etc."
                    ),
                },
                "duration": {"type": "string"},
                "severity": {"type": "string", "enum": ["mild", "moderate", "severe"]},
                "current_medication": {"type": "string", "description": "'none' if farmer says no medicine"},
                "temperature_c": {"type": "number", "description": "Convert Fahrenheit to Celsius if needed"},
                "date": {
                    "type": "string",
                    "description": (
                        "'today', 'tomorrow', 'yesterday', or an ISO date YYYY-MM-DD"
                    ),
                },
                "time": {
                    "type": "string",
                    "description": (
                        "24-hour HH:MM. If farmer says only a period of day with no exact "
                        "hour, use morning=09:00, afternoon=14:00, evening=18:00, night=20:00."
                    ),
                },
                "weather_location": {"type": "string", "description": "Pincode or place name"},
                "forecast_days": {"type": "integer", "minimum": 1, "maximum": 7},
                "country_code": {"type": "string"},
                "unavailable_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Field names the farmer explicitly said are not available / "
                        "unknown (e.g. 'severity' if the farmer said 'severity not available')."
                    ),
                },
                "follow_up_question": {
                    "type": "string",
                    "description": (
                        "The single most important missing piece of information for the "
                        "detected intent, phrased in the SAME language as the user's input. "
                        "Omit entirely if no follow-up is needed."
                    ),
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
        }
    },
}

_TOOL_SYSTEM_PROMPT = (
    "You are the sole extraction engine for a livestock voice assistant. Read "
    "farmer input in any language and script (Hindi/Tamil/Telugu/Kannada/"
    "Malayalam/English, or mixed) and in any word order. There is no fallback "
    "text parser after you.\n"
    "\n"
    "ALWAYS call the record_farmer_intent tool exactly once. Populate ONLY "
    "the fields the farmer stated. For short follow-up answers ('yes', "
    "'my cow', '10 am', 'ನಾಳೆ'), the pending question in the Context block "
    "tells you which field the reply is answering — populate that field even "
    "with zero surrounding context. If the current message states a new "
    "value for a field that already has a value in the context, the new "
    "message wins.\n"
    "\n"
    "Examples:\n"
    "1) User: \"ನನ್ನ ಹಸು\" | pending_questions: [\"animal name/tag\"] "
    "-> tool call: {species: 'cow', animal_name: 'ಹಸು'}\n"
    "2) User: \"ఆవుకు జ్వరం\" (no prior context) -> "
    "{intent: 'LOG_HEALTH', species: 'cow', issue: 'fever', symptoms: ['fever']}\n"
    "3) User: \"கால்நடை மருத்துவர் தேவை\" (need a vet, no animal named) -> "
    "{intent: 'CREATE_APPOINTMENT'} — species is OMITTED, never CREATE_ANIMAL\n"
    "4) User: \"बकरी को टीका चाहिए\" (goat needs vaccine) -> "
    "{intent: 'CREATE_APPOINTMENT', species: 'goat'}\n"
    "5) User: \"10 am\" | pending_questions: [\"appointment time\"] -> "
    "{time: '10:00'}\n"
    "6) User: \"ആട്\" | context species already set to 'cow' from an earlier "
    "guess -> {species: 'goat'} — a bare word naming an animal ALWAYS "
    "overrides a previously-guessed species, even a single word with no "
    "other context.\n"
    "\n"
    "STRICT NO-GUESS RULE: a field with no corresponding word anywhere in "
    "the farmer's utterance must be left out of the tool call entirely — "
    "including on the very first turn of a conversation. 'Call a vet' or "
    "'I need an appointment' names no animal, so species/animal_name/"
    "animal_tag must all be omitted; wait for a later turn to name the "
    "animal rather than guessing one now. An omitted field you fill in "
    "later is normal and expected; a wrongly-guessed field is a bug you "
    "must not create.\n"
    "\n"
    "COMPOUND-WORD CAVEAT: several Indic languages build job-title/compound "
    "words out of an animal-word root plus a suffix — e.g. Malayalam "
    "'പശുവൈദ്യൻ' (veterinarian) is built from 'പശു' (cow) + 'വൈദ്യൻ' "
    "(physician), but the whole word means 'veterinarian', NOT 'cow'. A "
    "species root appearing only as part of a longer compound word (a job "
    "title, a place name, etc.) is NOT a species mention — only a standalone "
    "species word, or the species word as a separate token in the sentence, "
    "counts as the farmer naming that animal.\n"
    "\n"
    "Never invent values. Never populate fields the farmer did not state."
)


def call_bedrock(text: str, context: Optional[Dict[str, Any]] = None):
    """Extract intent + entities from a farmer voice turn via a Bedrock
    Converse tool call. Returns the same shape prior JSON-parsing versions
    of this function returned, so orchestrator + tests stay unchanged."""
    adapter = BedrockTextAdapter(task=TaskTier.EXTRACTION)

    messages = [
        {"role": "user", "content": build_prompt(text, context=context)}
    ]

    result = adapter.converse_with_tool(
        messages=messages,
        tool_spec=_EXTRACTION_TOOL_SPEC,
        system=_TOOL_SYSTEM_PROMPT,
        tool_choice_name="record_farmer_intent",
    )
    tool_input = result.get("tool_input") or {}

    # Split the tool args back into the {intent, entities, ...} shape the
    # orchestrator already consumes.
    intent = tool_input.pop("intent", None)
    unavailable_fields = tool_input.pop("unavailable_fields", None) or []
    follow_up_question = tool_input.pop("follow_up_question", None)
    confidence = tool_input.pop("confidence", None)
    # Whatever's left in tool_input is the entities dict — every key was
    # declared in the tool schema, so no coercion or key-check needed.
    entities = tool_input

    return {
        "intent": intent,
        "entities": entities,
        "unavailable_fields": list(unavailable_fields) if isinstance(unavailable_fields, list) else [],
        "missing_fields": [],
        "follow_up_questions": [follow_up_question] if follow_up_question else [],
        "confidence": float(confidence) if isinstance(confidence, (int, float)) else 0.0,
        "_raw": result.get("text"),
    }


FARM_FIELDS = [
    "name", "email", "phone", "alternate_phone", "address", "city",
    "district", "pincode", "state", "country", "total_animal_capacity",
    "current_animal_count", "sheep_count", "goat_count", "notes",
]

_FIELD_QUESTIONS = {
    "name": "What's the name of your farm?",
    "email": "What's your email address?",
    "phone": "What's your phone number?",
    "alternate_phone": "Do you have an alternate phone number?",
    "address": "What's your farm's full address?",
    "city": "Which city is your farm located in?",
    "district": "Which district is your farm in?",
    "pincode": "What's the pincode for your farm?",
    "state": "Which state is your farm located in?",
    "country": "What country is your farm in?",
    "total_animal_capacity": "How many animals can your farm hold in total?",
    "current_animal_count": "How many animals do you currently have?",
    "sheep_count": "How many sheep do you have?",
    "goat_count": "How many goats do you have?",
    "notes": "Any special notes about your farm?",
}


def _has_value(v) -> bool:
    return v not in (None, "", 0, "0", 0.0)


def _next_missing_field(data: dict):
    for f in FARM_FIELDS:
        if not _has_value(data.get(f)):
            return f
    return None


_LANG_INSTRUCTIONS = {
    "hi": "Ask the next question in Hindi (हिंदी). Use the Hindi script (Devanagari).",
    "kn": "Ask the next question in Kannada (ಕನ್ನಡ). Use the Kannada script.",
    "te": "Ask the next question in Telugu (తెలుగు). Use the Telugu script.",
    "en": "Ask the next question in English.",
    "mix": "Ask the next question in Hinglish (mix of Hindi and English, using Latin script).",
    "mix-hi": "Ask the next question in Hinglish (mix of Hindi and English, using Latin script).",
    "mix-kn": "Ask the next question mixing Kannada and English (using Kannada + Latin script).",
    "mix-te": "Ask the next question mixing Telugu and English (using Telugu + Latin script).",
}


def extract_farm_onboarding(text: str, existing_data: Optional[dict] = None, language: str = "en") -> dict:
    import json as _json
    adapter = BedrockTextAdapter(task=TaskTier.EXTRACTION)
    existing = existing_data or {}
    filled = {k: v for k, v in existing.items() if _has_value(v)}
    missing = [f for f in FARM_FIELDS if not _has_value(filled.get(f))]

    lang_code = language or "en"
    lang_instruction = _LANG_INSTRUCTIONS.get(
        lang_code, _LANG_INSTRUCTIONS.get(lang_code.replace("mix-", "mix"), "Ask the next question in English.")
    )

    prompt = f"""You are an onboarding assistant for a livestock farm management system.

The farmer said: "{text}"

Already collected (store in English/numeric only): {_json.dumps(filled, ensure_ascii=False)}
Still needed: {_json.dumps(missing, ensure_ascii=False)}

Extract farm details from the farmer's message. Return ONLY a JSON object:
- extracted_fields: object with any new fields found (keys: name, email, phone, alternate_phone, address, city, district, pincode, state, country, total_animal_capacity, current_animal_count, sheep_count, goat_count, notes)
- follow_up_question: a friendly question to ask next for the most important missing field (or null if all done)

Rules:
- Store ALL field values in English or numeric only (e.g. phone numbers, counts as numbers, pincode as number)
- total_animal_capacity, current_animal_count, sheep_count, goat_count must be numbers
- pincode must be a number
- Extract ONLY what the farmer explicitly says. Do not guess.
- {lang_instruction}
- Ask ONE question at a time. Keep it conversational and friendly.
- Return ONLY valid JSON, no markdown, no backticks."""

    try:
        raw = adapter.complete(
            messages=[{"role": "user", "content": prompt}],
            system="You are a farm onboarding assistant. Extract fields in English/numeric. Ask follow-ups in user's language. Return only JSON."
        )
        parsed = _json.loads(raw.strip())
        extracted = parsed.get("extracted_fields", {})
        llm_fq = parsed.get("follow_up_question")
    except Exception:
        extracted = {}
        llm_fq = None

    merged = dict(filled)
    for k, v in extracted.items():
        if _has_value(v):
            merged[k] = v

    next_field = _next_missing_field(merged)

    if next_field is None:
        return {
            "data": merged,
            "missing_fields": [],
            "follow_up_question": None,
            "complete": True,
        }

    question = llm_fq if llm_fq else _FIELD_QUESTIONS.get(next_field, f"Please provide: {next_field}")
    return {
        "data": merged,
        "missing_fields": [f for f in FARM_FIELDS if not _has_value(merged.get(f))],
        "follow_up_question": question,
        "complete": False,
    }


def generate_seasonal_advisory(
    district: str,
    location: str,
    forecast: dict,
    historical: dict,
) -> str:
    import json as _json
    adapter = BedrockTextAdapter(task=TaskTier.LONG_FORM)

    daily = forecast.get("daily") or {}
    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    rain = daily.get("precipitation_sum") or []
    wind = daily.get("wind_speed_10m_max") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []

    forecast_lines = []
    for i, d in enumerate(dates):
        forecast_lines.append(
            f"  {d}: high {tmax[i] if i < len(tmax) else '?'}C, low {tmin[i] if i < len(tmin) else '?'}C, "
            f"rain {rain[i] if i < len(rain) else 0}mm, wind {wind[i] if i < len(wind) else 0}km/h"
        )

    forecast_text = "\n".join(forecast_lines) if forecast_lines else "No forecast data"

    hist_years = _json.dumps(historical.get("years") or [], indent=2, default=str)
    hist_summary = _json.dumps(historical.get("summary") or {}, indent=2, default=str)

    prompt = f"""You are an expert veterinary epidemiologist assessing weather risk for livestock.

LOCATION: {district} ({location})

CURRENT WEEK FORECAST:
{forecast_text}

HISTORICAL DATA (same week, past 5 years):
{hist_summary}

Year-by-year:
{hist_years}

Write an SMS-style weather alert and advisory for sheep and goat farmers in {district}.

Requirements:
1. Compare this week's forecast against the 5-year historical average.
2. If weather is near normal, say "No major deviation from historical pattern. Routine management advised."
3. If unusual (heat wave, heavy rain, cold spell, strong wind), give specific precautions.
4. SEPARATE advisory for:
   - Nomadic farmers (lambs vs adults)
   - Organized/settled farmers (lambs vs adults)
5. Reference ICAR or Department of Animal Husbandry guidelines where relevant.
6. Keep SMS-style: short sentences, bullet points with * prefix, max ~600 characters.
7. Write in clear English suitable for translation.
8. End with: "-- {district} Veterinary Warning"."""
    try:
        out = adapter.complete(
            messages=[{"role": "user", "content": prompt}],
            system="You are an expert veterinary epidemiologist. Write SMS-style livestock weather advisories."
        )
        return (out or "").strip() or "Advisory generation failed."
    except Exception:
        return "Advisory generation failed. Please try again."


def get_weather_recommendation(weather_data: dict, location_display: str = "") -> str:
    import json as _json
    adapter = BedrockTextAdapter(task=TaskTier.GENERATION)
    forecast = _json.dumps(weather_data.get("forecast_days") or [], indent=2, default=str)
    alerts = _json.dumps(weather_data.get("alerts") or [], indent=2, default=str)
    risk = weather_data.get("risk_level", "low")
    summary = weather_data.get("summary", "")

    loc = location_display or weather_data.get("resolved_location", {}).get("display_name", "your area")

    prompt = f"""You are a practical livestock farming weather advisor for {loc}.

Weather Summary: {summary}
Risk Level: {risk}

Forecast (next few days):
{forecast}

Alerts:
{alerts}

Give the farmer short, actionable recommendations for protecting their animals and farm.

- If the weather is normal (low risk, no extreme conditions), just say: "All good, no need to worry about the weather."
- If there are any concerns, mention practical steps (e.g. provide shade, move animals to shelter, ensure ventilation, check water supply, secure loose objects).
- Keep it concise, under 5 sentences.
- Use simple language. Do NOT use markdown formatting."""
    try:
        out = adapter.complete(
            messages=[{"role": "user", "content": prompt}],
            system="You are a helpful livestock farming weather advisor. Keep recommendations practical and concise. If weather is normal, reassure the farmer."
        )
        return (out or "").strip() or "All good, no need to worry about the weather."
    except Exception:
        return "All good, no need to worry about the weather."


def translate_to_english(text: str) -> str:
    src = (text or "").strip()
    if not src:
        return src

    adapter = BedrockTextAdapter(task=TaskTier.EXTRACTION)
    system = (
        "You are a translation assistant for a livestock operations system. "
        "Translate user message to concise English. Preserve names, IDs, time, date, medicine names, and quantities exactly. "
        "Return ONLY translated text."
    )
    try:
        out = adapter.complete(messages=[{"role": "user", "content": src}], system=system)
        return (out or "").strip() or src
    except Exception:
        return src
