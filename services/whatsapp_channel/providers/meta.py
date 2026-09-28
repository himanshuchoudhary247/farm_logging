"""Meta Cloud API (Graph) provider for the WhatsApp channel.

Reference: https://developers.facebook.com/docs/whatsapp/cloud-api

Setup (needs a human):
1. Register a Meta app + WhatsApp Business account, get a phone number
   ID and a long-lived access token.
2. Set WHATSAPP_META_APP_SECRET (the app's client secret -- used to
   verify inbound webhook signatures) and WHATSAPP_META_VERIFY_TOKEN
   (a string YOU pick, echoed back to Meta during webhook setup).
3. Point Meta's webhook config at `https://<your-host>/whatsapp/webhook`.
   Meta issues a one-time GET with `hub.mode=subscribe&hub.verify_token=<yours>&hub.challenge=...`;
   see `main.py::whatsapp_webhook_verify` for the handshake.
4. Subscribe to the `messages` field on the app dashboard.

Everything below assumes Meta Cloud API v18+ (schema stable since ~2023-06).
Verified against Meta's own webhook payload examples in the docs.
"""
from __future__ import annotations

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


_META_GRAPH_BASE = "https://graph.facebook.com/v18.0"

_log = logging.getLogger("whatsapp_channel.meta")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)


class MetaProvider(WhatsAppProvider):
    def __init__(self, config: Any) -> None:
        self.config = config
        # Required at config time; if any of these are missing when a
        # request actually arrives, we raise -- fail fast beats sending
        # unauthenticated traffic.
        if not config.meta_phone_id:
            raise ValueError("WHATSAPP_META_PHONE_ID is required for provider=meta")
        if not config.meta_access_token:
            raise ValueError("WHATSAPP_META_ACCESS_TOKEN is required for provider=meta")
        if not config.meta_app_secret:
            raise ValueError("WHATSAPP_META_APP_SECRET is required for provider=meta")
        self._phone_id = config.meta_phone_id
        self._access_token = config.meta_access_token
        self._app_secret = config.meta_app_secret.encode("utf-8")

    def verify_signature(self, body: bytes, headers: dict) -> bool:
        """Meta signs the raw request body with the app secret using
        HMAC-SHA256 and puts the result in `X-Hub-Signature-256`
        prefixed by `sha256=`. Reject anything without a valid signature
        (missing header, wrong length, mismatched digest) -- otherwise
        anyone who guesses our webhook URL could inject inbound messages.
        Uses hmac.compare_digest for a constant-time comparison."""
        header = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256") or ""
        if not header.startswith("sha256="):
            return False
        provided = header.split("=", 1)[1].strip()
        expected = hmac.new(self._app_secret, body, hashlib.sha256).hexdigest()
        try:
            return hmac.compare_digest(provided, expected)
        except (TypeError, ValueError):
            return False

    def parse_inbound(self, body: dict) -> List[InboundMessage]:
        """Real Meta payload shape (abbreviated):
            {"entry": [{"changes": [{"value": {"messages": [
                {"from": "9198...", "id": "wamid...", "timestamp": "17...",
                 "text": {"body": "..."}} | {"audio": {"id": "..."}} | ...
            ]}}]}]}
        Non-message events (statuses, receipts) have no `messages` key
        -- return empty; the webhook still 200s so Meta stops retrying."""
        if not isinstance(body, dict):
            return []
        out: list[InboundMessage] = []
        for entry in body.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = change.get("value") or {}
                for msg in value.get("messages", []) or []:
                    text_val = ""
                    media_type = None
                    media_id = None
                    if "text" in msg and isinstance(msg["text"], dict):
                        text_val = str(msg["text"].get("body") or "")
                    for mt in ("audio", "image", "video", "voice"):
                        if mt in msg and isinstance(msg[mt], dict):
                            media_type = "audio" if mt == "voice" else mt
                            media_id = str(msg[mt].get("id") or "")
                            break
                    ts_raw = msg.get("timestamp")
                    ts: float | None = None
                    if ts_raw:
                        try:
                            ts = float(ts_raw)
                        except (TypeError, ValueError):
                            ts = None
                    out.append(InboundMessage(
                        from_phone=str(msg.get("from") or ""),
                        text=text_val,
                        id=str(msg.get("id") or f"meta-{time.time_ns()}"),
                        ts=ts,
                        media_type=media_type,
                        media_id_or_url=media_id,
                        raw=msg,
                    ))
        return out

    def send_text(self, to_phone: str, text: str) -> None:
        """POST /{phone_id}/messages with a text body. Raises on any
        non-2xx from Meta -- caller (router) logs and moves on; the
        message is lost for this attempt (not retried at this layer,
        matching how Meta's own retry semantics work: they'll re-send
        the inbound if we haven't 200'd yet, but a failed OUTBOUND is
        on us to notice)."""
        url = f"{_META_GRAPH_BASE}/{self._phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }
        t0 = time.time()
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        _log.info(
            "meta send_text to=%s status=%d ms=%.0f len=%d",
            to_phone, resp.status_code, (time.time() - t0) * 1000, len(text),
        )
        resp.raise_for_status()

    def download_media(self, media_id_or_url: str) -> bytes:
        """Meta's media flow is two-step: GET /{media_id} returns a JSON
        with a `url` field (a signed URL that expires in ~5 min);
        GET that url with the same Bearer token returns the actual bytes."""
        info_url = f"{_META_GRAPH_BASE}/{media_id_or_url}"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        resp = requests.get(info_url, headers=headers, timeout=10)
        resp.raise_for_status()
        signed_url = (resp.json() or {}).get("url")
        if not signed_url:
            raise ValueError(f"Meta returned no signed url for media {media_id_or_url!r}")
        blob_resp = requests.get(signed_url, headers=headers, timeout=30)
        blob_resp.raise_for_status()
        return blob_resp.content
