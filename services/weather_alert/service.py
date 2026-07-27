from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import requests


GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

_CACHE_TTL_SEC = 15 * 60
_cache: dict[str, tuple[float, Any]] = {}


@dataclass
class ResolvedLocation:
    query: str
    display_name: str
    lat: float
    lon: float


def _is_pin_code(value: str) -> bool:
    v = (value or "").strip()
    return v.isdigit() and 5 <= len(v) <= 8


def _cache_get(key: str) -> Any:
    item = _cache.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > _CACHE_TTL_SEC:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.time(), value)


def _request_json(url: str, *, params: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # pragma: no cover - exercised in live network failures
            last_error = e
            if attempt < 2:
                time.sleep(0.4 * (attempt + 1))
                continue
            raise RuntimeError(f"Weather provider request failed: {e}") from e
    raise RuntimeError(f"Weather provider request failed: {last_error}")


def resolve_location(query: str, country_code: str = "in") -> ResolvedLocation:
    q = (query or "").strip()
    if not q:
        raise ValueError("location query is empty")

    if _is_pin_code(q):
        query_text = f"{q}, {country_code.upper()}"
    else:
        query_text = q

    cache_key = f"geo:{country_code}:{query_text}".lower()
    cached = _cache_get(cache_key)
    if cached:
        return cached

    rows = _request_json(
        GEOCODE_URL,
        params={
            "q": query_text,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        },
        headers={"User-Agent": "farmer-chat-weather-alert/1.0"},
    )
    rows = rows or []
    if not rows:
        raise ValueError(f"Could not resolve location for '{query}'")

    row = rows[0]
    resolved = ResolvedLocation(
        query=q,
        display_name=str(row.get("display_name") or q),
        lat=float(row["lat"]),
        lon=float(row["lon"]),
    )
    _cache_set(cache_key, resolved)
    return resolved


def _classify_weather_alert(day: dict[str, Any]) -> dict[str, Any] | None:
    code = int(day.get("weather_code", -1))
    rain_mm = float(day.get("precipitation_sum", 0.0) or 0.0)
    wind_kph = float(day.get("wind_speed_10m_max", 0.0) or 0.0)

    reasons: list[str] = []
    level = "low"

    # Thunderstorm / violent weather codes (WMO)
    if code in {95, 96, 99}:
        level = "high"
        reasons.append("Thunderstorm risk")

    # Heavy rain risk
    if rain_mm >= 35:
        level = "high"
        reasons.append(f"Heavy rainfall forecast ({rain_mm:.1f} mm)")
    elif rain_mm >= 15:
        level = "medium" if level != "high" else level
        reasons.append(f"Moderate rainfall forecast ({rain_mm:.1f} mm)")

    # Strong wind risk
    if wind_kph >= 50:
        level = "high"
        reasons.append(f"Strong wind forecast ({wind_kph:.1f} km/h)")
    elif wind_kph >= 30:
        level = "medium" if level != "high" else level
        reasons.append(f"Windy conditions ({wind_kph:.1f} km/h)")

    if not reasons:
        return None

    return {
        "date": day.get("date"),
        "level": level,
        "reasons": reasons,
        "weather_code": code,
        "rain_mm": rain_mm,
        "wind_kph": wind_kph,
    }


def _fetch_forecast(lat: float, lon: float, days: int = 3) -> dict[str, Any]:
    horizon = max(1, min(days, 7))
    cache_key = f"forecast:{lat:.4f}:{lon:.4f}:{horizon}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = _request_json(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "timezone": "auto",
            "forecast_days": horizon,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        },
    )
    _cache_set(cache_key, data)
    return data


def _advisories_for_level(level: str) -> list[str]:
    if level == "high":
        return [
            "Move livestock to covered shelter before evening.",
            "Store dry fodder and clean water for 24-48 hours.",
            "Avoid open grazing during thunderstorm/wind windows.",
            "Keep emergency vet contacts ready and monitor weak animals.",
        ]
    if level == "medium":
        return [
            "Check roof/drainage and keep bedding area dry.",
            "Reduce long grazing trips during rain/wind hours.",
            "Observe appetite and stress signs, especially in calves/kids.",
        ]
    return [
        "Continue routine care and hydration.",
        "Re-check forecast tomorrow for changes.",
    ]


HISTORICAL_YEARS = 5


def _parse_district(display_name: str) -> str:
    parts = [p.strip() for p in display_name.split(",")]
    if len(parts) >= 3:
        return parts[-3]
    return parts[0] if parts else display_name


def _same_dates_past_years(years_back: int = 5) -> list[tuple[str, str]]:
    from datetime import datetime, timedelta
    today = datetime.now()
    start = today - timedelta(days=6)
    ranges: list[tuple[str, str]] = []
    for y in range(1, years_back + 1):
        sy = start.replace(year=start.year - y)
        ey = today.replace(year=today.year - y)
        ranges.append((sy.strftime("%Y-%m-%d"), ey.strftime("%Y-%m-%d")))
    return ranges


def get_historical_weather(lat: float, lon: float) -> dict[str, Any]:
    cache_key = f"hist:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    date_ranges = _same_dates_past_years(HISTORICAL_YEARS)
    all_years: list[dict[str, Any]] = []

    for start_date, end_date in date_ranges:
        try:
            data = _request_json(
                ARCHIVE_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": start_date,
                    "end_date": end_date,
                    "timezone": "auto",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                },
            )
            daily = data.get("daily") or {}
            temps_max = [x for x in (daily.get("temperature_2m_max") or []) if x is not None]
            temps_min = [x for x in (daily.get("temperature_2m_min") or []) if x is not None]
            rain = [x for x in (daily.get("precipitation_sum") or []) if x is not None]
            wind = [x for x in (daily.get("wind_speed_10m_max") or []) if x is not None]

            all_years.append({
                "year": start_date[:4],
                "period": f"{start_date} / {end_date}",
                "avg_temp_max": round(sum(temps_max) / len(temps_max), 1) if temps_max else None,
                "avg_temp_min": round(sum(temps_min) / len(temps_min), 1) if temps_min else None,
                "total_rainfall_mm": round(sum(rain), 1) if rain else 0.0,
                "avg_wind_kph": round(sum(wind) / len(wind), 1) if wind else 0.0,
                "extreme_rain_days": sum(1 for r in rain if r >= 15),
                "extreme_wind_days": sum(1 for w in wind if w >= 30),
            })
        except Exception:
            all_years.append({"year": start_date[:4], "period": f"{start_date} / {end_date}", "error": "data unavailable"})

    result = {
        "period_label": f"Same week, past {HISTORICAL_YEARS} years",
        "years": all_years,
    }

    temps_max_all = [y["avg_temp_max"] for y in all_years if y.get("avg_temp_max") is not None]
    temps_min_all = [y["avg_temp_min"] for y in all_years if y.get("avg_temp_min") is not None]
    rains_all = [y["total_rainfall_mm"] for y in all_years if y.get("total_rainfall_mm") is not None]
    winds_all = [y["avg_wind_kph"] for y in all_years if y.get("avg_wind_kph") is not None]

    result["summary"] = {
        "avg_high_temp": round(sum(temps_max_all) / len(temps_max_all), 1) if temps_max_all else None,
        "avg_low_temp": round(sum(temps_min_all) / len(temps_min_all), 1) if temps_min_all else None,
        "avg_rainfall_mm": round(sum(rains_all) / len(rains_all), 1) if rains_all else 0.0,
        "avg_wind_kph": round(sum(winds_all) / len(winds_all), 1) if winds_all else 0.0,
    }

    _cache_set(cache_key, result)
    return result


def get_seasonal_advisory_data(location_or_pin: str, country_code: str = "in", days: int = 7) -> dict[str, Any]:
    loc = resolve_location(location_or_pin, country_code=country_code)
    forecast = _fetch_forecast(loc.lat, loc.lon, days=days)
    historical = get_historical_weather(loc.lat, loc.lon)
    district = _parse_district(loc.display_name)
    return {
        "district": district,
        "location": loc.display_name,
        "lat": loc.lat,
        "lon": loc.lon,
        "forecast": forecast,
        "historical": historical,
    }


def get_weather_alert(location_or_pin: str, country_code: str = "in", days: int = 3) -> dict[str, Any]:
    loc = resolve_location(location_or_pin, country_code=country_code)
    forecast = _fetch_forecast(loc.lat, loc.lon, days=days)
    daily = forecast.get("daily") or {}

    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    rain = daily.get("precipitation_sum") or []
    wind = daily.get("wind_speed_10m_max") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []

    days_payload: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    for i, d in enumerate(dates):
        day = {
            "date": d,
            "weather_code": codes[i] if i < len(codes) else None,
            "precipitation_sum": rain[i] if i < len(rain) else None,
            "wind_speed_10m_max": wind[i] if i < len(wind) else None,
            "temperature_2m_max": tmax[i] if i < len(tmax) else None,
            "temperature_2m_min": tmin[i] if i < len(tmin) else None,
        }
        days_payload.append(day)
        alert = _classify_weather_alert(day)
        if alert:
            alerts.append(alert)

    top_level = "low"
    if any(a["level"] == "high" for a in alerts):
        top_level = "high"
    elif any(a["level"] == "medium" for a in alerts):
        top_level = "medium"

    summary = "No significant weather risk in next days."
    if top_level == "high":
        summary = "High weather risk detected. Take protective action for livestock and fodder."
    elif top_level == "medium":
        summary = "Moderate weather risk detected. Monitor animals and shelter arrangements."

    return {
        "query": location_or_pin,
        "resolved_location": {
            "display_name": loc.display_name,
            "lat": loc.lat,
            "lon": loc.lon,
        },
        "risk_level": top_level,
        "summary": summary,
        "advisories": _advisories_for_level(top_level),
        "alerts": alerts,
        "forecast_days": days_payload,
    }
