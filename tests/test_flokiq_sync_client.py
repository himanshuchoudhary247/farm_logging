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


@pytest.fixture
def health_on(on, monkeypatch):
    monkeypatch.setenv("FLOKIQ_SYNC_HEALTH_LOGS", "true")


def test_health_log_demo_farmer_id_is_skipped(health_on, monkeypatch):
    calls = _capture(monkeypatch, _Resp(201, {"log_id": "h-1"}))
    assert client.create_health_log("f-001", "411001", ["fever"]) is None
    assert calls == []


ANIMAL = "11111111-1111-1111-1111-111111111111"


def test_health_log_sends_json_to_internal_route_with_key(health_on, monkeypatch):
    calls = _capture(monkeypatch, _Resp(201, {"log_id": "h-1"}))
    result = client.create_health_log(
        FARMER, "411001", ["fever", "not eating"],
        animal_id=ANIMAL, risk_level="Medium",
        ai_diagnosis_suggestion="Could be a sign of mastitis.",
        potential_ailments=["mastitis"], first_aid_advice="Keep hydrated.",
    )
    assert result == {"log_id": "h-1"}
    call = calls[0]
    assert call["url"] == "https://backend.test/v1/internal/health-logs"
    assert call["headers"] == {"X-Internal-Api-Key": "secret-key"}
    assert call["json"] == {
        "farmerId": FARMER,
        "pincode": "411001",
        "symptomsReported": ["fever", "not eating"],
        "animalId": ANIMAL,
        "riskLevel": "Medium",
        "aiDiagnosisSuggestion": "Could be a sign of mastitis.",
        "potentialAilments": ["mastitis"],
        "firstAidAdvice": "Keep hydrated.",
    }


def test_health_log_non_uuid_animal_id_is_omitted_not_fatal(health_on, monkeypatch):
    """Real bug, review-found: animals registered through Chocolate have
    local, non-UUID ids (e.g. "MLTEST03"). main_backend requires animalId
    to be a UUID -- sending one of those would 400 the ENTIRE log,
    dropping real symptoms/AI-diagnosis data over an optional field. The
    log must still go through, just without the animal link."""
    calls = _capture(monkeypatch, _Resp(201, {"log_id": "h-1"}))
    result = client.create_health_log(FARMER, "411001", ["fever"], animal_id="MLTEST03")
    assert result == {"log_id": "h-1"}
    assert "animalId" not in calls[0]["json"]


def test_health_log_non_pin_pincode_skips_the_call(health_on, monkeypatch):
    """Real bug, review-found: pincode here can be values["weather_location"],
    which is sometimes a place name ("Pune") rather than a 6-digit PIN.
    pincode is NOT NULL on main_backend -- sending a place name would
    400, so it must be treated the same as a missing pincode (skip)."""
    calls = _capture(monkeypatch, _Resp(201, {"log_id": "h-1"}))
    assert client.create_health_log(FARMER, "Pune", ["fever"]) is None
    assert calls == []


def test_health_log_risk_level_is_normalized_to_main_backends_casing(health_on, monkeypatch):
    """risk_level comes from an LLM; main_backend only accepts the exact
    casing Low/Medium/High."""
    calls = _capture(monkeypatch, _Resp(201, {"log_id": "h-1"}))
    client.create_health_log(FARMER, "411001", ["fever"], risk_level="low")
    assert calls[0]["json"]["riskLevel"] == "Low"


def test_health_log_unrecognized_risk_level_is_omitted(health_on, monkeypatch):
    calls = _capture(monkeypatch, _Resp(201, {"log_id": "h-1"}))
    client.create_health_log(FARMER, "411001", ["fever"], risk_level="critical")
    assert "riskLevel" not in calls[0]["json"]


def test_health_log_missing_key_makes_no_call(health_on, monkeypatch):
    monkeypatch.delenv("FLOKIQ_INTERNAL_API_KEY")
    calls = _capture(monkeypatch, _Resp(201, {"log_id": "h-1"}))
    assert client.create_health_log(FARMER, "411001", ["fever"]) is None
    assert calls == []


def test_health_log_http_error_returns_none(health_on, monkeypatch):
    _capture(monkeypatch, _Resp(400, None, '{"message":"bad"}'))
    assert client.create_health_log(FARMER, "411001", ["fever"]) is None


def test_notes_name_the_animal_and_issue():
    values = {"animal_name": "GAURI", "species": "goat", "issue": "not eating", "miscellaneous_notes": "since yesterday"}
    assert client.build_appointment_notes(values) == "GAURI (goat): not eating. since yesterday. Booked via Chocolate."


def test_notes_fall_back_to_symptoms():
    values = {"animal_name": "LAKSHMI", "symptoms": ["fever", "loose stool"]}
    assert client.build_appointment_notes(values) == "LAKSHMI: fever, loose stool. Booked via Chocolate."


def test_notes_are_capped():
    assert len(client.build_appointment_notes({"issue": "x" * 5000})) == 1000
    