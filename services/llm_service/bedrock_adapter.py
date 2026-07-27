import os
import json
import boto3
from typing import Optional, Dict, Any


class BedrockTextAdapter:
    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")

    def complete(self, messages, system=None):
        prompt = ""
        if system:
            prompt += f"System: {system}\n"
        for m in messages:
            prompt += f"{m['role'].capitalize()}: {m['content']}\n"
        prompt += "Assistant:"

        # Anthropic models via invoke_model
        if self.model_id.startswith("anthropic."):
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
            }
            resp = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
            )
            out = json.loads(resp["body"].read())
            return out.get("content", [{"text": ""}])[0]["text"]

        # Non-anthropic models via Converse API
        req = {
            "modelId": self.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            "inferenceConfig": {
                "maxTokens": 512,
                "temperature": 0,
            },
        }
        if system:
            req["system"] = [{"text": system}]

        resp = self.client.converse(**req)
        content = resp.get("output", {}).get("message", {}).get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return ""


# ---- Voice Extraction Wrapper ----
_SYSTEM_PROMPT = (
    "You are an information extraction system for a livestock app.\n"
    "Return ONLY valid JSON. No backticks. No markdown. No preamble. No trailing text.\n"
    "The response MUST be a single JSON object with EXACT keys: intent, entities, missing_fields, follow_up_questions, confidence.\n"
    "- intent: one of [WEATHER_ALERT, FETCH_ANIMAL_DETAILS, CREATE_ANIMAL, UPDATE_ANIMAL, LOG_HEALTH, CREATE_APPOINTMENT] or null\n"
    "- entities: a JSON object (can be empty)\n"
    "- missing_fields: array of strings\n"
    "- follow_up_questions: array of strings\n"
    "- confidence: number between 0 and 1\n"
    "If information is missing, leave fields null or empty; do not invent values."
)

def build_prompt(text: str, context: Optional[Dict[str, Any]] = None) -> str:
    # Conversational extraction with missing fields + follow-ups
    session_intent = None
    session_entities = {}
    pending_questions = []
    if context:
        session_intent = context.get("intent")
        session_entities = context.get("entities") or {}
        pending_questions = context.get("pending_questions") or []

    return f"""
You are an AI assistant for a livestock management system.

User said:
"{text}"

Conversation context:
- current_intent: {json.dumps(session_intent)}
- known_entities: {json.dumps(session_entities, ensure_ascii=False)}
- pending_questions: {json.dumps(pending_questions, ensure_ascii=False)}

Your job:
1. Identify intent
2. Extract entities
3. Identify missing required fields
4. Suggest follow-up questions

Intents:
- WEATHER_ALERT
- FETCH_ANIMAL_DETAILS
- CREATE_ANIMAL
- UPDATE_ANIMAL
- LOG_HEALTH
- CREATE_APPOINTMENT
- null

Entity schema hints:
- Animal: animal_id, animal_name, species, sex, breed, age_years, feeding_details, animal_record_mode(new|existing)
- Health: issue, symptoms(list), duration, severity, temperature_c, current_medication
- Appointment: date, time, animal_id/animal_name, issue, duration, severity, current_medication, temperature_c
- Weather: weather_location(pin or place), country_code, forecast_days

Return ONLY valid JSON (no extra text):
{{
  "intent": "...",
  "entities": {{}},
  "missing_fields": [],
  "follow_up_questions": [],
  "confidence": 0.0
}}
"""


def _safe_json_parse(s: str):
    s = s.strip()
    # Remove code fences like ```json ... ```
    if "```" in s:
        parts = s.split("```")
        # pick the largest chunk that likely contains JSON
        s = max(parts, key=len).strip()
        if s.startswith("json"):
            s = s[4:].strip()
    # Try direct parse
    try:
        return json.loads(s)
    except Exception:
        pass

    # If no braces at all but contains intent key, wrap whole string
    if '{' not in s and '"intent"' in s:
        try:
            candidate = '{' + s.strip().strip(',') + '}'
            return json.loads(candidate)
        except Exception:
            pass

    # Handle case where model returns key-values without outer braces
    if s.startswith('"intent"') or s.startswith("'intent'") or '"intent"' in s:
        try:
            candidate = '{' + s + '}'
            return json.loads(candidate)
        except Exception:
            pass

    # Aggressive extraction: find first valid JSON object
    start = s.find("{")
    while start != -1:
        end = s.rfind("}")
        if end == -1 or end <= start:
            break
        candidate = s[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            start = s.find("{", start + 1)
            continue

    # Fallback
    return {
        "intent": None,
        "entities": {},
        "confidence": 0.0,
        "_raw": s,
    }


def call_bedrock(text: str, context: Optional[Dict[str, Any]] = None):
    adapter = BedrockTextAdapter()

    messages = [
        {"role": "user", "content": build_prompt(text, context=context)}
    ]

    raw = adapter.complete(messages=messages, system=_SYSTEM_PROMPT)

    parsed = _safe_json_parse(raw)

    # Ensure shape
    return {
        "intent": parsed.get("intent"),
        "entities": parsed.get("entities", {}),
        "missing_fields": parsed.get("missing_fields", []) or [],
        "follow_up_questions": parsed.get("follow_up_questions", []) or [],
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "_raw": raw,
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
    adapter = BedrockTextAdapter()
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
    adapter = BedrockTextAdapter()

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
    adapter = BedrockTextAdapter()
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

    adapter = BedrockTextAdapter()
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
