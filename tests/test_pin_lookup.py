"""Local PIN table: used for known PINs, falls back to Nominatim otherwise,
and never breaks weather when the file is missing or turned off."""
from pathlib import Path

import pytest

from services.weather_alert import pin_lookup, service


@pytest.fixture
def no_cache(monkeypatch):
    monkeypatch.setattr(service, "_cache_get", lambda key: None)
    monkeypatch.setattr(service, "_cache_set", lambda key, value: None)


def _no_nominatim(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Nominatim must not be called for a PIN in the table")
    monkeypatch.setattr(service, "_request_json", fail)


def _fake_nominatim(monkeypatch, calls):
    def fake(url, params=None, headers=None, **kwargs):
        calls.append(params)
        return [{"lat": "21.0", "lon": "75.0", "display_name": "Somewhere, Some District, Maharashtra, India"}]
    monkeypatch.setattr(service, "_request_json", fake)


def test_known_pin_uses_table_not_nominatim(monkeypatch, no_cache):
    _no_nominatim(monkeypatch)
    loc = service.resolve_location("411001")
    assert loc.display_name.startswith("411001, ")
    assert service._parse_state(loc.display_name) == "Maharashtra"
    assert service._parse_district(loc.display_name) == "Pune"
    assert 18.3 < loc.lat < 18.7 and 73.7 < loc.lon < 74.1


def test_pin_missing_from_nominatim_now_resolves(monkeypatch, no_cache):
    # 471111 is not in Nominatim (India); it used to resolve to Turkey.
    _no_nominatim(monkeypatch)
    loc = service.resolve_location("471111")
    assert service._parse_state(loc.display_name) == "Madhya Pradesh"


def test_unknown_pin_falls_back_to_nominatim(monkeypatch, no_cache):
    monkeypatch.setattr(pin_lookup, "_table", {})
    calls = []
    _fake_nominatim(monkeypatch, calls)
    service.resolve_location("999999")
    assert calls and calls[0]["q"] == "999999"


def test_place_name_never_uses_table(monkeypatch, no_cache):
    calls = []
    _fake_nominatim(monkeypatch, calls)
    service.resolve_location("Pune")
    assert calls and calls[0]["q"] == "Pune"


def test_switch_off_uses_nominatim(monkeypatch, no_cache):
    monkeypatch.setenv("PIN_LOOKUP_LOCAL", "0")
    calls = []
    _fake_nominatim(monkeypatch, calls)
    service.resolve_location("411001")
    assert calls and calls[0]["q"] == "411001"


def test_missing_file_falls_back_without_error(monkeypatch, no_cache, tmp_path):
    monkeypatch.setattr(pin_lookup, "_DATA_PATH", tmp_path / "missing.csv")
    monkeypatch.setattr(pin_lookup, "_table", None)
    calls = []
    _fake_nominatim(monkeypatch, calls)
    service.resolve_location("411001")
    assert calls


def test_bad_rows_are_skipped(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text(
        "pin,office,district,state,lat,lon\n"
        "411001,Pune,Pune,Maharashtra,18.5,73.8\n"
        "411002,Bad,Pune,Maharashtra,not-a-number,73.8\n",
        encoding="utf-8",
    )
    table = pin_lookup._load(path)
    assert set(table) == {"411001"}


def test_shipped_table_is_sane():
    table = pin_lookup._load(pin_lookup._DATA_PATH)
    assert len(table) > 18000
    for place in table.values():
        assert len(place.pin) == 6 and place.pin.isdigit()
        assert 6 <= place.lat <= 37.5 and 68 <= place.lon <= 97.5
        assert place.state and place.district

        