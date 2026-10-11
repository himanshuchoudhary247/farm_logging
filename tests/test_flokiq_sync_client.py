"""flokiq_sync client: sends bookings to main_backend's internal route,
stays off unless configured, never raises, and writes a useful note."""
import pytest

from services.flokiq_sync import client

FARMER = "9e95446d-c317-4074-b698-c8cc35325de6"


class _Resp:
    def __init__(self, status=201, body=None, text=""):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("FLOKIQ_SYNC_ENABLED", "true")
    monkeypatch.setenv("FLOKIQ_API_BASE_URL", "https://backend.test/v1/")
    monkeypatch.setenv("FLOKIQ_INTERNAL_API_KEY", "secret-key")
    monkeypatch.delenv("FLOKIQ_SYNC_HEALTH_LOGS", raising=False)


def _capture(monkeypatch, resp):
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return resp

    monkeypatch.setattr(client.requests, "post", fake_post)
    return calls


def test_off_by_default_makes_no_call(monkeypatch):
    monkeypatch.delenv("FLOKIQ_SYNC_ENABLED", raising=False)
    calls = _capture(monkeypatch, _Resp())
    assert client.create_appointment(FARMER, "2026-10-05", "17:00") is None
    assert calls == []


def test_missing_key_makes_no_call(on, monkeypatch):
    monkeypatch.delenv("FLOKIQ_INTERNAL_API_KEY")
    calls = _capture(monkeypatch, _Resp())
    assert client.create_appointment(FARMER, "2026-10-05", "17:00") is None
    assert calls == []


def test_demo_farmer_id_is_skipped(on, monkeypatch):
    calls = _capture(monkeypatch, _Resp())
    assert client.create_appointment("f-001", "2026-10-05", "17:00") is None
    assert calls == []


def test_sends_json_to_internal_route_with_key(on, monkeypatch):
    calls = _capture(monkeypatch, _Resp(201, {"id": "a-1"}))
    result = client.create_appointment(FARMER, "2026-10-05", "17:00", notes="GAURI (goat): not eating.")
    assert result == {"id": "a-1"}
    call = calls[0]
    assert call["url"] == "https://backend.test/v1/internal/appointments"
    assert call["headers"] == {"X-Internal-Api-Key": "secret-key"}
    assert call["json"] == {"farmerId": FARMER, "date": "2026-10-05", "time": "17:00", "notes": "GAURI (goat): not eating."}
    assert "doctorId" not in call["json"] and "addedByUserId" not in call["json"]


def test_existing_appointment_200_is_success(on, monkeypatch):
    _capture(monkeypatch, _Resp(200, {"id": "a-1"}))
    assert client.create_appointment(FARMER, "2026-10-05", "17:00") == {"id": "a-1"}


def test_http_error_returns_none(on, monkeypatch):
    _capture(monkeypatch, _Resp(400, None, '{"message":"bad"}'))
    assert client.create_appointment(FARMER, "2026-10-05", "17:00") is None


def test_network_error_returns_none(on, monkeypatch):
    def boom(url, **kwargs):
        raise client.requests.ConnectionError("down")

    monkeypatch.setattr(client.requests, "post", boom)
    assert client.create_appointment(FARMER, "2026-10-05", "17:00") is None


def test_health_log_sync_is_off_by_default(on, monkeypatch):
    calls = _capture(monkeypatch, _Resp(201, {"log_id": "h-1"}))
    assert client.create_health_log(FARMER, "411001", ["fever"]) is None
    assert calls == []


def test_notes_name_the_animal_and_issue():
    values = {"animal_name": "GAURI", "species": "goat", "issue": "not eating", "miscellaneous_notes": "since yesterday"}
    assert client.build_appointment_notes(values) == "GAURI (goat): not eating. since yesterday. Booked via Chocolate."


def test_notes_fall_back_to_symptoms():
    values = {"animal_name": "LAKSHMI", "symptoms": ["fever", "loose stool"]}
    assert client.build_appointment_notes(values) == "LAKSHMI: fever, loose stool. Booked via Chocolate."


def test_notes_are_capped():
    assert len(client.build_appointment_notes({"issue": "x" * 5000})) == 1000
    