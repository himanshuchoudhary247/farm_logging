"""Channel-gated dispatcher for the WhatsApp transport.

This is the entire load-bearing logic of the WhatsApp module. Per plan
elegant-roaming-river.md, it does NOT add a new agent -- it wires the
inbound WhatsApp message into `services.chat_orchestrator.adk_router.
route_turn_adk` with an `allowed_intents` gate so a channel-specific
feature subset is honored deterministically.

Flow for one inbound message:
  1. Dedupe by provider message.id (Meta retries aggressively).
  2. Rate-limit per phone (in-memory rolling window).
  3. Resolve phone -> Farmer (whatsapp_phone override wins; else phone).
  4. If unknown -> enrollment prompt (or generic reject if enrollment
     is disabled) and return.
  5. Detect message language from script (Devanagari->hi, etc); fall
     back to config default when the text is script-neutral.
  6. If the resolved farmer has a pending enrollment prompt state --
     nothing complex, just call `route_turn_adk` normally. Enrollment
     confirmation handling for a KNOWN farmer receiving a matching
     phone/username lookup is done by _try_enroll_from_reply below; a
     no-match reply falls through to normal dispatch (so a farmer
     already-linked can still ask questions).
  7. Build a namespaced session_id (whatsapp-<sha1(phone)[:12]>) so
     sticky routing works exactly like on the app but never collides
     with app browser-session UUIDs.
  8. Dispatch via route_turn_adk(..., allowed_intents=cfg.allowed_intents).
     If the dispatcher returns the blocked stub (agent=None), send the
     localized blocked_intent message; else send the reply_text.
  9. Truncate at max_reply_chars with a localized trim suffix.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from services.chat_orchestrator.adk_router import route_turn_adk
from services.query_agent.adk_agent import detect_language
from services.whatsapp_channel.config import WhatsAppChannelConfig, load_config
from services.whatsapp_channel.dedupe import MessageDedupe, default_dedupe
from services.whatsapp_channel.messages import message, summarize_allowed_intents
from services.whatsapp_channel.providers.base import (
    InboundMessage,
    WhatsAppProvider,
)
from services.whatsapp_channel.rate_limit import PhoneRateLimiter
from storage import (
    _canonicalize_phone,
    get_farmer_by_whatsapp_phone,
    get_farmer_by_username,
    load_farmers,
    update_farmer_whatsapp_phone,
)

_log = logging.getLogger("whatsapp_channel.router")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)


# Module-level rate limiter, keyed by config-at-import-time. Tests
# reset it via `reset_state_for_tests()`.
_rate_limiter: Optional[PhoneRateLimiter] = None
_dedupe: MessageDedupe = default_dedupe


def _get_rate_limiter(cfg: WhatsAppChannelConfig) -> PhoneRateLimiter:
    global _rate_limiter
    if _rate_limiter is None or (
        _rate_limiter.per_min != cfg.per_phone_per_min
        or _rate_limiter.per_hour != cfg.per_phone_per_hour
    ):
        _rate_limiter = PhoneRateLimiter(cfg.per_phone_per_min, cfg.per_phone_per_hour)
    return _rate_limiter


def _session_id_for(phone: str) -> str:
    """Deterministic per-phone session ID, explicitly namespaced with
    `whatsapp-` so it can never collide with an app browser-session UUID.
    Short (12 chars of sha1) so logs are readable."""
    digest = hashlib.sha1(phone.encode("utf-8")).hexdigest()[:12]
    return f"whatsapp-{digest}"


def _pick_language(text: str, cfg: WhatsAppChannelConfig) -> str:
    """Reuse query_agent.detect_language for script-based detection.
    Returns a canonical IETF-like tag (`en-IN`, `hi-IN`, etc) that the
    downstream agents expect. Script-neutral text (bare number, emoji,
    punctuation) falls back to config's default_language."""
    detected = detect_language(text)  # 'en' | 'hi' | 'ta' | 'te' | 'kn'
    if detected == "en":
        # Ambiguous: could be genuinely English or just script-neutral.
        # If any Latin letter is present at all treat as English; else
        # fall through to the configured default (matters when config
        # default is a non-English tag).
        if any(ch.isalpha() and ord(ch) < 128 for ch in text):
            return "en-IN"
        return cfg.default_language
    return {"hi": "hi-IN", "ta": "ta-IN", "te": "te-IN", "kn": "kn-IN"}[detected]


def _truncate_reply(text: str, cap: int, language: str) -> str:
    """Clip at `cap` chars total, appending a localized trim suffix so
    the farmer knows their answer was cut. cap includes the suffix, and
    the guarantee is len(result) <= cap. Edge case: if the localized
    suffix alone is longer than cap (only happens with unrealistically
    small caps in tests), the suffix itself is clipped too rather than
    silently blowing past the cap."""
    if not text:
        return text
    if len(text) <= cap:
        return text
    suffix = message(language, "reply_trimmed_suffix")
    if len(suffix) >= cap:
        # Cap is smaller than the localized suffix itself -- clip both
        # (keeps len(result) <= cap even for pathological configs).
        return (text[: max(0, cap - 3)] + "...")[:cap]
    return text[: cap - len(suffix)] + suffix


def _try_enroll_from_reply(text: str) -> "Optional[object]":
    """When an unknown-phone farmer replies to the enrollment prompt with
    their registered phone or username, resolve to that farmer and return
    the Farmer object -- caller then sets whatsapp_phone on it. Returns
    None if the reply doesn't match anything (caller sends the
    enrollment_failed message)."""
    stripped = text.strip()
    if not stripped:
        return None
    # Phone-shape check: canonicalize the reply, then look up by phone
    # OR whatsapp_phone (same helper the initial lookup uses).
    canon = _canonicalize_phone(stripped)
    if canon and (canon.startswith("+") or canon.isdigit()) and len(canon) >= 8:
        found = get_farmer_by_whatsapp_phone(canon)
        if found is not None:
            return found
    # Otherwise treat as a username lookup.
    return get_farmer_by_username(stripped)


def handle_inbound(provider: WhatsAppProvider, msg: InboundMessage) -> None:
    """Process one InboundMessage end-to-end: verify, dispatch, send.
    Never raises to the webhook handler -- swallows and logs any error
    (a farmer-visible reply is not attempted for pipeline exceptions,
    matching how Meta itself handles our downstream failures: they'll
    just retry the webhook)."""
    cfg = load_config()
    if not cfg.enabled:
        _log.info("whatsapp inbound dropped: channel disabled")
        return

    if not _dedupe.is_new(msg.id):
        _log.info("whatsapp inbound dedupe hit id=%s from=%s", msg.id, msg.from_phone)
        return

    ok, reason = _get_rate_limiter(cfg).check(msg.from_phone)
    if not ok:
        _log.info(
            "whatsapp rate-limited from=%s reason=%s (text=%r)",
            msg.from_phone, reason, msg.text[:80],
        )
        language = _pick_language(msg.text, cfg)
        try:
            provider.send_text(msg.from_phone, message(language, "rate_limited"))
        except Exception as exc:
            _log.warning("whatsapp send_text failed for rate_limited: %s", exc)
        return

    farmer = get_farmer_by_whatsapp_phone(msg.from_phone)
    language = _pick_language(msg.text, cfg)

    if farmer is None:
        # Unknown phone. Enrollment flow (if enabled) tries to match the
        # reply against a registered farmer's phone or username; on match
        # we bind whatsapp_phone and prompt them to send their question.
        if not cfg.enrollment_enabled:
            provider.send_text(msg.from_phone, message(language, "unknown_farmer_no_enroll"))
            return
        candidate = _try_enroll_from_reply(msg.text)
        if candidate is None:
            provider.send_text(msg.from_phone, message(language, "unknown_farmer_enroll_prompt"))
            return
        update_farmer_whatsapp_phone(candidate.id, msg.from_phone)
        provider.send_text(msg.from_phone, message(language, "enrollment_success", name=candidate.name))
        return

    session_id = _session_id_for(msg.from_phone)
    try:
        result = route_turn_adk(
            farmer_id=farmer.id,
            session_id=session_id,
            text=msg.text,
            language=language,
            include_audio=cfg.include_audio,
            allowed_intents=set(cfg.allowed_intents),
        )
    except Exception as exc:
        _log.exception("route_turn_adk raised for farmer=%s from=%s: %s", farmer.id, msg.from_phone, exc)
        return

    if result.get("agent") is None:
        # Gate blocked this intent for the WhatsApp channel. Send the
        # localized explanation instead of any agent output.
        reply = message(
            language, "blocked_intent",
            allowed_summary=summarize_allowed_intents(language, cfg.allowed_intents),
        )
    else:
        reply = str(result.get("reply_text") or "").strip()
        if not reply:
            _log.warning(
                "whatsapp empty reply from agent=%s farmer=%s -- dropping",
                result.get("agent"), farmer.id,
            )
            return

    reply = _truncate_reply(reply, cfg.max_reply_chars, language)
    try:
        provider.send_text(msg.from_phone, reply)
    except Exception as exc:
        _log.warning("whatsapp send_text failed for farmer=%s: %s", farmer.id, exc)


def handle_inbound_batch(provider: WhatsAppProvider, messages: "list[InboundMessage]") -> None:
    """Process every parsed message from one webhook delivery. Runs as a
    FastAPI background task, after the webhook has already returned 200.
    One message failing never stops the rest: handle_inbound already logs
    its own errors, and this is the same belt-and-suspenders loop that used
    to live inline in the webhook handler."""
    for msg in messages:
        try:
            handle_inbound(provider, msg)
        except Exception as exc:  # router already logs, but belt-and-suspenders
            _log.exception("whatsapp handle_inbound raised for id=%s: %s", msg.id, exc)


def reset_state_for_tests() -> None:
    """Test hook: forget the module-level rate limiter and dedupe so
    each test starts fresh. Never call from production code paths."""
    global _rate_limiter, _dedupe
    _rate_limiter = None
    _dedupe = MessageDedupe()
