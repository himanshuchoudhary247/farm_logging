"""Test/dev provider. Records everything, verifies nothing, sends nowhere.

Used by:
- Every test in tests/test_whatsapp_*.py -- so unit tests don't need a
  real Meta app secret or Twilio account.
- scripts/whatsapp_dev_send.py --provider mock -- so a developer can
  exercise the full inbound-message pipeline locally without touching
  the real WhatsApp Business API at all.

`parse_inbound` accepts either the plain dev-send dict shape (single
message per POST body -- fastest to write in a test) OR a Meta-style
`{entry: [{changes: [{value: {messages: [...]}}]}]}` envelope (so a
smoke test that copy-pastes a real Meta payload also works). Anything
else parses as an empty list.
"""
from __future__ import annotations

import time
from typing import Any, List

from services.whatsapp_channel.providers.base import (
    InboundMessage,
    WhatsAppProvider,
)


class MockProvider(WhatsAppProvider):
    def __init__(self, config: Any = None) -> None:
        self.config = config
        # Every send captured as (to_phone, text). Tests assert on this
        # list rather than making network calls.
        self.sent_texts: list[tuple[str, str]] = []
        self.sent_audio: list[tuple[str, bytes]] = []
        self.downloaded: dict[str, bytes] = {}
        # Preload test-only media responses via `mock.stub_media(...)`.
        self._media_stubs: dict[str, bytes] = {}

    def verify_signature(self, body: bytes, headers: dict) -> bool:
        return True

    def parse_inbound(self, body: dict) -> List[InboundMessage]:
        if not isinstance(body, dict):
            return []
        # Simple dev-send shape: single message dict, top-level.
        if "from_phone" in body and "text" in body:
            return [InboundMessage(
                from_phone=str(body["from_phone"]),
                text=str(body.get("text") or ""),
                id=str(body.get("id") or f"mock-{time.time_ns()}"),
                ts=body.get("ts"),
                media_type=body.get("media_type"),
                media_id_or_url=body.get("media_id_or_url"),
                raw=dict(body),
            )]
        # Meta-style envelope. See tests/test_whatsapp_providers.py for the shape.
        out: list[InboundMessage] = []
        for entry in body.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = change.get("value") or {}
                for msg in value.get("messages", []) or []:
                    text_val = ""
                    media_type = None
                    media_id = None
                    if "text" in msg:
                        text_val = str((msg.get("text") or {}).get("body") or "")
                    for mt in ("audio", "image", "video"):
                        if mt in msg:
                            media_type = mt
                            media_id = str((msg.get(mt) or {}).get("id") or "")
                            break
                    out.append(InboundMessage(
                        from_phone=str(msg.get("from") or ""),
                        text=text_val,
                        id=str(msg.get("id") or f"mock-{time.time_ns()}"),
                        ts=float(msg["timestamp"]) if msg.get("timestamp") else None,
                        media_type=media_type,
                        media_id_or_url=media_id,
                        raw=msg,
                    ))
        return out

    def send_text(self, to_phone: str, text: str) -> None:
        self.sent_texts.append((to_phone, text))

    def send_audio(self, to_phone: str, audio_bytes: bytes) -> None:
        self.sent_audio.append((to_phone, audio_bytes))

    def download_media(self, media_id_or_url: str) -> bytes:
        blob = self._media_stubs.get(media_id_or_url, b"")
        self.downloaded[media_id_or_url] = blob
        return blob

    def stub_media(self, media_id_or_url: str, payload: bytes) -> None:
        """Test helper: pre-register bytes to return from download_media."""
        self._media_stubs[media_id_or_url] = payload
