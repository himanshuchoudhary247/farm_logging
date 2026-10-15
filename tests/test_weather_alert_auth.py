"""Auth gate on POST /weather/alert (whole-dev-branch cache-planning work):
a new scheduled caller (main_backend's weather-cache cron) will hit this
route automatically every 4 hours, unlike today's human-triggered chatbot
turns -- an automated, unauthenticated caller is a different risk, so the
route now depends on the existing require_api_key gate.

services.api_service.main calls validate_env() at import time, which
sys.exit(1)s if AWS creds are not set -- no test file imports it today.
These tests set fake AWS/VOICE_BUCKET env vars via monkeypatch before the
first import, so the module loads the same way whether this suite is run
with or without real AWS credentials in the outer environment."""
from __future__ import annotations

import pytest
from fastapi import HTTPException


@pytest.fixture
def main_module(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setenv("VOICE_BUCKET", "test-bucket")
    from services.api_service import main
    return main


def test_wrong_key_is_rejected(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "_API_KEY", "secret-123")
    with pytest.raises(HTTPException) as exc_info:
        main_module.require_api_key(x_api_key="wrong")
    assert exc_info.value.status_code == 401


def test_missing_key_is_rejected(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "_API_KEY", "secret-123")
    with pytest.raises(HTTPException) as exc_info:
        main_module.require_api_key(x_api_key="")
    assert exc_info.value.status_code == 401


def test_correct_key_is_accepted(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "_API_KEY", "secret-123")
    assert main_module.require_api_key(x_api_key="secret-123") is None


def test_gate_is_inert_when_key_unset(main_module, monkeypatch):
    """Matches every other require_api_key route's existing behavior:
    unset FARMER_CHAT_API_KEY means local dev stays unauthenticated."""
    monkeypatch.setattr(main_module, "_API_KEY", "")
    assert main_module.require_api_key(x_api_key="") is None
    assert main_module.require_api_key(x_api_key="anything") is None


def test_weather_alert_route_depends_on_require_api_key(main_module):
    """The route itself must declare the dependency -- a regression here
    (the dependency silently dropped from the signature) would leave the
    endpoint open again without any of the above tests catching it."""
    import inspect

    sig = inspect.signature(main_module.weather_alert)
    auth_param = sig.parameters["_auth"]
    depends = auth_param.default
    assert depends.dependency is main_module.require_api_key
