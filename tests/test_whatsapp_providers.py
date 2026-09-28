"""Provider unit tests (Meta + Twilio signature verification, parse
shapes, and send_text wire format). Mocks requests.post at the boundary
so no test hits real network. Same pattern as test_freellmapi_adapter.py.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from types import SimpleNamespace

import pytest

from services.whatsapp_channel.config import WhatsAppChannelConfig
from services.whatsapp_channel.providers.meta import MetaProvider
from services.whatsapp_channel.providers.twilio import TwilioProvider


def _meta_cfg() -> WhatsAppChannelConfig:
    return WhatsAppChannelConfig(
        enabled=True,
        allowed_intents=frozenset({"query"}),
        default_language="en-IN",
        include_audio=False,
        max_reply_chars=4000,
        provider="meta",
        per_phone_per_min=6,
        per_phone_per_hour=100,
        enrollment_enabled=True,
        meta_phone_id="123456",
        meta_access_token="MOCK-TOKEN",
        meta_app_secret="mock-secret",
        meta_verify_token="verify-me",
    )


def _twilio_cfg() -> WhatsAppChannelConfig:
    return WhatsAppChannelConfig(
        enabled=True,
        allowed_intents=frozenset({"query"}),
        default_language="en-IN",
        include_audio=False,
        max_reply_chars=4000,
        provider="twilio",
        per_phone_per_min=6,
        per_phone_per_hour=100,
        enrollment_enabled=True,
        twilio_account_sid="AC-mock",
        twilio_auth_token="tok-secret",
        twilio_whatsapp_from="whatsapp:+14155238886",
    )


def _mock_response(payload=None, status=200):
    return SimpleNamespace(
        raise_for_status=lambda: None if 200 <= status < 300 else (_ for _ in ()).throw(RuntimeError(f"HTTP {status}")),
        status_code=status,
        json=lambda: payload or {},
        content=b"",
    )


# ---- Meta ----------------------------------------------------------------


def test_meta_verify_signature_accepts_valid_hmac_rejects_forged():
    provider = MetaProvider(_meta_cfg())
    body = b'{"hello":"world"}'
    expected = hmac.new(b"mock-secret", body, hashlib.sha256).hexdigest()

    assert provider.verify_signature(body, {"X-Hub-Signature-256": f"sha256={expected}"}) is True
    assert provider.verify_signature(body, {"X-Hub-Signature-256": "sha256=deadbeef"}) is False
    assert provider.verify_signature(body, {}) is False, "no header -> reject"
    assert provider.verify_signature(body, {"X-Hub-Signature-256": expected}) is False, "no sha256= prefix -> reject"


def test_meta_parse_inbound_extracts_text_message():
    provider = MetaProvider(_meta_cfg())
    payload = {
        "entry": [{"changes": [{"value": {"messages": [
            {"from": "919876543210", "id": "wamid.xyz", "timestamp": "1700000000",
             "text": {"body": "how many animals do I have"}},
        ]}}]}]
    }
    messages = provider.parse_inbound(payload)
    assert len(messages) == 1
    assert messages[0].from_phone == "919876543210"
    assert messages[0].text == "how many animals do I have"
    assert messages[0].id == "wamid.xyz"
    assert messages[0].ts == 1700000000.0
    assert messages[0].media_type is None


def test_meta_parse_inbound_extracts_audio_message():
    provider = MetaProvider(_meta_cfg())
    payload = {
        "entry": [{"changes": [{"value": {"messages": [
            {"from": "919876543210", "id": "wamid.aud", "audio": {"id": "media-abc"}},
        ]}}]}]
    }
    messages = provider.parse_inbound(payload)
    assert len(messages) == 1
    assert messages[0].media_type == "audio"
    assert messages[0].media_id_or_url == "media-abc"


def test_meta_parse_inbound_ignores_status_events():
    """Status callbacks (delivery/read receipts) have no `messages` key --
    must return an empty list so we still 200 without doing anything."""
    provider = MetaProvider(_meta_cfg())
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.x", "status": "read"}]}}]}]}
    assert provider.parse_inbound(payload) == []


def test_meta_send_text_wire_format(monkeypatch):
    provider = MetaProvider(_meta_cfg())
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _mock_response(payload={"messages": [{"id": "wamid.sent"}]})

    monkeypatch.setattr("services.whatsapp_channel.providers.meta.requests.post", fake_post)
    provider.send_text("+919876543210", "hello world")
    assert captured["url"].endswith("/123456/messages"), "phone ID from config baked into URL"
    assert captured["headers"]["Authorization"] == "Bearer MOCK-TOKEN"
    assert captured["json"] == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "+919876543210",
        "type": "text",
        "text": {"body": "hello world"},
    }


def test_meta_constructor_requires_secrets():
    with pytest.raises(ValueError, match="WHATSAPP_META_PHONE_ID"):
        MetaProvider(WhatsAppChannelConfig(
            enabled=True, allowed_intents=frozenset(), default_language="en-IN",
            include_audio=False, max_reply_chars=4000, provider="meta",
            per_phone_per_min=6, per_phone_per_hour=100, enrollment_enabled=True,
        ))


# ---- Twilio ----------------------------------------------------------------


def test_twilio_verify_signature_accepts_valid_hmac_sha1_rejects_forged():
    provider = TwilioProvider(_twilio_cfg())
    url = "https://api.example.com/whatsapp/webhook"
    form_params = {"From": "whatsapp:+919876543210", "Body": "hi", "MessageSid": "SM123"}
    canonical = url + "".join(f"{k}{form_params[k]}" for k in sorted(form_params))
    expected = base64.b64encode(
        hmac.new(b"tok-secret", canonical.encode("utf-8"), hashlib.sha1).digest()
    ).decode("ascii")
    headers_ok = {
        "X-Twilio-Signature": expected,
        "X-Twilio-Full-Url": url,
        "_twilio_form_params": form_params,
    }
    assert provider.verify_signature(b"ignored-for-twilio", headers_ok) is True

    headers_forged = {**headers_ok, "X-Twilio-Signature": "wrongsignature=="}
    assert provider.verify_signature(b"ignored", headers_forged) is False

    assert provider.verify_signature(b"", {}) is False, "no headers -> reject"


def test_twilio_parse_inbound_single_form_message():
    provider = TwilioProvider(_twilio_cfg())
    body = {
        "From": "whatsapp:+919876543210",
        "Body": "book a vet visit",
        "MessageSid": "SM123",
        "NumMedia": "0",
    }
    messages = provider.parse_inbound(body)
    assert len(messages) == 1
    assert messages[0].from_phone == "whatsapp:+919876543210"
    assert messages[0].text == "book a vet visit"
    assert messages[0].id == "SM123"
    assert messages[0].media_type is None


def test_twilio_send_text_wire_format(monkeypatch):
    provider = TwilioProvider(_twilio_cfg())
    captured = {}

    def fake_post(url, auth, data, timeout):
        captured["url"] = url
        captured["auth"] = auth
        captured["data"] = data
        return _mock_response()

    monkeypatch.setattr("services.whatsapp_channel.providers.twilio.requests.post", fake_post)
    provider.send_text("+919876543210", "hi")
    assert captured["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC-mock/Messages.json"
    assert captured["auth"] == ("AC-mock", "tok-secret")
    assert captured["data"]["From"] == "whatsapp:+14155238886"
    assert captured["data"]["To"] == "whatsapp:+919876543210", (
        "auto-prepend 'whatsapp:' if the caller passed a bare number"
    )
    assert captured["data"]["Body"] == "hi"
