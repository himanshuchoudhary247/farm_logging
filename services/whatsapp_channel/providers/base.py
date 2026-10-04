"""WhatsAppProvider abstract base + InboundMessage dataclass.

The router (`services/whatsapp_channel/router.py`) is provider-agnostic:
it only ever talks to this interface. Adding a new WhatsApp gateway
(360dialog, MessageBird, whatever) is a matter of implementing this
protocol, adding it to the provider factory in
`services/whatsapp_channel/__init__.py::get_provider`, and adding its
env vars to config.py + .env.example. Zero router changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class InboundMessage:
    """Normalized shape the router consumes. Every provider's
    parse_inbound() converts its own webhook payload into a list of
    these. `raw` keeps the original provider dict for debugging /
    logging -- never inspected by the router itself."""
    from_phone: str            # canonicalized on lookup; providers pass through the wire format
    text: str                  # empty string for media-only messages
    id: str                    # provider's message ID (for dedupe)
    ts: Optional[float] = None # UNIX seconds; None if the provider didn't send one
    media_type: Optional[str] = None   # "audio" | "image" | "video" | None
    media_id_or_url: Optional[str] = None  # Meta returns an id (lookup + download); Twilio a URL
    raw: dict = field(default_factory=dict)


class WhatsAppProvider(ABC):
    """Provider interface. Each real provider (Meta, Twilio) supplies its
    own implementation; the router NEVER special-cases on which one is
    active."""

    @abstractmethod
    def verify_signature(self, body: bytes, headers: dict) -> bool:
        """True iff the provider's signature header validates `body`. If
        False, the webhook handler returns 403 without parsing the body."""

    @abstractmethod
    def parse_inbound(self, body: dict) -> List[InboundMessage]:
        """Turn one webhook body into zero or more InboundMessage rows.
        Meta batches messages under one POST; Twilio sends one at a time.
        Non-message events (delivery receipts, read receipts, status
        callbacks) return an empty list -- the webhook still returns 200,
        just nothing to dispatch."""

    @abstractmethod
    def send_text(self, to_phone: str, text: str) -> None:
        """Send a plain text WhatsApp message. Should retry cleanly on
        provider-side transient errors OR raise -- the router doesn't
        handle send failures beyond logging (a retryable failure is
        Meta's problem, not ours; a permanent one means the farmer
        won't get this specific reply, which is a real limitation but
        not a bug in this module)."""

    def send_audio(self, to_phone: str, audio_bytes: bytes) -> None:
        """Optional. Default NotImplementedError -- providers that don't
        support audio send can leave this alone; the router only calls it
        when `include_audio: true` in config AND the agent produced audio."""
        raise NotImplementedError(f"{type(self).__name__} does not implement audio send")

    def download_media(self, media_id_or_url: str) -> bytes:
        """Optional. Default NotImplementedError -- only Meta requires the
        two-step /media/<id> -> signed URL dance; Twilio delivers a direct
        URL that requires basic auth. The router only calls this when
        InboundMessage.media_id_or_url is set."""
        raise NotImplementedError(f"{type(self).__name__} does not implement media download")
