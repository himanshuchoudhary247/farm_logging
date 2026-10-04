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
  4. If unknown -> enrollment with OTP (or generic reject if enrollment
     is disabled or no OTP sender is configured) and return. The sender
     claims a farmer by registered phone or username; a 6-digit code is
     SMSed to that farmer's REGISTERED phone, and the WhatsApp number is
     linked only after it sends that code back. A question sent along
     with the claim is answered right after linking. See
     _handle_unknown_sender.
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
import re
from typing import Optional

from services.chat_orchestrator.adk_router import route_turn_adk
from services.query_agent.adk_agent import detect_language
from services.whatsapp_channel.config import WhatsAppChannelConfig, load_config
from services.whatsapp_channel.dedupe import MessageDedupe, default_dedupe
from services.whatsapp_channel.enrollment import PendingEnrollments, new_code
from services.whatsapp_channel.messages import message, summarize_allowed_intents
from services.whatsapp_channel.otp_sender import OtpSender, build_otp_sender
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


def _new_claim_limiter() -> PhoneRateLimiter:
    """Claims (a phone number or username typed by an unknown WhatsApp
    number), per WhatsApp sender: slows down guessing usernames."""
    return PhoneRateLimiter(per_min=3, per_hour=10)


def _new_otp_send_limiter() -> PhoneRateLimiter:
    """OTP SMS per target farmer: stops anyone from flooding a farmer's
    phone with codes (and running up SMS cost)."""
    return PhoneRateLimiter(per_min=1, per_hour=3)


# Enrollment (OTP) state -- finding 1 of the PR #24 review. Same
# in-memory, per-process limitation as the rate limiter and dedupe.
_pending = PendingEnrollments()
_claim_limiter = _new_claim_limiter()
_otp_send_limiter = _new_otp_send_limiter()
_otp_sender: Optional[OtpSender] = None
_otp_sender_provider: Optional[str] = None

# A bare 6-digit reply is an OTP answer.
_OTP_RE = re.compile(r"^\s*(\d{6})\s*$")
# A leading phone number, allowing the spaces/dashes farmers type
# ("+91 98765 43210"), optionally followed by a question.
_PHONE_CLAIM_RE = re.compile(r"^\s*(\+?\d[\d\s\-]{6,}\d)(?:\s+(.*))?$", re.DOTALL)


def _get_rate_limiter(cfg: WhatsAppChannelConfig) -> PhoneRateLimiter:
    global _rate_limiter
    if _rate_limiter is None or (
        _rate_limiter.per_min != cfg.per_phone_per_min
        or _rate_limiter.per_hour != cfg.per_phone_per_hour
    ):
        _rate_limiter = PhoneRateLimiter(cfg.per_phone_per_min, cfg.per_phone_per_hour)
    return _rate_limiter


def _get_otp_sender(cfg: WhatsAppChannelConfig) -> Optional[OtpSender]:
    """The configured OTP sender, built once per provider setting. None
    means enrollment must be refused (fail closed)."""
    global _otp_sender, _otp_sender_provider
    if _otp_sender is None or _otp_sender_provider != cfg.otp_provider:
        _otp_sender = build_otp_sender(cfg)
        _otp_sender_provider = cfg.otp_provider
    return _otp_sender


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
    the Farmer object. Since the OTP step, the caller does NOT link on a
    match any more: it sends a code to the farmer's registered phone and
    links only after the code comes back. Returns None if the reply
    doesn't match anything."""
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


def _split_claim(text: str) -> tuple[str, str]:
    """Split an enrollment reply into (claim, question). The claim is a
    leading phone number (spaces/dashes allowed) or else the first word
    (a username); the rest is a question the farmer sent along, e.g.
    "+919999999999 how many goats" -> ("+919999999999", "how many goats").
    The question is answered once the OTP is verified (finding 4 of the
    PR #24 review: it used to be dropped)."""
    match = _PHONE_CLAIM_RE.match(text or "")
    if match:
        return match.group(1).strip(), (match.group(2) or "").strip()
    parts = (text or "").strip().split(None, 1)
    if not parts:
        return "", ""
    return parts[0], (parts[1].strip() if len(parts) > 1 else "")


def _answer(provider: WhatsAppProvider, cfg: WhatsAppChannelConfig, farmer: object,
            from_phone: str, text: str, language: str) -> None:
    """Dispatch one message from a linked farmer through route_turn_adk and
    send the reply. Used for every normal message, and for the question a
    farmer sent along with an enrollment claim once the OTP is verified."""
    session_id = _session_id_for(from_phone)
    try:
        result = route_turn_adk(
            farmer_id=farmer.id,
            session_id=session_id,
            text=text,
            language=language,
            include_audio=cfg.include_audio,
            allowed_intents=set(cfg.allowed_intents),
        )
    except Exception as exc:
        _log.exception("route_turn_adk raised for farmer=%s from=%s: %s", farmer.id, from_phone, exc)
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
        provider.send_text(from_phone, reply)
    except Exception as exc:
        _log.warning("whatsapp send_text failed for farmer=%s: %s", farmer.id, exc)


def _handle_unknown_sender(provider: WhatsAppProvider, cfg: WhatsAppChannelConfig,
                           msg: InboundMessage, language: str) -> None:
    """Enrollment for a WhatsApp number that isn't linked to any farmer
    (finding 1 of the PR #24 review). Linking used to happen as soon as
    the sender typed a registered phone or username, so anyone could take
    over a farmer's account. Now:
      1. The sender claims a farmer (phone or username, optionally with a
         question after it).
      2. If the claim matches, a 6-digit code is SMSed to that farmer's
         REGISTERED phone. The reply on WhatsApp is the same whether or
         not it matched, so usernames can't be probed.
      3. Only a correct code from the same WhatsApp number links it; the
         pending question is then answered (finding 4).
    Claims are rate-limited per WhatsApp number and OTP SMS per farmer."""
    if not cfg.enrollment_enabled:
        provider.send_text(msg.from_phone, message(language, "unknown_farmer_no_enroll"))
        return

    sender = _get_otp_sender(cfg)
    if sender is None:
        _log.warning(
            "whatsapp enrollment is enabled but no OTP provider is configured "
            "(WHATSAPP_OTP_PROVIDER) -- refusing to link from=%s", msg.from_phone,
        )
        provider.send_text(msg.from_phone, message(language, "unknown_farmer_no_enroll"))
        return

    code_match = _OTP_RE.match(msg.text or "")
    if code_match and _pending.has(msg.from_phone):
        status, pending = _pending.verify(msg.from_phone, code_match.group(1))
        if status == "ok":
            update_farmer_whatsapp_phone(pending.farmer_id, msg.from_phone)
            _log.info("whatsapp enrollment verified farmer=%s from=%s", pending.farmer_id, msg.from_phone)
            provider.send_text(msg.from_phone, message(language, "enrollment_success", name=pending.farmer_name))
            if pending.question:
                farmer = get_farmer_by_whatsapp_phone(msg.from_phone)
                if farmer is not None:
                    _answer(provider, cfg, farmer, msg.from_phone, pending.question,
                            _pick_language(pending.question, cfg))
            return
        key = {"wrong": "otp_wrong", "locked": "otp_locked"}.get(status, "otp_expired")
        _log.info("whatsapp enrollment code %s from=%s", status, msg.from_phone)
        provider.send_text(msg.from_phone, message(language, key))
        return

    claim, question = _split_claim(msg.text)
    allowed, _ = _claim_limiter.check(msg.from_phone)
    candidate = _try_enroll_from_reply(claim) if (allowed and claim) else None
    if not allowed:
        _log.info("whatsapp enrollment claim rate-limited from=%s", msg.from_phone)
    candidate_phone = getattr(candidate, "phone", "") if candidate is not None else ""
    if candidate is not None and candidate_phone:
        if _otp_send_limiter.check(str(candidate.id))[0]:
            code = new_code()
            if sender.send(candidate_phone, code):
                _pending.start(msg.from_phone, candidate.id, candidate.name, code, question=question)
                _log.info("whatsapp enrollment code sent farmer=%s from=%s", candidate.id, msg.from_phone)
            else:
                _log.warning("whatsapp enrollment code send failed farmer=%s", candidate.id)
        else:
            _log.info("whatsapp enrollment OTP rate-limited farmer=%s", candidate.id)
    elif candidate is not None:
        _log.info("whatsapp enrollment claim matched farmer=%s with no registered phone", candidate.id)

    # Same reply whether or not anything matched (no account probing).
    provider.send_text(msg.from_phone, message(language, "enroll_code_sent"))


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
        # Unknown phone. Enrollment (if enabled) needs an OTP sent to the
        # claimed farmer's registered phone before anything is linked --
        # see _handle_unknown_sender.
        _handle_unknown_sender(provider, cfg, msg, language)
        return

    _answer(provider, cfg, farmer, msg.from_phone, msg.text, language)


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
    """Test hook: forget the module-level rate limiter, dedupe and
    enrollment (OTP) state so each test starts fresh. Never call from
    production code paths."""
    global _rate_limiter, _dedupe, _pending, _claim_limiter, _otp_send_limiter
    global _otp_sender, _otp_sender_provider
    _rate_limiter = None
    _dedupe = MessageDedupe()
    _pending = PendingEnrollments()
    _claim_limiter = _new_claim_limiter()
    _otp_send_limiter = _new_otp_send_limiter()
    _otp_sender = None
    _otp_sender_provider = None
