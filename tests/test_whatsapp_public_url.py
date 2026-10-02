"""Twilio signs the PUBLIC webhook URL, so the URL used for signature
verification must be the public one even when running behind a proxy."""
from starlette.requests import Request

from services.whatsapp_channel.public_url import twilio_public_url as _twilio_public_url


def _request(headers=None, query=b""):
    scope = {
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "server": ("10.0.0.5", 8001),
        "path": "/whatsapp/webhook",
        "query_string": query,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


def test_no_proxy_uses_request_url(monkeypatch):
    monkeypatch.delenv("WHATSAPP_PUBLIC_URL", raising=False)
    assert _twilio_public_url(_request()) == "http://10.0.0.5:8001/whatsapp/webhook"


def test_forwarded_headers_give_public_url(monkeypatch):
    monkeypatch.delenv("WHATSAPP_PUBLIC_URL", raising=False)
    req = _request({"X-Forwarded-Proto": "https", "X-Forwarded-Host": "api.flokiq.com"})
    assert _twilio_public_url(req) == "https://api.flokiq.com/whatsapp/webhook"


def test_configured_public_url_wins(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PUBLIC_URL", "https://api.flokiq.com/whatsapp/webhook")
    req = _request({"X-Forwarded-Proto": "http", "X-Forwarded-Host": "internal"}, query=b"a=1")
    assert _twilio_public_url(req) == "https://api.flokiq.com/whatsapp/webhook?a=1"
    