"""wttr.in weather data fetcher (free, no API key).

Fetches current conditions + short-term forecast from wttr.in, which
aggregates from multiple national weather services. Used as a third
weather source alongside Open-Meteo and IMD, giving cross-source verbose
for alerts. Honest label: 'wttr.in' (not branded as Google).
"""

from __future__ import annotations

from typing import Any

import requests

_WTTR_URL = "https://wttr.in/{query}?format=j1"
_HEADERS = {"User-Agent": "curl/8.0"}

_WEATHER_CODE_MAP = {
    "113": "Clear",
    "116": "Partly cloudy",
    "119": "Cloudy",
    "122": "Overcast",
    "143": "Fog",
    "176": "Patchy light rain",
    "200": "Thundery outbreaks",
    "230": "Blizzard",
    "248": "Fog",
    "260": "Freezing fog",
    "263": "Patchy light drizzle",
    "266": "Light drizzle",
    "281": "Freezing drizzle",
    "284": "Heavy freezing drizzle",
    "293": "Patchy light rain",
    "296": "Light rain",
    "299": "Moderate rain",
    "302": "Heavy rain",
    "305": "Very heavy rain",
    "308": "Torrential rain",
    "311": "Light sleet",
    "314": "Moderate sleet",
    "317": "Heavy sleet",
    "320": "Patchy light snow",
    "323": "Light snow",
    "326": "Moderate snow",
    "329": "Heavy snow",
    "332": "Very heavy snow",
    "335": "Blizzard",
    "338": "Blizzard",
    "350": "Freezing drizzle",
    "353": "Patchy light rain",
    "356": "Moderate rain",
    "359": "Heavy rain",
    "371": "Moderate snow",
    "374": "Heavy snow",
    "377": "Blizzard",
    "386": "Patchy light rain with thunder",
    "389": "Moderate rain with thunder",
    "392": "Patchy light snow with thunder",
    "395": "Heavy snow with thunder",
}

_SEVERE_CODES = {"200", "230", "302", "305", "308", "329", "332", "335", "338", "359", "377", "389", "395"}
_MODERATE_CODES = {"176", "266", "296", "299", "317", "320", "323", "326", "350", "353", "356", "371", "374", "386", "392"}


def _classify(code: str) -> dict[str, Any] | None:
    desc = _WEATHER_CODE_MAP.get(code, "Unknown")
    if code in _SEVERE_CODES:
        return {"level": "high", "condition": desc, "weather_code": code}
    if code in _MODERATE_CODES:
        return {"level": "medium", "condition": desc, "weather_code": code}
    return None


def fetch_wttr(pin: str, district: str, state: str = "") -> dict[str, Any]:
    """Fetch current weather condition from wttr.in and classify if severe."""
    try:
        resp = requests.get(
            _WTTR_URL.format(query=pin),
            headers=_HEADERS,
            timeout=12,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {"source": "wttr.in", "status": "unavailable", "alert": None}

    current = (data.get("current_condition") or [{}])[0]
    code = current.get("weatherCode", "")
    temp_c = current.get("temp_C", "")
    desc = (current.get("weatherDesc") or [{}])[0].get("value", "").strip()

    classified = _classify(code)
    return {
        "source": "wttr.in",
        "status": "ok",
        "current": {
            "temp_c": temp_c,
            "condition": desc,
            "weather_code": code,
        },
        "alert": {
            "level": classified["level"],
            "type": classified["condition"],
            "weather_code": classified["weather_code"],
            "source": "wttr.in",
        } if classified else None,
    }