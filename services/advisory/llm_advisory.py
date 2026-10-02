"""LLM refinement of the weather advisory for one farmer.

Weather data (shared per location) plus this farmer's own animals and
recent health issues go to one LLM call, which writes a short advisory for
this farm in the farmer's language. The rule-based actions from
generate_personalized_recommendation are passed in as points the advice
must keep, so the safety-relevant rules are never lost.

Never raises: on any LLM error, timeout or badly shaped reply it returns
None, and the caller falls back to the rule-based advice.

Same LLM path as get_weather_recommendation (BedrockTextAdapter with
TaskTier.GENERATION), so the LLM_PROVIDER=freellmapi fallback applies too.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from datetime import date
from typing import Any, Iterable, Optional

_log = logging.getLogger("advisory.llm")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_LANGUAGES = {
    "en": "English", "hi": "Hindi", "ta": "Tamil", "te": "Telugu",
    "kn": "Kannada", "ml": "Malayalam",
}
_MAX_ACTIONS = 5
_MAX_SUMMARY_CHARS = 600
_MAX_ACTION_CHARS = 300

# Same inputs (farmer, data, language) -> reuse the advice instead of a new
# LLM call every time the app asks. Any change in weather or in the
# farmer's animals/issues changes the key, so stale advice isn't reused.
_CACHE_TTL_SEC = 12 * 60 * 60
_CACHE_MAX_ENTRIES = 500
_cache: "OrderedDict[str, tuple[float, dict[str, Any]]]" = OrderedDict()
_cache_lock = threading.Lock()

_SYSTEM = (
    "You are a practical livestock advisor for small farmers in India. "
    "You write short, clear advice for one farmer's own farm. "
    "Reply with JSON only."
)

_PROMPT = """Write weather advice for this farmer's own farm.

Farmer: {name}
Animals on the farm:
{livestock}
Recent health issues: {issues}

Weather and market data for their area:
{weather}

Advice already decided by our rules (keep the meaning of each point, in simpler words):
{base_actions}

Rules:
- Use only the facts above. Never invent animals, numbers, dates or prices.
- Make the advice specific to the animals they actually have (species, young animals, issues).
- Never name medicines or doses. If an animal is sick or an issue is serious, tell them to consult a vet.
- If the weather is normal and there are no issues, say so briefly.
- Write in {language}. Simple words, no markdown.
- At most {max_actions} actions, one short sentence each.

Reply with only this JSON:
{{"summary": "<one or two sentences>", "actions": ["<action>", "..."]}}"""


def _age_years(animal: Any, today: date) -> Optional[float]:
    if getattr(animal, "age_years", None) is not None:
        return float(animal.age_years)
    raw = (getattr(animal, "birth_date", None) or "")[:10]
    try:
        born = date.fromisoformat(raw)
    except ValueError:
        return None
    return (today - born).days / 365.25


def summarize_livestock(animals: Iterable[Any], today: Optional[date] = None) -> list[dict[str, Any]]:
    """Short per-species summary of ACTIVE animals: count, top breeds, sex
    split and how many are under one year. A summary, not the full list,
    so a large farm doesn't blow up the prompt."""
    today = today or date.today()
    groups: dict[str, dict[str, Any]] = {}
    for animal in animals:
        if (getattr(animal, "status", "active") or "active").strip().lower() != "active":
            continue
        species = (getattr(animal, "species", "") or "unknown").strip().lower()
        group = groups.setdefault(species, {"type": species, "count": 0, "breeds": {}, "female": 0, "male": 0, "under_1_year": 0})
        group["count"] += 1
        breed = (getattr(animal, "breed", "") or "").strip()
        if breed:
            group["breeds"][breed] = group["breeds"].get(breed, 0) + 1
        sex = (getattr(animal, "sex", "") or "").strip().lower()
        if sex in ("female", "f"):
            group["female"] += 1
        elif sex in ("male", "m"):
            group["male"] += 1
        age = _age_years(animal, today)
        if age is not None and age < 1:
            group["under_1_year"] += 1

    result = []
    for group in sorted(groups.values(), key=lambda g: -g["count"]):
        top = sorted(group["breeds"].items(), key=lambda kv: -kv[1])[:3]
        group["breeds"] = {name: count for name, count in top}
        result.append(group)
    return result


def _weather_facts(data: dict[str, Any]) -> dict[str, Any]:
    """Pick the useful facts from either weather shape: the cache_refresh
    "general alert" (weather.summary / risk_level / advisories, heat,
    feed_market) or pincode_store's get_pincode_data (weather =
    get_weather_alert output with alerts / forecast_days)."""
    weather = data.get("weather") or {}
    feed = (data.get("feed_market") or {}).get("commodities") or []
    facts = {
        "summary": weather.get("summary"),
        "risk_level": weather.get("risk_level"),
        "advisories": (weather.get("advisories") or [])[:5],
        "alerts": (weather.get("alerts") or [])[:5],
        "forecast_days": (weather.get("forecast_days") or [])[:3],
        "heat_level": (data.get("heat") or {}).get("level"),
        "feed_prices": [
            {"commodity": c.get("commodity"), "modal_price_avg": c.get("modal_price_avg")}
            for c in feed[:3]
        ],
    }
    return {k: v for k, v in facts.items() if v not in (None, [], {})}


def _parse_reply(text: str) -> Optional[dict[str, Any]]:
    """Expect {"summary": str, "actions": [str, ...]}; tolerate ``` fences or
    text around the JSON. Anything off-shape -> None."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get("summary")
    actions = data.get("actions")
    if not isinstance(summary, str) or not summary.strip():
        return None
    if not isinstance(actions, list):
        return None
    clean = [a.strip() for a in actions if isinstance(a, str) and a.strip()]
    if not clean:
        return None
    return {
        "summary": summary.strip()[:_MAX_SUMMARY_CHARS],
        "actions": [a[:_MAX_ACTION_CHARS] for a in clean[:_MAX_ACTIONS]],
    }


def _make_adapter():
    from services.llm_service.bedrock_adapter import BedrockTextAdapter, TaskTier
    return BedrockTextAdapter(task=TaskTier.GENERATION)


def _cache_key(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_llm_advisory(
    farmer_profile: dict[str, Any],
    livestock_summary: list[dict[str, Any]],
    weather_data: dict[str, Any],
    base_actions: Iterable[str],
    language: str = "en",
) -> Optional[dict[str, Any]]:
    """One LLM call -> {"summary", "actions", "language"} for this farmer,
    or None if anything goes wrong (caller then uses the rule-based advice)."""
    lang = (language or "en").split("-")[0].lower()
    if lang not in _LANGUAGES:
        lang = "en"
    facts = _weather_facts(weather_data or {})
    base = [str(a) for a in base_actions if str(a).strip()]
    issues = [str(i) for i in (farmer_profile.get("current_issues") or [])][:5]
    payload = {
        "farmer_id": farmer_profile.get("farmer_id"),
        "language": lang,
        "livestock": livestock_summary,
        "issues": issues,
        "weather": facts,
        "base_actions": base,
    }

    key = _cache_key(payload)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and time.time() - cached[0] < _CACHE_TTL_SEC:
            _cache.move_to_end(key)
            return cached[1]

    prompt = _PROMPT.format(
        name=farmer_profile.get("name") or "Farmer",
        livestock=json.dumps(livestock_summary, ensure_ascii=False) if livestock_summary else "No animals recorded.",
        issues=", ".join(issues) if issues else "None",
        weather=json.dumps(facts, ensure_ascii=False, default=str) if facts else "No weather data.",
        base_actions="\n".join(f"- {a}" for a in base) if base else "- None",
        language=_LANGUAGES[lang],
        max_actions=_MAX_ACTIONS,
    )
    try:
        reply = _make_adapter().complete(
            messages=[{"role": "user", "content": prompt}],
            system=_SYSTEM,
        )
    except Exception as exc:
        _log.warning("llm advisory failed farmer=%s: %s", farmer_profile.get("farmer_id"), exc)
        return None

    parsed = _parse_reply(reply or "")
    if parsed is None:
        _log.warning("llm advisory reply not usable farmer=%s", farmer_profile.get("farmer_id"))
        return None

    result = {**parsed, "language": lang}
    with _cache_lock:
        _cache[key] = (time.time(), result)
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)
    return result


def clear_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()
