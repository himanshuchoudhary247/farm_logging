"""Farm Summary: everything the app's "Farm Summary" card shows, in one call.

What comes back:
- weather for the farm's location (risk level, heat level, summary)
- how many active animals the farm has, per species
- which vaccinations are still pending (status "pending"), oldest due first
- a short AI suggestion in the farmer's language
- optionally, audio of that suggestion

The facts (weather, counts, vaccinations) are worked out in code, never by
the LLM. The LLM only turns those facts into advice, through
generate_llm_advisory, which already forbids invented numbers, caches
replies and returns None instead of raising.

Weather comes from services.pincode_store, the same cached source the
chatbot's weather agent uses, so it works for any PIN or place name (not
only the PINs in config/pincode_profiles.yaml) and the card agrees with
what the chatbot tells the farmer. The location is found in the same order
as the chatbot: saved weather location, then the farm's PIN.

Each part is built on its own. If the weather lookup, the LLM or the audio
fails, the other parts still come back and the failed part is named in
"errors", so the app can show the rest of the card.

Data comes from this service's own storage for now. Every read goes through
load_farm_data(), so moving to main_backend later means changing only that
function.

Env switches (both default on):
- FARM_SUMMARY_LLM_ENABLED: off -> no LLM call, suggestion is null.
- FARM_SUMMARY_AUDIO_ENABLED: off -> no audio, even if the app asks.
"""
from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional

_log = logging.getLogger("farm_summary")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

# The same 7 languages the advisory LLM and the app support.
SUPPORTED_LANGUAGES = ("en", "hi", "ta", "te", "kn", "mr", "ml")

# The card lists at most this many pending vaccinations (counts still cover all).
_MAX_VACCINATION_ITEMS = 50
# At most this many vaccination reminders go to the LLM, so weather advice
# still fits in its 5 actions.
_MAX_VACCINATION_POINTS = 3

_ON = {"1", "true", "yes", "on"}


def _flag(name: str, default: str = "true") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in _ON


def normalize_language(language: Optional[str]) -> str:
    lang = (language or "en").split("-")[0].strip().lower()
    return lang if lang in SUPPORTED_LANGUAGES else "en"


@dataclass
class FarmData:
    farmer: Any
    # False when this service has no record of the farmer yet (see load_farm_data).
    known_locally: bool
    animals: list
    farms: list
    vaccinations: list
    health_logs: list
    appointments: list


def load_farm_data(farmer_id: str) -> FarmData:
    """All reads for the summary. The only function to change when the data
    moves to main_backend.

    The app sends main_backend's farmer id, which this service may not have a
    record of yet (a farmer who has never registered an animal through the
    chatbot). /chat/turn serves any farmer id the same way, so instead of a
    404 such a farmer gets an empty local record: zero animals and
    vaccinations here, and the weather still found through the main_backend
    farm PIN (resolve_location)."""
    from storage import (
        animals_for_farmer,
        appointments_for_farmer,
        farms_for_farmer,
        get_farmer_by_id,
        health_logs_for_farmer,
        vaccination_records_for_farmer,
    )

    from models import Farmer

    farmer = get_farmer_by_id(farmer_id)
    known = farmer is not None
    if farmer is None:
        # Never saved: only lets the shared helpers below read .id/.name/
        # .weather_location without a special case.
        farmer = Farmer(id=farmer_id, name="", login_username="", password_hash="")
    return FarmData(
        farmer=farmer,
        known_locally=known,
        animals=animals_for_farmer(farmer_id),
        farms=farms_for_farmer(farmer_id),
        vaccinations=vaccination_records_for_farmer(farmer_id),
        health_logs=health_logs_for_farmer(farmer_id),
        appointments=appointments_for_farmer(farmer_id),
    )


def _is_active(animal: Any) -> bool:
    return (getattr(animal, "status", "active") or "active").strip().lower() == "active"


def count_animals(animals: list) -> dict[str, Any]:
    """Active animals only (sold/dead ones are not on the farm), per species,
    biggest group first."""
    counts: dict[str, int] = {}
    total = 0
    for animal in animals:
        if not _is_active(animal):
            continue
        total += 1
        species = (getattr(animal, "species", "") or "").strip().lower() or "unknown"
        counts[species] = counts.get(species, 0) + 1
    by_species = [
        {"species": species, "count": count}
        for species, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {"total": total, "by_species": by_species}


def _parse_date(raw: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(raw or "")[:10])
    except ValueError:
        return None


def pending_vaccinations(records: list, animals: list, today: date) -> dict[str, Any]:
    """Records with status "pending" (due, not yet given). Skips animals that
    are no longer active. A record whose animal isn't found is kept, with
    animal_name null, so a pending vaccine is never silently hidden.
    Overdue = due date before today. Oldest due first, no-date ones last."""
    by_id = {getattr(a, "id", None): a for a in animals}
    items: list[dict[str, Any]] = []
    for record in records:
        if (getattr(record, "status", "") or "").strip().lower() != "pending":
            continue
        animal = by_id.get(record.animal_id)
        if animal is not None and not _is_active(animal):
            continue
        due = _parse_date(record.due_date)
        items.append({
            "record_id": record.id,
            "animal_id": record.animal_id,
            "animal_name": animal.tag_or_name if animal is not None else None,
            "species": ((animal.species or "").strip().lower() or None) if animal is not None else None,
            "vaccine_name": record.vaccine_name,
            "due_date": due.isoformat() if due else None,
            "overdue": bool(due and due < today),
        })
    items.sort(key=lambda i: (i["due_date"] is None, i["due_date"] or "", i["animal_name"] or ""))
    return {
        "pending_count": len(items),
        "overdue_count": sum(1 for i in items if i["overdue"]),
        "items": items[:_MAX_VACCINATION_ITEMS],
        "truncated": len(items) > _MAX_VACCINATION_ITEMS,
    }


def _lower(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    return text or None


def resolve_location(farmer_id: str, data: FarmData) -> str:
    """Where to get the weather for, same order as the chatbot's weather
    tool: the farmer's saved weather location (PIN or place name), then the
    farm's PIN here, then the farm's PIN in main_backend. "" if none."""
    loc = str(getattr(data.farmer, "weather_location", "") or "").strip()
    if loc:
        return loc
    for farm in data.farms:
        if getattr(farm, "pincode", None):
            return str(farm.pincode).strip()
    try:
        from services.flokiq_sync import client as flokiq_sync
        return str(flokiq_sync.get_farm_pincode(farmer_id) or "").strip()
    except Exception as exc:
        _log.warning("farm summary main_backend PIN lookup failed farmer=%s: %s", farmer_id, exc)
        return ""


def load_weather(location: str) -> Optional[dict[str, Any]]:
    """Weather for a location as {"pin", "weather", "heat", "feed_market",
    "stale"}: the shape the personalized rules and the advisory LLM read.
    None if the weather could not be fetched (the error is logged)."""
    from services.cache_refresh.service import _extract_heat_summary
    from services.pincode_store import get_pincode_data

    data = get_pincode_data(location)
    weather = data.get("weather")
    if not weather:
        _log.warning("farm summary weather unavailable location=%s errors=%s", location, data.get("errors"))
        return None
    return {
        "pin": location,
        "weather": weather,
        "heat": _extract_heat_summary(weather),
        "feed_market": data.get("feed_market"),
        "stale": bool(data.get("stale")),
    }


def weather_card(general: dict[str, Any], location: str) -> dict[str, Any]:
    """Only the weather fields the card shows."""
    weather = general.get("weather") or {}
    heat = general.get("heat") or {}
    return {
        "available": True,
        "location": location,
        "risk_level": _lower(weather.get("risk_level")),
        "heat_level": _lower(heat.get("level")),
        "summary": weather.get("summary") or None,
        "stale": bool(general.get("stale")),
    }


def vaccination_points(vaccinations: dict[str, Any]) -> list[str]:
    """Pending vaccinations as plain English points for the LLM (it writes the
    advice in the farmer's language). Built from the facts only."""
    points = []
    shown = vaccinations["items"][:_MAX_VACCINATION_POINTS]
    for item in shown:
        who = item["animal_name"] or "one animal"
        if item["overdue"]:
            when = f"overdue since {item['due_date']}"
        elif item["due_date"]:
            when = f"due on {item['due_date']}"
        else:
            when = "due date not recorded"
        points.append(f"{item['vaccine_name']} vaccination for {who} is pending ({when}); arrange it with the vet.")
    remaining = vaccinations["pending_count"] - len(shown)
    if remaining > 0:
        points.append(f"{remaining} more vaccinations are pending; check the vaccination list.")
    return points


# Sent to the LLM when there is no weather for the farm (no location, or the
# lookup failed). Without it the advisory prompt's "if the weather is normal,
# say so" rule lets the LLM call missing weather "normal".
NO_WEATHER_POINT = (
    "Weather data for this farm is not available right now. Say this once in "
    "the summary only, not as an action, and say nothing about today's weather."
)


def build_suggestion(
    data: FarmData,
    location: str,
    general: Optional[dict[str, Any]],
    vaccinations: dict[str, Any],
    language: str,
) -> Optional[dict[str, Any]]:
    """{"summary", "actions", "language"} or None (LLM failed or bad reply).
    general is None when there is no weather: the LLM is then told so."""
    from services.advisory import build_farmer_profile, generate_personalized_recommendation
    from services.advisory.llm_advisory import generate_llm_advisory, summarize_livestock

    profile = build_farmer_profile(data.farmer, location, data.animals, data.health_logs, data.appointments, data.farms)
    if general:
        weather_points = list(generate_personalized_recommendation(profile, general).get("actions") or [])
    else:
        weather_points = [NO_WEATHER_POINT]
    return generate_llm_advisory(
        profile,
        summarize_livestock(data.animals),
        general or {},
        vaccination_points(vaccinations) + weather_points,
        language=language,
    )


def suggestion_audio(suggestion: dict[str, Any]) -> Optional[str]:
    """Base64 mp3 of the suggestion, or None if TTS fails."""
    from services.voice_agent.tts import synthesize_speech

    text = " ".join([suggestion.get("summary") or ""] + list(suggestion.get("actions") or [])).strip()
    audio, err = synthesize_speech(text, target_lang=suggestion.get("language"))
    if not audio:
        _log.warning("farm summary audio failed: %s", err)
        return None
    return base64.b64encode(audio).decode("ascii")


def build_farm_summary(
    farmer_id: str,
    language: str = "en",
    include_audio: bool = False,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """The full card, for any farmer id (see load_farm_data)."""
    t0 = time.time()
    lang = normalize_language(language)
    today = today or date.today()

    data = load_farm_data(farmer_id)

    errors: list[str] = []
    animals = count_animals(data.animals)
    vaccinations = pending_vaccinations(data.vaccinations, data.animals, today)

    location = resolve_location(farmer_id, data)
    general: Optional[dict[str, Any]] = None
    weather: dict[str, Any] = {
        "available": False, "location": location or None,
        "risk_level": None, "heat_level": None, "summary": None, "stale": False,
    }
    if not location:
        errors.append("weather_no_location")
    else:
        try:
            general = load_weather(location)
        except Exception as exc:
            _log.warning("farm summary weather failed farmer=%s location=%s: %s", farmer_id, location, exc)
            general = None
        if general is None:
            errors.append("weather")
        else:
            weather = weather_card(general, location)

    suggestion: Optional[dict[str, Any]] = None
    if not _flag("FARM_SUMMARY_LLM_ENABLED"):
        errors.append("suggestion_disabled")
    else:
        try:
            suggestion = build_suggestion(data, location, general, vaccinations, lang)
        except Exception as exc:
            _log.warning("farm summary suggestion failed farmer=%s: %s", farmer_id, exc)
            suggestion = None
        if suggestion is None:
            errors.append("suggestion")

    audio_base64: Optional[str] = None
    if include_audio and suggestion:
        if not _flag("FARM_SUMMARY_AUDIO_ENABLED"):
            errors.append("audio_disabled")
        else:
            try:
                audio_base64 = suggestion_audio(suggestion)
            except Exception as exc:
                _log.warning("farm summary audio failed farmer=%s: %s", farmer_id, exc)
                audio_base64 = None
            if audio_base64 is None:
                errors.append("audio")

    _log.info(
        "LATENCY farm_summary farmer=%s known_locally=%s lang=%s ms=%.0f animals=%d pending_vacc=%d errors=%s",
        farmer_id, data.known_locally, lang, (time.time() - t0) * 1000, animals["total"], vaccinations["pending_count"],
        ",".join(errors) or "none",
    )
    return {
        "farmer_id": farmer_id,
        "language": lang,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weather": weather,
        "animals": animals,
        "vaccinations": vaccinations,
        "suggestion": suggestion,
        "audio_base64": audio_base64,
        "errors": errors,
    }
