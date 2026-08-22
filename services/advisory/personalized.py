from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from models import Animal, Appointment, Farm, Farmer, HealthLog


def _animal_index(farmer_profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    animals: dict[str, dict[str, Any]] = {}
    for entry in farmer_profile.get("livestock", []):
        animal_type = str(entry.get("type") or "").lower()
        if not animal_type:
            continue
        animals[animal_type] = entry
    return animals


def aggregate_livestock(animals: Iterable[Animal]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for animal in animals:
        species = (animal.species or "unknown").strip().lower()
        counts[species] = counts.get(species, 0) + 1
    return [{"type": species, "count": count} for species, count in counts.items()]


def recent_issues(logs: Iterable[HealthLog], limit: int = 5) -> list[str]:
    def _sort_key(log: HealthLog) -> tuple[str, str]:
        return (log.recorded_at or "", log.id)

    sorted_logs = sorted(logs, key=_sort_key, reverse=True)
    issues: list[str] = []
    for log in sorted_logs:
        issue = (log.issue or "").strip()
        if not issue:
            continue
        if issue not in issues:
            issues.append(issue)
        if len(issues) >= limit:
            break
    return issues


def recent_vet_visits(appointments: Iterable[Appointment], limit: int = 5) -> list[str]:
    rows = sorted(appointments, key=lambda a: (a.date or "", a.time or "", a.id), reverse=True)
    visits: list[str] = []
    for appt in rows:
        label = f"{appt.date} {appt.time}".strip()
        if label and label not in visits:
            visits.append(label)
        if len(visits) >= limit:
            break
    return visits


def infer_pin_code(request_pin: Optional[str], farmer: Farmer, farms: Iterable[Farm]) -> str:
    if request_pin:
        pin = str(request_pin).strip()
        if pin:
            return pin

    for farm in farms:
        if farm.pincode:
            return str(farm.pincode)

    candidate = (farmer.weather_location or "").strip()
    if candidate.isdigit():
        return candidate
    digits = "".join(ch for ch in candidate if ch.isdigit())
    if 5 <= len(digits) <= 8:
        return digits
    return ""


def build_farmer_profile(
    farmer: Farmer,
    pin: str,
    animals: Iterable[Animal],
    logs: Iterable[HealthLog],
    appointments: Iterable[Appointment],
    farms: Iterable[Farm],
) -> dict[str, Any]:
    return {
        "farmer_id": farmer.id,
        "name": farmer.name,
        "pin": pin,
        "livestock": aggregate_livestock(list(animals)),
        "current_issues": recent_issues(list(logs)),
        "recent_vet_visits": recent_vet_visits(list(appointments)),
        "farms": [f.model_dump() for f in farms],
    }


def generate_personalized_recommendation(
    farmer_profile: dict[str, Any],
    general_alert: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    animals = _animal_index(farmer_profile)

    weather = general_alert.get("weather") or {}
    heat = general_alert.get("heat") or {}
    feed_market = (general_alert.get("feed_market") or {}).get("commodities", [])

    recommendations: list[str] = []
    watch_items: list[str] = []

    risk_level = str(weather.get("risk_level") or "low").lower()
    if risk_level == "high":
        recommendations.append("Activate severe weather plan: secure sheds, stockpile fodder, and move weak animals under cover.")
    elif risk_level == "medium":
        recommendations.append("Review shelter drainage and shorten grazing windows during forecasted weather spikes.")

    heat_level = str(heat.get("level") or "low").lower()
    if heat_level in {"medium", "high"}:
        if "dairy_cattle" in animals or "buffalo" in animals:
            recommendations.append("Increase shade and electrolyte mix for dairy animals; monitor milk yield drops in the afternoon.")
        if "sheep" in animals or "goat" in animals:
            recommendations.append("Schedule grazing early morning/evening for small ruminants; provide misting or wet gunny cloth if THI stays high.")
        watch_items.append("Check respiration rate twice daily while THI remains elevated.")

    for issue in farmer_profile.get("current_issues", []):
        issue_lower = str(issue).lower()
        if "mastitis" in issue_lower and ("dairy_cattle" in animals or "buffalo" in animals):
            recommendations.append("Continue udder hygiene routine and keep bedding dry; plan vet follow-up if swelling persists.")
        if "foot" in issue_lower and ("sheep" in animals or "goat" in animals):
            recommendations.append("Inspect hoof health daily and apply antifungal wash after grazing on wet fields.")

    if feed_market:
        top_feed = feed_market[0]
        price = top_feed.get("modal_price_avg")
        commodity = top_feed.get("commodity")
        if price and commodity:
            recommendations.append(f"Plan feed purchase for {commodity} — current modal price ₹{int(price)} per quintal.")

    if farmer_profile.get("recent_vet_visits"):
        watch_items.append("Log follow-up outcomes from recent vet visit to keep the health record complete.")

    general_actions = weather.get("advisories") or []
    merged_actions = list(dict.fromkeys(general_actions + recommendations))

    return {
        "farmer_id": farmer_profile.get("farmer_id"),
        "farmer_name": farmer_profile.get("name"),
        "pin": general_alert.get("pin"),
        "generated_at": now,
        "general_summary": weather.get("summary"),
        "risk_level": weather.get("risk_level"),
        "heat_level": heat.get("level"),
        "actions": merged_actions,
        "watch_items": watch_items,
        "feed_market_highlights": feed_market[:3],
    }
