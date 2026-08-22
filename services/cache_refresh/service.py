from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from functools import lru_cache

import yaml

from services.weather_alert import service as weather_service
from services.market_prices.mandi import get_feed_price_snapshot


PIN_PROFILE_PATH = Path("config/pincode_profiles.yaml")
CACHE_SETTINGS_PATH = Path("config/cache_settings.yaml")
CACHE_ROOT = Path("data/cache")


@dataclass
class PinProfile:
    pin: str
    name: str | None
    district: str | None
    state: str | None
    default_animals: list[dict[str, Any]]
    farm_notes: list[str]
    raw: dict[str, Any]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_pin_profiles(path: Path | None = None) -> list[PinProfile]:
    cfg = _load_yaml(path or PIN_PROFILE_PATH)
    pins = cfg.get("pins") or []
    profiles: list[PinProfile] = []
    for item in pins:
        if not isinstance(item, dict) or not item.get("pin"):
            continue
        profiles.append(
            PinProfile(
                pin=str(item.get("pin")).strip(),
                name=item.get("name"),
                district=item.get("district"),
                state=item.get("state"),
                default_animals=list(item.get("default_animals") or []),
                farm_notes=list(item.get("farm_notes") or []),
                raw=item,
            )
        )
    return profiles


def load_cache_settings(path: Path | None = None) -> dict[str, Any]:
    return _load_yaml(path or CACHE_SETTINGS_PATH)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _cache_file_is_fresh(path: Path, refresh_hours: Any, now: datetime) -> bool:
    if not path.exists() or not isinstance(refresh_hours, (int, float)) or refresh_hours <= 0:
        return False
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    current = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    return current - modified_at < timedelta(hours=float(refresh_hours))


def _extract_heat_summary(weather_alert: dict[str, Any]) -> dict[str, Any]:
    best_level = "low"
    reason = None
    thi_max: float | None = None

    for day in weather_alert.get("forecast_days", []):
        thi = day.get("thi")
        if isinstance(thi, (int, float)):
            thi_max = thi if thi_max is None else max(thi_max, thi)

    for alert in weather_alert.get("alerts", []):
        level = alert.get("heat_stress_level")
        if level == "high":
            return {
                "level": "high",
                "reason": alert.get("heat_stress_reason"),
                "thi_max": thi_max,
            }
        if level == "medium" and best_level != "high":
            best_level = "medium"
            reason = alert.get("heat_stress_reason")

    return {"level": best_level, "reason": reason, "thi_max": thi_max}


def build_general_alert(
    pin_profile: PinProfile,
    weather_alert: dict[str, Any] | None,
    seasonal_data: dict[str, Any] | None,
    feed_snapshot: dict[str, Any] | None,
    generated_at: datetime,
    settings: dict[str, Any],
    errors: list[str] | None = None,
) -> dict[str, Any]:
    weather_block: dict[str, Any] | None = None
    heat_block: dict[str, Any] | None = None
    if weather_alert:
        weather_block = {
            "risk_level": weather_alert.get("risk_level"),
            "summary": weather_alert.get("summary"),
            "advisories": weather_alert.get("advisories", []),
            "alerts": weather_alert.get("alerts", []),
            "resolved_location": weather_alert.get("resolved_location"),
        }
        heat_block = _extract_heat_summary(weather_alert)

    historical_summary = None
    if seasonal_data:
        historical = seasonal_data.get("historical") or {}
        if isinstance(historical, dict):
            historical_summary = historical.get("summary")

    feed_block = None
    if feed_snapshot:
        feed_block = {
            "state": feed_snapshot.get("state"),
            "latest_fetched_at": feed_snapshot.get("latest_fetched_at"),
            "commodities": feed_snapshot.get("commodities", []),
        }

    weather_valid = _valid_until(settings.get("weather", {}), generated_at)
    market_valid = _valid_until(settings.get("market", {}), generated_at)
    valid_until_candidates = [dt for dt in [weather_valid, market_valid] if dt is not None]
    valid_until = min(valid_until_candidates).isoformat() if valid_until_candidates else None

    generated_iso = (
        generated_at.astimezone(timezone.utc)
        if generated_at.tzinfo is not None
        else generated_at.replace(tzinfo=timezone.utc)
    ).isoformat()

    return {
        "pin": pin_profile.pin,
        "location": {
            "name": pin_profile.name,
            "district": pin_profile.district,
            "state": pin_profile.state,
        },
        "generated_at": generated_iso,
        "valid_until": valid_until,
        "weather": weather_block,
        "heat": heat_block,
        "historical": historical_summary,
        "feed_market": feed_block,
        "profile": {
            "default_animals": pin_profile.default_animals,
            "farm_notes": pin_profile.farm_notes,
        },
        "errors": errors or [],
    }


def _valid_until(section: dict[str, Any], generated_at: datetime) -> datetime | None:
    refresh_hours = section.get("refresh_hours")
    if isinstance(refresh_hours, (int, float)) and refresh_hours > 0:
        return generated_at + timedelta(hours=float(refresh_hours))
    return None


def refresh_pin_cache(
    pin_profile: PinProfile,
    settings: dict[str, Any],
    cache_root: Path = CACHE_ROOT,
    now: datetime | None = None,
    services: Iterable[str] | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    cache_dir = cache_root / pin_profile.pin
    errors: list[str] = []
    selected_services = set(services or {"weather_alert", "seasonal_advisory", "feed_prices"})

    weather_alert: dict[str, Any] | None = None
    seasonal_data: dict[str, Any] | None = None
    feed_snapshot: dict[str, Any] | None = None

    weather_days = int(settings.get("weather", {}).get("alert_days") or 3)
    seasonal_days = int(settings.get("weather", {}).get("seasonal_days") or 7)

    weather_path = cache_dir / "weather_alert.json"
    weather_settings = settings.get("weather", {})
    if "weather_alert" not in selected_services:
        if weather_path.exists():
            weather_alert = _read_json(weather_path)
    elif _cache_file_is_fresh(weather_path, weather_settings.get("refresh_hours"), now):
        weather_alert = _read_json(weather_path)
    else:
        try:
            weather_alert = weather_service.get_weather_alert(pin_profile.pin, days=weather_days)
            _write_json(weather_path, weather_alert)
        except Exception as exc:  # pragma: no cover - network/runtime path
            errors.append(f"weather_alert: {exc}")

    seasonal_path = cache_dir / "seasonal_advisory.json"
    if "seasonal_advisory" not in selected_services:
        if seasonal_path.exists():
            seasonal_data = _read_json(seasonal_path)
    elif _cache_file_is_fresh(seasonal_path, weather_settings.get("refresh_hours"), now):
        seasonal_data = _read_json(seasonal_path)
    else:
        try:
            seasonal_data = weather_service.get_seasonal_advisory_data(pin_profile.pin, days=seasonal_days)
            _write_json(seasonal_path, seasonal_data)
        except Exception as exc:  # pragma: no cover
            errors.append(f"seasonal_advisory: {exc}")

    state_name = (
        (weather_alert or {}).get("resolved_location", {}).get("state")
        or pin_profile.state
    )
    market_path = cache_dir / "feed_prices.json"
    market_settings = settings.get("market", {})
    if "feed_prices" not in selected_services:
        if market_path.exists():
            feed_snapshot = _read_json(market_path)
    elif _cache_file_is_fresh(market_path, market_settings.get("refresh_hours"), now):
        feed_snapshot = _read_json(market_path)
    elif state_name:
        try:
            feed_snapshot = get_feed_price_snapshot(state_name)
            _write_json(market_path, feed_snapshot)
        except Exception as exc:  # pragma: no cover
            errors.append(f"feed_prices: {exc}")
    else:
        errors.append("feed_prices: unable to determine state")

    general_alert = build_general_alert(
        pin_profile,
        weather_alert,
        seasonal_data,
        feed_snapshot,
        now,
        settings,
        errors,
    )
    _write_json(cache_dir / "general_alert.json", general_alert)
    return general_alert


def refresh_all_pins(
    pin_profiles_path: Path | None = None,
    cache_settings_path: Path | None = None,
    target_pin: str | None = None,
    cache_root: Path = CACHE_ROOT,
    services: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    profiles = load_pin_profiles(pin_profiles_path)
    if target_pin:
        profiles = [p for p in profiles if p.pin == target_pin]
    settings = load_cache_settings(cache_settings_path)
    results: list[dict[str, Any]] = []
    for profile in profiles:
        results.append(refresh_pin_cache(profile, settings, cache_root=cache_root, services=services))
    return results


def read_cached_general_alert(pin: str, cache_root: Path = CACHE_ROOT) -> dict[str, Any] | None:
    path = cache_root / pin / "general_alert.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_cached_weather_alert(pin: str, cache_root: Path = CACHE_ROOT) -> dict[str, Any] | None:
    path = cache_root / pin / "weather_alert.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return None


def is_general_alert_stale(alert: dict[str, Any], now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    valid_until = _parse_iso(alert.get("valid_until"))
    if valid_until is None:
        return True
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    return now > valid_until


def find_pin_profile(pin: str, profiles: Iterable[PinProfile]) -> PinProfile | None:
    for profile in profiles:
        if profile.pin == pin:
            return profile
    return None


def ensure_general_alert(
    pin: str,
    settings: dict[str, Any],
    profiles: Iterable[PinProfile],
    cache_root: Path = CACHE_ROOT,
    force_refresh: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    profile = find_pin_profile(pin, profiles)
    if profile is None:
        raise ValueError(f"PIN {pin} is not configured")

    now = now or datetime.now(timezone.utc)
    if not force_refresh:
        cached = read_cached_general_alert(pin, cache_root=cache_root)
        if cached and not is_general_alert_stale(cached, now=now):
            return cached

    return refresh_pin_cache(profile, settings, cache_root=cache_root, now=now)
