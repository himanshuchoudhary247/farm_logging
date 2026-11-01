"""Tests for the A2UI weather forecast card (services/a2ui/weather_widget.py).

The weather result is built by the repo's own pincode_store._build and
weather_alert.get_weather_alert (only the network calls -- geocoding, the
Open-Meteo forecast, seasonal and feed prices -- are replaced), so the card
is tested against exactly what the weather tool hands the chat."""
from __future__ import annotations

import json
from datetime import date

import pytest

from services.a2ui import weather_widget as ww
from services.a2ui import widgets
from services.pincode_store import store
from services.weather_alert import service as weather_service

TODAY = date(2026, 10, 29)


def _forecast(**overrides):
    daily = {
        "time": ["2026-10-29", "2026-10-30", "2026-10-31"],
        "weather_code": [1, 61, 3],
        "precipitation_sum": [0.0, 12.4, 2.5],
        "wind_speed_10m_max": [10.0, 22.0, 14.0],
        "temperature_2m_max": [33.6, 38.9, 30.2],
        "temperature_2m_min": [21.4, 27.0, 20.0],
        "relative_humidity_2m_mean": [55, 80, 61],
    }
    daily.update(overrides)
    return {"daily": daily}


@pytest.fixture
def real_result(monkeypatch):
    """What get_weather_context returns for PIN 411001, via the real code."""
    def build(**overrides):
        monkeypatch.setattr(weather_service, "resolve_location", lambda q, country_code="in": weather_service.ResolvedLocation(
            query=q, display_name="Pune City, Pune, Maharashtra, 411001, India", lat=18.5, lon=73.8))
        monkeypatch.setattr(weather_service, "_fetch_forecast", lambda lat, lon, days=3: _forecast(**overrides))
        monkeypatch.setattr(store, "get_seasonal_advisory_data", lambda pin, days=7: {"district": "Pune", "state": "Maharashtra"})
        monkeypatch.setattr(store, "get_feed_price_snapshot", lambda state: {"state": state})
        return store._build("411001")
    return build


def _parts(messages):
    create, update, data = messages
    comps = {c["id"]: c for c in update["updateComponents"]["components"]}
    return create["createSurface"], comps, data["updateDataModel"]


def _row_texts(comps, i):
    """The texts of day tile i, top to bottom."""
    return [comps[c]["text"] for c in comps[f"day{i}_col"]["children"]]


# ---- shape ---------------------------------------------------------------

def test_card_follows_a2ui_v09_and_is_read_only(real_result):
    messages = ww.build_weather_widget(real_result(), "en-IN", surface_id="weather-s1", today=TODAY)
    assert [list(m)[1] for m in messages] == ["createSurface", "updateComponents", "updateDataModel"]
    create, comps, data = _parts(messages)
    assert create["surfaceId"] == data["surfaceId"] == "weather-s1"
    assert comps["root"]["component"] == "Card"
    assert not any(c["component"] in {"Button", "TextField", "ChoicePicker", "DateTimeInput"} for c in comps.values())
    json.dumps(messages, ensure_ascii=False)


def test_only_basic_catalog_components_and_every_reference_exists(real_result):
    allowed = {"Card", "Column", "Row", "Text", "Divider"}
    _, comps, _ = _parts(ww.build_weather_widget(real_result(), "en-IN", today=TODAY))
    assert {c["component"] for c in comps.values()} <= allowed
    for c in comps.values():
        for ref in ([c["child"]] if "child" in c else []) + list(c.get("children") or []):
            assert ref in comps, (c["id"], ref)


# ---- content ---------------------------------------------------------------

def test_place_risk_and_one_row_per_day(real_result):
    result = real_result()
    _, comps, _ = _parts(ww.build_weather_widget(result, "en-IN", today=TODAY))
    assert comps["place"]["text"] == "Pune, Maharashtra (411001)"
    assert comps["risk"]["text"].endswith(ww._TEXT["en"][result["weather"]["risk_level"]])
    assert comps["days"]["component"] == "Row" and comps["days"]["children"] == ["day0", "day1", "day2"]
    for i in range(3):
        assert comps[f"day{i}"]["component"] == "Card" and comps[f"day{i}"]["weight"] == 1
        assert comps[f"day{i}_col"]["align"] == "center"
    assert comps["day0_sky"]["variant"] == "h1", "the sky picture is the biggest thing on a tile"


def test_row_numbers_come_from_the_forecast(real_result):
    _, comps, _ = _parts(ww.build_weather_widget(real_result(), "en-IN", today=TODAY))
    assert _row_texts(comps, 0) == ["Today", "⛅", "34° / 21°", "🌧 0 mm", "💧 55%"]
    assert _row_texts(comps, 1) == ["Tomorrow", "🌧️", "39° / 27°", "🌧 12 mm", "💧 80%"]
    assert _row_texts(comps, 2) == ["Sat", "☁️", "30° / 20°", "🌧 2.5 mm", "💧 61%"]


def test_a_calm_forecast_has_no_warnings(real_result):
    result = real_result()
    assert result["weather"]["alerts"] == []
    _, comps, _ = _parts(ww.build_weather_widget(result, "en-IN", today=TODAY))
    assert not any(c.endswith("_warning") for c in comps)


def test_the_risky_day_gets_its_own_warning(real_result):
    """Alerts come from weather_alert's own classification of the real
    forecast: a thunderstorm with 40 mm rain and 55 km/h wind tomorrow."""
    result = real_result(weather_code=[1, 95, 3], precipitation_sum=[0.0, 40.0, 16.0],
                         wind_speed_10m_max=[10.0, 55.0, 12.0])
    assert {a["date"]: a["level"] for a in result["weather"]["alerts"]} == {"2026-10-30": "high", "2026-10-31": "medium"}
    _, comps, _ = _parts(ww.build_weather_widget(result, "en-IN", today=TODAY))
    assert _row_texts(comps, 1)[1] == "⛈️"
    assert _row_texts(comps, 1)[-1] == "⚠️ Thunderstorm, Heavy rain, Strong wind"
    assert _row_texts(comps, 2)[-1] == "⚠️ Rain"
    assert not any("⚠️" in t for t in _row_texts(comps, 0))
    assert comps["risk"]["text"] == "🔴 High risk"


@pytest.mark.parametrize("alert, expected", [
    ({"level": "high", "heat_stress_level": "high"}, "⚠️ Heat stress"),
    ({"level": "medium", "wind_kph": 31.0}, "⚠️ Strong wind"),
    ({"level": "high", "reasons": ["something new"]}, "⚠️ Weather warning"),
    ({"level": "low", "rain_mm": 40.0}, ""),
    (None, ""),
    ("x", ""),
])
def test_warning_words(alert, expected):
    assert ww._warning(alert, ww._TEXT["en"]) == expected


@pytest.mark.parametrize("code, icon", [(0, "☀️"), (2, "⛅"), (3, "☁️"), (45, "🌫️"), (53, "🌦️"), (81, "🌦️"),
                                        (63, "🌧️"), (73, "❄️"), (96, "⛈️"), (1000, ""), (None, ""), ("x", "")])
def test_sky_icon_for_each_weather_code(code, icon):
    assert ww._sky_icon(code) == icon


def test_day_names_after_tomorrow_follow_the_calendar():
    text = ww._TEXT["hi"]
    assert [ww._day_label(f"2026-11-0{d}", date(2026, 11, 1), text) for d in range(1, 8)] == \
        ["आज", "कल", "मंगल", "बुध", "गुरु", "शुक्र", "शनि"]


def test_missing_numbers_show_a_dash_not_a_crash(real_result):
    result = real_result(temperature_2m_max=[None, 30, 30], precipitation_sum=[None, 1, 1],
                         relative_humidity_2m_mean=[])
    _, comps, _ = _parts(ww.build_weather_widget(result, "en-IN", today=TODAY))
    assert _row_texts(comps, 0) == ["Today", "⛅", "– / 21°", "🌧 – mm"], "no humidity piece when it is missing"


@pytest.mark.parametrize("bad", ["hot", True, float("nan"), None, [1]])
def test_odd_values_are_not_shown_as_numbers(bad):
    assert ww._whole(bad) == "–" and ww._rain(bad) == "–"


def test_place_falls_back_to_the_resolved_name_then_the_pin(real_result):
    result = real_result()
    result["district"] = result["state"] = None
    assert ww._place(result, result["weather"]) == "Pune City, Pune (411001)"
    result["weather"]["resolved_location"] = {}
    assert ww._place(result, result["weather"]) == "411001"


def test_today_is_judged_in_india_time():
    # 00:30 IST on 30 Oct is still 29 Oct in UTC.
    from datetime import datetime, timezone
    utc = datetime(2026, 10, 29, 19, 0, tzinfo=timezone.utc)
    assert utc.astimezone(ww._FARM_TZ).date() == date(2026, 10, 30)


def test_a_date_that_is_not_iso_is_shown_as_it_is():
    assert ww._day_label("Fri", TODAY, ww._TEXT["en"]) == "Fri"
    assert ww._day_label("2026-02-30", TODAY, ww._TEXT["en"]) == "2026-02-30"


def test_at_most_a_week_of_rows(real_result):
    many = [f"2026-11-{d:02d}" for d in range(1, 15)]
    result = real_result(time=many, weather_code=[1] * 14, precipitation_sum=[0] * 14, wind_speed_10m_max=[5] * 14,
                         temperature_2m_max=[30] * 14, temperature_2m_min=[20] * 14, relative_humidity_2m_mean=[50] * 14)
    _, comps, _ = _parts(ww.build_weather_widget(result, "en-IN", today=TODAY))
    assert len(comps["days"]["children"]) == ww.MAX_DAYS == 3
    assert [_row_texts(comps, i)[0] for i in range(3)] == ["Sun", "Mon", "Tue"], "the first three days are kept"


# ---- when there is no card ---------------------------------------------------

@pytest.mark.parametrize("result", [
    {"error": "no_location", "message": "Need a PIN code or place name to check the weather."},
    {"error": "Could not resolve location"},
    {"pin": "411001", "weather": None},
    {"pin": "411001", "weather": {"forecast_days": []}},
    {"pin": "411001", "weather": {"forecast_days": [{"date": ""}, "x", None]}},
    None, "text", [],
])
def test_no_card_without_a_forecast(result):
    assert ww.build_weather_widget(result, "en-IN", today=TODAY) is None


def test_the_farm_details_added_by_the_tool_do_not_matter(real_result):
    result = {**real_result(), "your_farm": {"animals": {"goat": 12}}}
    assert ww.build_weather_widget(result, "en-IN", today=TODAY) is not None


# ---- language -------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["en-IN", "hi-IN", "mr-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN"])
def test_words_are_in_the_farmers_language(real_result, lang):
    _, comps, _ = _parts(ww.build_weather_widget(real_result(), lang, today=TODAY))
    text = ww._TEXT[lang.split("-")[0]]
    assert comps["title"]["text"] == text["title"]
    assert _row_texts(comps, 0)[0] == text["today"]


def test_every_language_has_every_word():
    assert all(set(t) == set(ww._TEXT["en"]) for t in ww._TEXT.values())
    assert all(len(t["days"]) == 7 and len(set(t["days"])) == 7 for t in ww._TEXT.values())


@pytest.mark.parametrize("language", ["fr-FR", "", None])
def test_an_unknown_language_gets_english(real_result, language):
    _, comps, _ = _parts(ww.build_weather_widget(real_result(), language, today=TODAY))
    assert comps["title"]["text"] == ww._TEXT["en"]["title"]


# ---- live entry point and dispatcher --------------------------------------------

def test_dispatcher_sends_the_card_for_weather_replies(real_result, monkeypatch):
    monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)
    messages = widgets.widget_for("weather_alert", "f-001", "s1", real_result(), "en-IN")
    assert messages[0]["createSurface"]["surfaceId"] == "weather-s1"


def test_switched_off_sends_nothing(real_result, monkeypatch):
    monkeypatch.setenv("CHAT_A2UI_WIDGETS", "off")
    assert ww.weather_widget_for("f-001", "s1", real_result(), "en-IN") is None


def test_a_failure_while_building_drops_only_the_card(real_result, monkeypatch):
    monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)

    def boom(*a, **k):
        raise RuntimeError("broken")

    monkeypatch.setattr(ww, "build_weather_widget", boom)
    assert ww.weather_widget_for("f-001", "s1", real_result(), "en-IN") is None
