"""LLM advisory: livestock summary, prompt contents, reply validation,
fallback to None on any failure, and reuse of identical requests."""
from datetime import date
from types import SimpleNamespace

import pytest

from services.advisory import llm_advisory as adv

TODAY = date(2026, 10, 2)


def _animal(species, breed="", sex="", age=None, birth=None, status="active"):
    return SimpleNamespace(species=species, breed=breed, sex=sex, age_years=age, birth_date=birth, status=status)


class _FakeAdapter:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def complete(self, messages, system=None):
        self.calls.append(messages[0]["content"])
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture(autouse=True)
def _clear():
    adv.clear_cache_for_tests()
    yield
    adv.clear_cache_for_tests()


def _use(monkeypatch, adapter):
    monkeypatch.setattr(adv, "_make_adapter", lambda: adapter)
    return adapter


PROFILE = {"farmer_id": "f-1", "name": "Ramu", "current_issues": ["Foot rot in flock"]}
WEATHER = {"weather": {"summary": "Heavy rain tomorrow", "risk_level": "high", "advisories": ["Move animals under cover"]}}
GOOD = '{"summary": "Heavy rain tomorrow.", "actions": ["Keep goats in the shed.", "Check hooves daily."]}'


def test_summary_counts_only_active_animals():
    animals = [
        _animal("Goat", "Osmanabadi", "female", age=0.5),
        _animal("goat", "Osmanabadi", "male", age=3),
        _animal("goat", "Sirohi", "female", birth="2026-06-01"),
        _animal("goat", status="sold"),
        _animal("sheep", "Deccani", "female", age=2),
    ]
    summary = adv.summarize_livestock(animals, today=TODAY)
    goat = summary[0]
    assert goat["type"] == "goat" and goat["count"] == 3
    assert goat["breeds"] == {"Osmanabadi": 2, "Sirohi": 1}
    assert goat["female"] == 2 and goat["male"] == 1
    assert goat["under_1_year"] == 2
    assert summary[1]["type"] == "sheep"


def test_prompt_has_farm_issues_weather_and_rules(monkeypatch):
    fake = _use(monkeypatch, _FakeAdapter(reply=GOOD))
    livestock = [{"type": "goat", "count": 12, "under_1_year": 3}]
    adv.generate_llm_advisory(PROFILE, livestock, WEATHER, ["Inspect hoof health daily."], language="hi")
    prompt = fake.calls[0]
    assert '"count": 12' in prompt
    assert "Foot rot in flock" in prompt
    assert "Heavy rain tomorrow" in prompt
    assert "Inspect hoof health daily." in prompt
    assert "Write in Hindi" in prompt
    assert "Never name medicines" in prompt


def test_good_reply_is_returned(monkeypatch):
    _use(monkeypatch, _FakeAdapter(reply="```json\n" + GOOD + "\n```"))
    result = adv.generate_llm_advisory(PROFILE, [], WEATHER, [], language="en-IN")
    assert result == {"summary": "Heavy rain tomorrow.", "actions": ["Keep goats in the shed.", "Check hooves daily."], "language": "en"}


def test_too_many_actions_are_cut(monkeypatch):
    many = '{"summary": "s", "actions": ["a1", "a2", "a3", "a4", "a5", "a6", "a7"]}'
    _use(monkeypatch, _FakeAdapter(reply=many))
    assert len(adv.generate_llm_advisory(PROFILE, [], WEATHER, [])["actions"]) == 5


@pytest.mark.parametrize("reply", ["not json", '{"summary": ""}', '{"summary": "s", "actions": []}', ""])
def test_bad_reply_returns_none(monkeypatch, reply):
    _use(monkeypatch, _FakeAdapter(reply=reply))
    assert adv.generate_llm_advisory(PROFILE, [], WEATHER, []) is None


def test_llm_error_returns_none(monkeypatch):
    _use(monkeypatch, _FakeAdapter(error=RuntimeError("timeout")))
    assert adv.generate_llm_advisory(PROFILE, [], WEATHER, []) is None


def test_same_request_reuses_saved_advice(monkeypatch):
    fake = _use(monkeypatch, _FakeAdapter(reply=GOOD))
    adv.generate_llm_advisory(PROFILE, [], WEATHER, [])
    adv.generate_llm_advisory(PROFILE, [], WEATHER, [])
    assert len(fake.calls) == 1


def test_changed_weather_asks_again(monkeypatch):
    fake = _use(monkeypatch, _FakeAdapter(reply=GOOD))
    adv.generate_llm_advisory(PROFILE, [], WEATHER, [])
    adv.generate_llm_advisory(PROFILE, [], {"weather": {"summary": "Clear sky", "risk_level": "low"}}, [])
    assert len(fake.calls) == 2


def test_works_with_pincode_store_weather_shape(monkeypatch):
    fake = _use(monkeypatch, _FakeAdapter(reply=GOOD))
    data = {"weather": {"summary": "Hot", "risk_level": "medium", "alerts": [{"type": "heat"}], "forecast_days": [1, 2, 3, 4]}}
    adv.generate_llm_advisory(PROFILE, [], data, [])
    assert '"alerts"' in fake.calls[0] and '"forecast_days": [1, 2, 3]' in fake.calls[0]


def test_unknown_language_falls_back_to_english(monkeypatch):
    fake = _use(monkeypatch, _FakeAdapter(reply=GOOD))
    assert adv.generate_llm_advisory(PROFILE, [], WEATHER, [], language="xx")["language"] == "en"
    assert "Write in English" in fake.calls[0]
    