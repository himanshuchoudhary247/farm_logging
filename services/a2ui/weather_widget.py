"""Weather forecast card as an A2UI widget (https://a2ui.org, spec v0.9).

When Chocolate answers a weather question with real forecast data, its reply
also carries a small read-only card: the place and overall risk on top, then
three tiles side by side -- today, tomorrow, the day after -- each with the
day name, a big sky picture, max/min temperature, rain and humidity, and a
warning on a day weather_alert flags as risky. Built like a phone weather
app so a farmer can read it at a glance, even without reading much text.

Layout uses two presentation hints the FlokIQ app reads: "weight" (tiles
share the row equally) and "align": "center" on a Column. A renderer that
does not know them still shows every tile and number, only less neatly.
The written answer is unchanged; the card only shows the numbers it is based
on, so the farmer can see the next days at a glance.

No card when there is no forecast (the agent asked for a PIN code, the
lookup failed, or the data has no days). The card has no buttons and sends
nothing back.

Built from the weather tool's own result (services/pincode_store
get_pincode_data: {"pin", "district", "state", "weather": {"risk_level",
"resolved_location", "forecast_days": [...]}}), never from the model's text.
"""
from __future__ import annotations

import logging
import re
from datetime import date as _date, datetime, timedelta, timezone
from typing import Any, Optional

from services.a2ui.common import clean, lang_code, surface_messages, widgets_enabled

_log = logging.getLogger("a2ui_weather_widget")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

# Today, tomorrow, the day after: three tiles fit a phone screen side by side.
MAX_DAYS = 3
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RISK_ICON = {"low": "🟢", "medium": "🟡", "high": "🔴"}
# FlokIQ farmers are in India; the server clock may be UTC, which is still
# "yesterday" until 5:30 am IST (same reasoning as bedrock_adapter's dates).
# A fixed +05:30 offset: India has no daylight saving, and it needs no time
# zone database (not always installed on Windows).
_FARM_TZ = timezone(timedelta(hours=5, minutes=30))

# Words in the farmer's language. Numbers carry icons (🌡 🌧 💧) so a row
# reads the same in every language without more words.
_TEXT: dict[str, dict[str, Any]] = {
    "en": {"title": "Weather forecast", "low": "Low risk", "medium": "Medium risk", "high": "High risk",
           "today": "Today", "tomorrow": "Tomorrow",
           "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
           "storm": "Thunderstorm", "heavy_rain": "Heavy rain", "rain": "Rain", "wind": "Strong wind",
           "heat": "Heat stress", "warning": "Weather warning"},
    "hi": {"title": "मौसम का पूर्वानुमान", "low": "कम जोखिम", "medium": "मध्यम जोखिम", "high": "ज़्यादा जोखिम",
           "today": "आज", "tomorrow": "कल",
           "days": ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"],
           "storm": "आंधी-तूफ़ान", "heavy_rain": "तेज़ बारिश", "rain": "बारिश", "wind": "तेज़ हवा",
           "heat": "गर्मी का तनाव", "warning": "मौसम चेतावनी"},
    "mr": {"title": "हवामान अंदाज", "low": "कमी धोका", "medium": "मध्यम धोका", "high": "जास्त धोका",
           "today": "आज", "tomorrow": "उद्या",
           "days": ["सोम", "मंगळ", "बुध", "गुरु", "शुक्र", "शनि", "रवि"],
           "storm": "वादळी पाऊस", "heavy_rain": "जोरदार पाऊस", "rain": "पाऊस", "wind": "जोरदार वारा",
           "heat": "उष्णतेचा ताण", "warning": "हवामान इशारा"},
    "ta": {"title": "வானிலை முன்னறிவிப்பு", "low": "குறைந்த ஆபத்து", "medium": "நடுத்தர ஆபத்து",
           "high": "அதிக ஆபத்து", "today": "இன்று", "tomorrow": "நாளை",
           "days": ["திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி", "ஞாயிறு"],
           "storm": "இடியுடன் மழை", "heavy_rain": "கனமழை", "rain": "மழை", "wind": "பலத்த காற்று",
           "heat": "வெப்ப அழுத்தம்", "warning": "வானிலை எச்சரிக்கை"},
    "te": {"title": "వాతావరణ సూచన", "low": "తక్కువ ప్రమాదం", "medium": "మధ్యస్థ ప్రమాదం", "high": "ఎక్కువ ప్రమాదం",
           "today": "ఈరోజు", "tomorrow": "రేపు",
           "days": ["సోమ", "మంగళ", "బుధ", "గురు", "శుక్ర", "శని", "ఆది"],
           "storm": "ఉరుములతో వర్షం", "heavy_rain": "భారీ వర్షం", "rain": "వర్షం", "wind": "బలమైన గాలి",
           "heat": "వేడి ఒత్తిడి", "warning": "వాతావరణ హెచ్చరిక"},
    "kn": {"title": "ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ", "low": "ಕಡಿಮೆ ಅಪಾಯ", "medium": "ಮಧ್ಯಮ ಅಪಾಯ", "high": "ಹೆಚ್ಚಿನ ಅಪಾಯ",
           "today": "ಇಂದು", "tomorrow": "ನಾಳೆ",
           "days": ["ಸೋಮ", "ಮಂಗಳ", "ಬುಧ", "ಗುರು", "ಶುಕ್ರ", "ಶನಿ", "ಭಾನು"],
           "storm": "ಗುಡುಗು ಸಹಿತ ಮಳೆ", "heavy_rain": "ಭಾರಿ ಮಳೆ", "rain": "ಮಳೆ", "wind": "ಬಲವಾದ ಗಾಳಿ",
           "heat": "ಶಾಖದ ಒತ್ತಡ", "warning": "ಹವಾಮಾನ ಎಚ್ಚರಿಕೆ"},
    "ml": {"title": "കാലാവസ്ഥാ പ്രവചനം", "low": "കുറഞ്ഞ അപകടസാധ്യത", "medium": "ഇടത്തരം അപകടസാധ്യത",
           "high": "ഉയർന്ന അപകടസാധ്യത", "today": "ഇന്ന്", "tomorrow": "നാളെ",
           "days": ["തിങ്കൾ", "ചൊവ്വ", "ബുധൻ", "വ്യാഴം", "വെള്ളി", "ശനി", "ഞായർ"],
           "storm": "ഇടിമിന്നലോടെ മഴ", "heavy_rain": "കനത്ത മഴ", "rain": "മഴ", "wind": "ശക്തമായ കാറ്റ്",
           "heat": "ചൂട് സമ്മർദ്ദം", "warning": "കാലാവസ്ഥാ മുന്നറിയിപ്പ്"},
}

# WMO weather codes (what Open-Meteo returns) -> one picture per day.
_STORM_CODES = {95, 96, 99}


def _sky_icon(code: Any) -> str:
    n = _number(code)
    if n is None:
        return ""
    c = int(n)
    if c == 0:
        return "☀️"
    if c in (1, 2):
        return "⛅"
    if c == 3:
        return "☁️"
    if c in (45, 48):
        return "🌫️"
    if 51 <= c <= 57 or 80 <= c <= 82:
        return "🌦️"
    if 61 <= c <= 67:
        return "🌧️"
    if 71 <= c <= 77 or c in (85, 86):
        return "❄️"
    if c in _STORM_CODES:
        return "⛈️"
    return ""


def _warning(alert: Optional[dict[str, Any]], text: dict[str, Any]) -> str:
    """Short words for a medium/high day alert from weather_alert's own
    classification (its rain, wind, storm and heat checks); '' when the
    day has no such alert."""
    if not isinstance(alert, dict) or clean(alert.get("level")).lower() not in {"medium", "high"}:
        return ""
    words: list[str] = []
    code, rain, wind = _number(alert.get("weather_code")), _number(alert.get("rain_mm")), _number(alert.get("wind_kph"))
    if code is not None and int(code) in _STORM_CODES:
        words.append(text["storm"])
    if rain is not None and rain >= 35:
        words.append(text["heavy_rain"])
    elif rain is not None and rain >= 15:
        words.append(text["rain"])
    if wind is not None and wind >= 30:
        words.append(text["wind"])
    if clean(alert.get("heat_stress_level")).lower() in {"medium", "high"}:
        words.append(text["heat"])
    # The alert says something is wrong even if its reasons change later.
    return "⚠️ " + (", ".join(words) if words else text["warning"])


def _number(value: Any) -> Optional[float]:
    """A real number, or None (missing, text, bool, NaN)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return None if value != value else float(value)  # NaN != NaN


def _whole(value: Any) -> str:
    n = _number(value)
    return "–" if n is None else str(int(round(n)))


def _degrees(value: Any) -> str:
    n = _number(value)
    return "–" if n is None else f"{int(round(n))}°"


def _rain(value: Any) -> str:
    n = _number(value)
    if n is None:
        return "–"
    return str(int(round(n))) if n >= 10 or n == int(n) else f"{n:.1f}"


def _day_label(raw: Any, today: _date, text: dict[str, Any]) -> str:
    """"Today", "Tomorrow", then the weekday ("Sat"); the raw text if it is
    not a date."""
    value = clean(raw)
    if not _DATE_RE.match(value):
        return value or "–"
    try:
        day = _date.fromisoformat(value)
    except ValueError:
        return value
    if day == today:
        return text["today"]
    if day == today + timedelta(days=1):
        return text["tomorrow"]
    return text["days"][day.weekday()]


def _place(result: dict[str, Any], weather: dict[str, Any]) -> str:
    """District, state (PIN) when known; else the first parts of the
    resolved place name; else the PIN."""
    pin = clean(result.get("pin"))
    parts = [clean(result.get("district")), clean(result.get("state"))]
    place = ", ".join(p for p in parts if p)
    if not place:
        location = weather.get("resolved_location") if isinstance(weather.get("resolved_location"), dict) else {}
        place = ", ".join(p.strip() for p in clean(location.get("display_name")).split(",")[:2] if p.strip())
    if place and pin and pin not in place:
        return f"{place} ({pin})"
    return place or pin


def build_weather_widget(result: Any, language: str, surface_id: str = "weather",
                         today: Optional[_date] = None) -> Optional[list[dict]]:
    """A2UI v0.9 messages for the forecast card, or None when there is no
    forecast to show (error result, no weather data, no days)."""
    if not isinstance(result, dict) or result.get("error"):
        return None
    weather = result.get("weather")
    if not isinstance(weather, dict):
        return None
    days = [d for d in (weather.get("forecast_days") or []) if isinstance(d, dict) and clean(d.get("date"))]
    if not days:
        return None
    days = days[:MAX_DAYS]
    text = _TEXT[lang_code(language, _TEXT)]
    today = today or datetime.now(_FARM_TZ).date()

    components: list[dict[str, Any]] = [
        {"id": "root", "component": "Card", "child": "card"},
        {"id": "title", "component": "Text", "text": text["title"], "variant": "h4"},
    ]
    children = ["title"]
    place = _place(result, weather)
    if place:
        components.append({"id": "place", "component": "Text", "text": place, "variant": "caption"})
        children.append("place")
    risk = clean(weather.get("risk_level")).lower()
    if risk in _RISK_ICON:
        components.append({"id": "risk", "component": "Text", "text": f"{_RISK_ICON[risk]} {text[risk]}"})
        children.append("risk")
    components.append({"id": "divider", "component": "Divider"})
    children.append("divider")
    alerts = {clean(a.get("date")): a for a in (weather.get("alerts") or []) if isinstance(a, dict)}

    tiles: list[str] = []
    for i, day in enumerate(days):
        tile = f"day{i}"
        sky = _sky_icon(day.get("weather_code"))
        pieces = [("date", _day_label(day.get("date"), today, text), "h5")]
        if sky:
            pieces.append(("sky", sky, "h1"))
        pieces += [
            ("temp", f"{_degrees(day.get('temperature_2m_max'))} / {_degrees(day.get('temperature_2m_min'))}", "h5"),
            ("rain", f"🌧 {_rain(day.get('precipitation_sum'))} mm", "body"),
        ]
        if _number(day.get("relative_humidity_2m_mean")) is not None:
            pieces.append(("humidity", f"💧 {_whole(day.get('relative_humidity_2m_mean'))}%", "body"))
        warning = _warning(alerts.get(clean(day.get("date"))), text)
        if warning:
            pieces.append(("warning", warning, "caption"))
        cells = []
        for name, value, variant in pieces:
            cell = f"{tile}_{name}"
            components.append({"id": cell, "component": "Text", "text": value, "variant": variant})
            cells.append(cell)
        components.append({"id": f"{tile}_col", "component": "Column", "align": "center", "children": cells})
        components.append({"id": tile, "component": "Card", "weight": 1, "child": f"{tile}_col"})
        tiles.append(tile)
    components.append({"id": "days", "component": "Row", "children": tiles})
    children.append("days")

    components.insert(1, {"id": "card", "component": "Column", "children": children})
    return surface_messages(surface_id, components, "/weather", {})


def weather_widget_for(farmer_id: str, session_id: str, result: Any, language: str) -> Optional[list[dict]]:
    """The card for this weather reply, or None. Never raises: a problem
    building the card only drops the card, never the reply."""
    if not widgets_enabled() or not isinstance(result, dict):
        return None
    try:
        messages = build_weather_widget(result, language, surface_id=f"weather-{session_id}")
    except Exception as exc:  # the reply must never fail because of the card
        _log.warning("a2ui weather widget skipped farmer=%s err=%s", farmer_id, exc)
        return None
    if messages:
        days = len((result.get("weather") or {}).get("forecast_days") or [])
        _log.info("a2ui weather widget sent farmer=%s pin=%s days=%d", farmer_id, clean(result.get("pin")), days)
    return messages
