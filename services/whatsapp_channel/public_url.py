"""Public webhook URL for Twilio signature verification.

Kept outside api_service/main.py so it can be imported and tested without
main.py's import-time environment check."""
from __future__ import annotations

import os

from starlette.requests import Request


def twilio_public_url(request: Request) -> str:
    """The URL Twilio signed. Behind ALB/nginx/Cloudflare, request.url is
    the INTERNAL url (e.g. http://10.0.0.5:8001/whatsapp/webhook) while
    Twilio signs the PUBLIC url it POSTed to, so using request.url made
    every inbound fail signature verification (403). Order:
    WHATSAPP_PUBLIC_URL (the exact public webhook URL, most reliable) ->
    X-Forwarded-Proto / X-Forwarded-Host set by the proxy -> request.url
    (direct, no proxy)."""
    query = request.url.query
    configured = os.getenv("WHATSAPP_PUBLIC_URL", "").strip()
    if configured:
        return f"{configured}?{query}" if query else configured
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    if proto or host:
        return str(request.url.replace(
            scheme=proto or request.url.scheme,
            netloc=host or request.url.netloc,
        ))
    return str(request.url)
