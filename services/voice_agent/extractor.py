from typing import Any

from llm.adapters import get_text_adapter


SCHEMA = {
    "health_log": {
        "required": ["animal", "issue"],
        "optional": ["appetite", "temperature_c", "duration", "feces", "notes"],
    }
}


def detect_intent(text: str) -> str:
    adapter = get_text_adapter()
    prompt = (
        "You are an intent classifier for a livestock assistant.\n"
        "Classes: health_log, consultation, general.\n"
        "Return ONLY one label.\n"
        f"Text: {text}"
    )
    out = adapter.complete([{"role": "user", "content": prompt}])
    return out.strip().lower()


def extract_health_log(text: str) -> dict[str, Any]:
    adapter = get_text_adapter()
    prompt = f"""
You extract structured veterinary health log data.

Return STRICT JSON only.

Schema:
{{
  "animal": string | null,
  "issue": string,
  "appetite": "normal" | "reduced" | "off_feed" | null,
  "temperature_c": number | null,
  "duration": string | null,
  "feces": string | null,
  "notes": string | null
}}

Rules:
- Always include "issue" (summarize symptoms clearly)
- Map phrases like "not eating" -> appetite = "reduced"
- Extract numbers for temperature if present
- Keep null if unknown

Examples:
Input: "Cow not eating and has fever since 2 days"
Output:
{{
  "animal": "cow",
  "issue": "not eating and fever",
  "appetite": "reduced",
  "temperature_c": null,
  "duration": "2 days",
  "feces": null,
  "notes": null
}}

Text: {text}
"""
    out = adapter.complete([{"role": "user", "content": prompt}])
    import json

    try:
        return json.loads(out)
    except Exception:
        return {"issue": text}
import datetime


def _normalize_date(value):
    if not value:
        return None
    v = str(value).lower().strip()
    today = datetime.date.today()

    if v in ["today"]:
        return today.isoformat()
    if v in ["yesterday"]:
        return (today - datetime.timedelta(days=1)).isoformat()
    if v in ["tomorrow"]:
        return (today + datetime.timedelta(days=1)).isoformat()

    return value


def normalize_entities(entities: dict) -> dict:
    """Light normalization layer to make entities DB-friendly"""
    if not entities:
        return {}

    out = dict(entities)

    # Normalize date fields
    if "date" in out:
        out["date"] = _normalize_date(out["date"])

    if "date_of_event" in out:
        out["date_of_event"] = _normalize_date(out["date_of_event"])

    # Normalize symptoms to list
    if "symptoms" in out and isinstance(out["symptoms"], str):
        out["symptoms"] = [out["symptoms"]]

    # Lowercase enums
    for key in ["species", "sex", "event_type"]:
        if key in out and isinstance(out[key], str):
            out[key] = out[key].lower()

    return out
