from services.weather_alert import service


def _fake_geocoder(seen):
    def fake_request_json(url, params=None, headers=None, **kwargs):
        seen.update(params or {})
        return [{"lat": "18.5", "lon": "73.8", "display_name": "411001, Pune, Maharashtra, India"}]
    return fake_request_json


def _no_cache(monkeypatch):
    monkeypatch.setattr(service, "_cache_get", lambda key: None)
    monkeypatch.setattr(service, "_cache_set", lambda key, value: None)


def test_pin_search_is_limited_to_india(monkeypatch):
    # This test is about the Nominatim request. 471111 is in the local PIN
    # table, which would answer first, so turn the table off.
    monkeypatch.setenv("PIN_LOOKUP_LOCAL", "0")
    seen = {}
    monkeypatch.setattr(service, "_request_json", _fake_geocoder(seen))
    _no_cache(monkeypatch)
    service.resolve_location("471111")
    assert seen["countrycodes"] == "in"
    assert seen["q"] == "471111"


def test_place_name_search_is_limited_to_india(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "_request_json", _fake_geocoder(seen))
    _no_cache(monkeypatch)
    service.resolve_location("Pune")
    assert seen["countrycodes"] == "in"

def test_place_name_result_skips_postcode():
    name = "Pune, Pune City Subdistrict, Pune, Maharashtra, 411001, India"
    assert service._parse_state(name) == "Maharashtra"
    assert service._parse_district(name) == "Pune"


def test_pin_result_unchanged():
    name = "411001, Pune City Subdistrict, Pune, Maharashtra, India"
    assert service._parse_state(name) == "Maharashtra"
    assert service._parse_district(name) == "Pune"
    