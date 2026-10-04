"""Twilio WhatsApp provider -- WORKING SKELETON.

Ships with `verify_signature` and `send_text` implemented against
Twilio's real APIs. `download_media` is stubbed (raises
NotImplementedError) since the current project scope covers Meta as the
primary provider; a later engineer can fill it in without redesign.
`parse_inbound` handles Twilio's form-encoded webhook shape (single
message per POST -- Twilio doesn't batch like Meta does).

Reference: https://www.twilio.com/docs/whatsapp/api

Setup:
1. Sign up for a Twilio account, get an Account SID and Auth Token, and
   a WhatsApp-enabled number (sandbox is fine for dev).
2. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM (like
   `whatsapp:+14155238886` for the shared sandbox number).
3. Point Twilio's webhook config at `https://<your-host>/whatsapp/webhook`
   with method POST.

Twilio delivers inbound messages as form-encoded (not JSON), so the
webhook handler must forward the parsed form fields as `body` to
parse_inbound; see main.py::whatsapp_webhook.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Any, List

import requests

from services.whatsapp_channel.providers.base import (
    InboundMessage,
    WhatsAppProvider,
)


_log = logging.getLogger("whatsapp_channel.twilio")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)


class TwilioProvider(WhatsAppProvider):
    def __init__(self, config: Any) -> None:
        self.config = config
        if not config.twilio_account_sid:
            raise ValueError("TWILIO_ACCOUNT_SID is required for provider=twilio")
        if not config.twilio_auth_token:
            raise ValueError("TWILIO_AUTH_TOKEN is required for provider=twilio")
        if not config.twilio_whatsapp_from:
            raise ValueError("TWILIO_WHATSAPP_FROM is required for provider=twilio")
        self._sid = config.twilio_account_sid
        self._token = config.twilio_auth_token
        self._from = config.twilio_whatsapp_from

    def verify_signature(self, body: bytes, headers: dict) -> bool:
        """Twilio's signature scheme (HMAC-SHA1, base64) is:
            HMAC-SHA1(auth_token, request_url + sorted(param+value concatenated))
        The canonical URL is the FULL public URL Twilio POSTed to,
        including query string. The router / webhook handler must pass
        both the URL (via headers['X-Forwarded-Url'] or reconstructed
        from the request) and the parsed form params (via
        headers['_twilio_form_params'] as a dict). If those aren't
        passed we can't verify and MUST fail closed.

        Reference:
        https://www.twilio.com/docs/usage/webhooks/webhooks-security
        """
        provided = headers.get("X-Twilio-Signature") or headers.get("x-twilio-signature") or ""
        url = headers.get("X-Twilio-Full-Url") or headers.get("x-twilio-full-url") or ""
        form = headers.get("_twilio_form_params") or {}
        if not provided or not url:
            return False
        # Twilio's canonical string: URL + sorted(k+v for each param).
        parts = [url]
        for key in sorted(form.keys()):
            parts.append(f"{key}{form[key]}")
        canonical = "".join(parts).encode("utf-8")
        digest = hmac.new(self._token.encode("utf-8"), canonical, hashlib.sha1).digest()
        expected = base64.b64encode(digest).decode("ascii")
        try:
            return hmac.compare_digest(provided, expected)
        except (TypeError, ValueError):
            return False

    def parse_inbound(self, body: dict) -> List[InboundMessage]:
        """Twilio delivers each message as a single POST with form fields
        `From` (like `whatsapp:+91XXX`), `Body`, `MessageSid`,
        `NumMedia`, `MediaUrl0..N`, `MediaContentType0..N`. No batching."""
        if not isinstance(body, dict):
            return []
        from_val = str(body.get("From") or "")
        if not from_val:
            return []
        text_val = str(body.get("Body") or "")
        message_id = str(body.get("MessageSid") or f"twilio-{time.time_ns()}")
        media_type = None
        media_url = None
        try:
            num_media = int(body.get("NumMedia") or 0)
        except (TypeError, ValueError):
            num_media = 0
        if num_media > 0:
            media_url = str(body.get("MediaUrl0") or "") or None
            content_type = str(body.get("MediaContentType0") or "").lower()
            if content_type.startswith("audio/"):
                media_type = "audio"
            elif content_type.startswith("image/"):
                media_type = "image"
            elif content_type.startswith("video/"):
                media_type = "video"
        return [InboundMessage(
            from_phone=from_val,
            text=text_val,
            id=message_id,
            ts=None,
            media_type=media_type,
            media_id_or_url=media_url,
            raw=dict(body),
        )]

    def send_text(self, to_phone: str, text: str) -> None:
        """POST to Twilio's Messages resource with basic auth. Raises on
        any non-2xx -- same semantics as MetaProvider.send_text."""
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._sid}/Messages.json"
        data = {
            "From": self._from,
            "To": to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}",
            "Body": text,
        }
        t0 = time.time()
        resp = requests.post(url, auth=(self._sid, self._token), data=data, timeout=15)
        _log.info(
            "twilio send_text to=%s status=%d ms=%.0f len=%d",
            to_phone, resp.status_code, (time.time() - t0) * 1000, len(text),
        )
        resp.raise_for_status()

    # download_media / send_audio inherit the base's NotImplementedError
    # -- Twilio's media flow (basic-auth GET on MediaUrlN) is different
    # enough from Meta's to warrant its own implementation when needed.
    # For the current project scope (Meta is primary) this is fine.
