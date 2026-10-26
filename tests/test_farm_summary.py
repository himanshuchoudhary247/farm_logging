"""Farm Summary (services/farm_summary): facts from real storage files in a
temp data dir. The weather source (pincode_store), the main_backend PIN
lookup, the LLM and TTS are replaced, so nothing goes to the network or AWS."""
from __future__ import annotations

import json
import os
from datetime import date

import pytest

import services.advisory.llm_advisory as llm_advisory
import services.flokiq_sync.client as flokiq_client
import services.pincode_store as pincode_store
import services.voice_agent.tts as tts
from services.farm_summary import build_farm_summary
from services.farm_summary.service import NO_WEATHER_POINT, count_animals, pending_vaccinations
from models import Animal, VaccinationRecord

TODAY = date(2026, 10, 26)
FARMER = "f-1"

# Same shape as pincode_store.get_pincode_data: "weather" is the
# get_weather_alert output (risk_level, summary, advisories, alerts with
# heat_stress_level, forecast_days with thi).
PINCODE_DATA = {
    "pin": "560001",
    "district": "Bengaluru",
    "state": "Karnataka",
    "weather": {
        "risk_level": "Medium",
        "summary": "Light rain",
        "advisories": ["Keep animals dry."],
        "alerts": [{"heat_stress_level": "low"}],
        "forecast_days": [{"thi": 70}],
    },
    "seasonal": None,
    "feed_market": {"commodities": []},
    "errors": [],
}


class Sources:
    """What the replaced weather source and main_backend lookup return,
    and what they were asked for."""

    def __init__(self):
        self.weather = PINCODE_DATA
        self.weather_calls: list[str] = []
        self.main_backend_pin = None
        self.main_backend_calls: list[str] = []

    def get_pincode_data(self, location, force_refresh=False, ttl_sec=None):
        self.weather_calls.append(location)
        if isinstance(self.weather, Exception):
            raise self.weather
        return self.weather

    def get_farm_pincode(self, farmer_id):
        self.main_backend_calls.append(farmer_id)
        if isinstance(self.main_backend_pin, Exception):
            raise self.main_backend_pin
        return self.main_backend_pin


@pytest.fixture(autouse=True)
def sources(monkeypatch):
    src = Sources()
    monkeypatch.setattr(pincode_store, "get_pincode_data", src.get_pincode_data)
    monkeypatch.setattr(flokiq_client, "get_farm_pincode", src.get_farm_pincode)
    return src


def _write(tmp_path, name, rows):
    (tmp_path / name).write_text(json.dumps(rows), encoding="utf-8")


def _seed(tmp_path, monkeypatch, pincode=560001, weather_location=""):
    monkeypatch.setenv("FARMER_CHAT_DATA_DIR", str(tmp_path))
    _write(tmp_path, "farmers.json", [
        {"id": FARMER, "name": "Ravi", "login_username": "ravi", "password_hash": "x", "weather_location": weather_location},
        {"id": "f-2", "name": "Other", "login_username": "other", "password_hash": "x"},
    ])
    _write(tmp_path, "farms.json", [{"id": "farm-1", "farmer_id": FARMER, "pincode": pincode}])
    _write(tmp_path, "animals.json", [
        {"id": "a1", "farmer_id": FARMER, "species": "Goat", "tag_or_name": "Gauri"},
        {"id": "a2", "farmer_id": FARMER, "species": "goat", "tag_or_name": "Moti"},
        {"id": "a3", "farmer_id": FARMER, "species": "sheep", "tag_or_name": "Bholu"},
        {"id": "a4", "farmer_id": FARMER, "species": "sheep", "tag_or_name": "Sold one", "status": "sold"},
        {"id": "b1", "farmer_id": "f-2", "species": "buffalo", "tag_or_name": "Not mine"},
    ])
    _write(tmp_path, "vaccination_records.json", [
        {"id": "v1", "farmer_id": FARMER, "animal_id": "a1", "vaccine_name": "PPR", "status": "pending", "due_date": "2026-10-20"},
        {"id": "v2", "farmer_id": FARMER, "animal_id": "a3", "vaccine_name": "FMD", "status": "pending", "due_date": "2026-11-02"},
        {"id": "v3", "farmer_id": FARMER, "animal_id": "a2", "vaccine_name": "PPR", "status": "administered", "administered_date": "2026-09-01"},
        {"id": "v4", "farmer_id": FARMER, "animal_id": "a4", "vaccine_name": "FMD", "status": "pending", "due_date": "2026-10-01"},
        {"id": "v5", "farmer_id": "f-2", "animal_id": "b1", "vaccine_name": "HS", "status": "pending", "due_date": "2026-10-01"},
    ])


def _llm_ok(calls):
    def fake(profile, livestock, weather, base_actions, language="en"):
        calls.append({"livestock": livestock, "weather": weather, "base_actions": list(base_actions), "language": language})
        return {"summary": "All fine.", "actions": ["Give PPR to Gauri."], "language": language}
    return fake


# --- facts ---

def test_counts_only_active_animals_per_species():
    animals = [
        Animal(id="1", farmer_id=FARMER, species="Goat", tag_or_name="a"),
        Animal(id="2", farmer_id=FARMER, species="goat ", tag_or_name="b"),
        Animal(id="3", farmer_id=FARMER, species="", tag_or_name="c"),
        Animal(id="4", farmer_id=FARMER, species="sheep", tag_or_name="d", status="dead"),
    ]
    assert count_animals(animals) == {
        "total": 3,
        "by_species": [{"species": "goat", "count": 2}, {"species": "unknown", "count": 1}],
    }


def test_count_animals_empty_farm():
    assert count_animals([]) == {"total": 0, "by_species": []}


def test_pending_vaccinations_order_overdue_and_missing_animal():
    animals = [Animal(id="a1", farmer_id=FARMER, species="goat", tag_or_name="Gauri")]
    records = [
        VaccinationRecord(id="r1", farmer_id=FARMER, animal_id="a1", vaccine_name="FMD", due_date="2026-11-01"),
        VaccinationRecord(id="r2", farmer_id=FARMER, animal_id="gone", vaccine_name="PPR", due_date="2026-10-01"),
        VaccinationRecord(id="r3", farmer_id=FARMER, animal_id="a1", vaccine_name="HS"),
        VaccinationRecord(id="r4", farmer_id=FARMER, animal_id="a1", vaccine_name="X", status="administered"),
    ]
    out = pending_vaccinations(records, animals, TODAY)
    assert out["pending_count"] == 3
    assert out["overdue_count"] == 1
    assert [i["record_id"] for i in out["items"]] == ["r2", "r1", "r3"]
    assert out["items"][0]["animal_name"] is None and out["items"][0]["overdue"] is True
    assert out["items"][2]["due_date"] is None and out["items"][2]["overdue"] is False


# --- full card ---

def test_full_summary_from_storage(tmp_path, monkeypatch, sources):
    _seed(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok(calls))

    out = build_farm_summary(FARMER, language="hi", today=TODAY)

    assert sources.weather_calls == ["560001"]
    assert out["weather"] == {
        "available": True, "location": "560001", "risk_level": "medium",
        "heat_level": "low", "summary": "Light rain", "stale": False,
    }
    assert out["animals"] == {"total": 3, "by_species": [{"species": "goat", "count": 2}, {"species": "sheep", "count": 1}]}
    vacc = out["vaccinations"]
    assert vacc["pending_count"] == 2 and vacc["overdue_count"] == 1
    assert [(i["animal_name"], i["vaccine_name"], i["overdue"]) for i in vacc["items"]] == [("Gauri", "PPR", True), ("Bholu", "FMD", False)]
    assert out["suggestion"] == {"summary": "All fine.", "actions": ["Give PPR to Gauri."], "language": "hi"}
    assert out["audio_base64"] is None
    assert out["errors"] == []
    # The LLM gets the facts: vaccination points first, then the rule-based weather advice.
    base = calls[0]["base_actions"]
    assert calls[0]["language"] == "hi"
    assert base[0].startswith("PPR vaccination for Gauri is pending (overdue since 2026-10-20)")
    assert "Keep animals dry." in base
    assert any("Review shelter drainage" in a for a in base)
    assert NO_WEATHER_POINT not in base
    assert calls[0]["weather"]["weather"]["summary"] == "Light rain"


def test_farmer_with_no_local_record_gets_an_empty_card(tmp_path, monkeypatch, sources):
    """The app sends main_backend's farmer id, which may not be in this
    service's storage. Like /chat/turn, that is served, not a 404: nothing
    recorded here, weather through the main_backend farm PIN."""
    _seed(tmp_path, monkeypatch)
    sources.main_backend_pin = "411001"
    calls = []
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok(calls))
    out = build_farm_summary("app-only-farmer", language="hi", today=TODAY)
    assert out["farmer_id"] == "app-only-farmer"
    assert out["animals"] == {"total": 0, "by_species": []}
    assert out["vaccinations"]["pending_count"] == 0 and out["vaccinations"]["items"] == []
    assert sources.main_backend_calls == ["app-only-farmer"] and sources.weather_calls == ["411001"]
    assert out["weather"]["available"] is True and out["errors"] == []
    # Another farmer's records never leak in.
    assert all("Gauri" not in a for a in calls[0]["base_actions"])


def test_unknown_language_falls_back_to_english(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok(calls))
    out = build_farm_summary(FARMER, language="fr-FR", today=TODAY)
    assert out["language"] == "en" and calls[0]["language"] == "en"


# --- where the weather comes from (same order as the chatbot's weather tool) ---

def test_saved_weather_location_comes_first(tmp_path, monkeypatch, sources):
    _seed(tmp_path, monkeypatch, pincode=560001, weather_location="Pune")
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))
    out = build_farm_summary(FARMER, today=TODAY)
    assert sources.weather_calls == ["Pune"] and sources.main_backend_calls == []
    assert out["weather"]["location"] == "Pune"


def test_main_backend_pin_when_nothing_saved_here(tmp_path, monkeypatch, sources):
    _seed(tmp_path, monkeypatch, pincode=None)
    sources.main_backend_pin = "411001"
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))
    out = build_farm_summary(FARMER, today=TODAY)
    assert sources.main_backend_calls == [FARMER] and sources.weather_calls == ["411001"]
    assert out["weather"]["available"] is True and out["errors"] == []


def test_no_location_skips_weather(tmp_path, monkeypatch, sources):
    _seed(tmp_path, monkeypatch, pincode=None)
    calls = []
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok(calls))
    out = build_farm_summary(FARMER, today=TODAY)
    assert sources.weather_calls == []
    assert out["errors"] == ["weather_no_location"] and out["weather"]["location"] is None
    assert NO_WEATHER_POINT in calls[0]["base_actions"]


def test_main_backend_lookup_error_counts_as_no_location(tmp_path, monkeypatch, sources):
    _seed(tmp_path, monkeypatch, pincode=None)
    sources.main_backend_pin = RuntimeError("main_backend down")
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))
    out = build_farm_summary(FARMER, today=TODAY)
    assert out["errors"] == ["weather_no_location"]
    assert out["animals"]["total"] == 3


# --- weather failures and details ---

def test_weather_fetch_failed_keeps_the_rest(tmp_path, monkeypatch, sources):
    _seed(tmp_path, monkeypatch)
    sources.weather = {**PINCODE_DATA, "weather": None, "errors": ["weather_alert: bad PIN"]}
    calls = []
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok(calls))
    out = build_farm_summary(FARMER, today=TODAY)
    assert out["errors"] == ["weather"]
    assert out["weather"]["available"] is False and out["weather"]["location"] == "560001"
    assert out["animals"]["total"] == 3 and out["vaccinations"]["pending_count"] == 2
    # The LLM is told there is no weather, so it can't call it "normal".
    assert calls[0]["weather"] == {} and calls[0]["base_actions"][-1] == NO_WEATHER_POINT


def test_weather_exception_keeps_the_rest(tmp_path, monkeypatch, sources):
    _seed(tmp_path, monkeypatch)
    sources.weather = ValueError("pin is required")
    calls = []
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok(calls))
    out = build_farm_summary(FARMER, today=TODAY)
    assert out["errors"] == ["weather"] and out["suggestion"] is not None
    assert NO_WEATHER_POINT in calls[0]["base_actions"]


def test_stale_weather_is_flagged(tmp_path, monkeypatch, sources):
    _seed(tmp_path, monkeypatch)
    sources.weather = {**PINCODE_DATA, "stale": True}
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))
    out = build_farm_summary(FARMER, today=TODAY)
    assert out["weather"]["available"] is True and out["weather"]["stale"] is True
    assert out["errors"] == []


def test_heat_level_from_weather_alerts(tmp_path, monkeypatch, sources):
    _seed(tmp_path, monkeypatch)
    hot = {**PINCODE_DATA["weather"], "alerts": [{"heat_stress_level": "high", "heat_stress_reason": "THI 82"}]}
    sources.weather = {**PINCODE_DATA, "weather": hot}
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))
    out = build_farm_summary(FARMER, today=TODAY)
    assert out["weather"]["heat_level"] == "high"


def test_shared_weather_data_is_not_changed(tmp_path, monkeypatch, sources):
    """pincode_store's data is cached and shared by all farmers."""
    _seed(tmp_path, monkeypatch)
    shared = json.loads(json.dumps(PINCODE_DATA))
    sources.weather = shared
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))
    build_farm_summary(FARMER, today=TODAY)
    assert shared == PINCODE_DATA


# --- AI suggestion and audio ---

def test_llm_failure_keeps_facts(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", lambda *a, **k: None)
    out = build_farm_summary(FARMER, include_audio=True, today=TODAY)
    assert out["suggestion"] is None and out["audio_base64"] is None
    assert out["errors"] == ["suggestion"]
    assert out["animals"]["total"] == 3


def test_llm_exception_keeps_facts(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("no AWS credentials")

    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", boom)
    out = build_farm_summary(FARMER, today=TODAY)
    assert out["errors"] == ["suggestion"] and out["vaccinations"]["pending_count"] == 2


def test_llm_kill_switch(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setenv("FARM_SUMMARY_LLM_ENABLED", "false")

    def must_not_run(*a, **k):
        raise AssertionError("LLM called while switched off")

    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", must_not_run)
    out = build_farm_summary(FARMER, today=TODAY)
    assert out["suggestion"] is None and out["errors"] == ["suggestion_disabled"]


def test_audio_only_when_asked(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))
    spoken = []
    monkeypatch.setattr(tts, "synthesize_speech", lambda text, target_lang=None: spoken.append((text, target_lang)) or (b"mp3", None))

    out = build_farm_summary(FARMER, language="ta", today=TODAY)
    assert out["audio_base64"] is None and spoken == []

    out = build_farm_summary(FARMER, language="ta", include_audio=True, today=TODAY)
    assert out["audio_base64"] == "bXAz"  # base64 of b"mp3"
    assert spoken == [("All fine. Give PPR to Gauri.", "ta")]
    assert out["errors"] == []


def test_audio_failure_keeps_suggestion(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))
    monkeypatch.setattr(tts, "synthesize_speech", lambda text, target_lang=None: (None, "polly down"))
    out = build_farm_summary(FARMER, include_audio=True, today=TODAY)
    assert out["suggestion"] is not None and out["audio_base64"] is None
    assert out["errors"] == ["audio"]


def test_audio_kill_switch(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setenv("FARM_SUMMARY_AUDIO_ENABLED", "off")
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))

    def must_not_run(*a, **k):
        raise AssertionError("TTS called while switched off")

    monkeypatch.setattr(tts, "synthesize_speech", must_not_run)
    out = build_farm_summary(FARMER, include_audio=True, today=TODAY)
    assert out["audio_base64"] is None and out["errors"] == ["audio_disabled"]


# --- API route (services/api_service/main.py) ---

SUMMARY_PATH = "/farmers/{farmer_id}/summary"


@pytest.fixture
def api_main(monkeypatch):
    """services/api_service/main.py runs validate_env() on import and exits if
    a required env var is missing. Fill only the missing ones with dummy
    values for this test (weather, LLM and TTS are replaced, so nothing
    reaches AWS); real values, if set, are left as they are."""
    from utils.env_check import REQUIRED_ENV

    for name in REQUIRED_ENV:
        if not os.getenv(name):
            monkeypatch.setenv(name, "ap-south-1" if name == "AWS_REGION" else "test-placeholder")
    from services.api_service import main
    return main


def test_summary_route_depends_on_require_api_key(api_main):
    routes = [r for r in api_main.app.routes if getattr(r, "path", None) == SUMMARY_PATH and "GET" in getattr(r, "methods", set())]
    assert len(routes) == 1
    assert any(dep.call is api_main.require_api_key for dep in routes[0].dependant.dependencies)


def test_summary_route_answers_for_a_farmer_with_no_local_record(tmp_path, monkeypatch, api_main):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))
    out = api_main.farm_summary("app-only-farmer", language="en", include_audio=False, _auth=None)
    assert out["farmer_id"] == "app-only-farmer" and out["animals"]["total"] == 0


def test_summary_route_returns_card(tmp_path, monkeypatch, api_main):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(llm_advisory, "generate_llm_advisory", _llm_ok([]))
    out = api_main.farm_summary(FARMER, language="mr", include_audio=False, _auth=None)
    assert out["language"] == "mr"
    assert out["weather"]["risk_level"] == "medium"
    assert out["animals"]["total"] == 3
    assert out["vaccinations"]["pending_count"] == 2
    assert out["errors"] == []
