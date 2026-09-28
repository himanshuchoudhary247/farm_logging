"""WhatsApp channel config loader. YAML from config/channels.yaml with
env-var overrides. Same shape as bedrock_adapter._load_llm_config -- one
module-level cache filled lazily on first call.

Env override precedence (highest first):
1. WHATSAPP_* environment variables (explicit per-deploy).
2. config/channels.yaml `channels.whatsapp.*` block (checked-in defaults).
3. Hardcoded defaults in DEFAULTS below (safe/inert -- disabled).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet, Optional

_log = logging.getLogger("whatsapp_channel.config")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)


# Hardcoded fallbacks. Ships inert: enabled=false so nothing changes for
# any existing deployment or local dev environment.
DEFAULTS = {
    "enabled": False,
    "allowed_intents": ["query", "appointment", "weather", "add_animal"],
    "default_language": "en-IN",
    "include_audio": False,
    "max_reply_chars": 4000,
    "provider": "mock",
    "rate_limit": {"per_phone_per_min": 6, "per_phone_per_hour": 100},
    "enrollment": {"enabled": True},
}


class ChannelDisabled(Exception):
    """Raised by get_provider() when the WhatsApp module is off. Callers
    (the webhook endpoints) turn this into a 503 -- not a 404, because 404
    would falsely imply the endpoint doesn't exist rather than being off."""


@dataclass(frozen=True)
class WhatsAppChannelConfig:
    enabled: bool
    allowed_intents: FrozenSet[str]
    default_language: str
    include_audio: bool
    max_reply_chars: int
    provider: str
    per_phone_per_min: int
    per_phone_per_hour: int
    enrollment_enabled: bool
    # Provider-specific secrets, resolved from env only (never checked in).
    meta_phone_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    meta_app_secret: Optional[str] = None
    meta_verify_token: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None


_cache: Optional[WhatsAppChannelConfig] = None


def _yaml_config() -> dict:
    """Load config/channels.yaml if present. Empty dict if missing or the
    file fails to parse -- we still ship with a valid inert config from
    DEFAULTS below."""
    path = os.getenv("CHANNELS_CONFIG_PATH") or str(
        Path(__file__).resolve().parents[2] / "config" / "channels.yaml"
    )
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        _log.info("channels config not found at %s -- using defaults", path)
        return {}
    except Exception as exc:  # pragma: no cover -- YAML parse error surfaces via log
        _log.warning("channels config load failed at %s: %s -- using defaults", path, exc)
        return {}
    return (data.get("channels") or {}).get("whatsapp") or {}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        _log.warning("env %s=%r is not an integer -- using default %d", name, raw, default)
        return default


def _resolve_intents(yaml_val, env_val: Optional[str]) -> FrozenSet[str]:
    """Env WHATSAPP_ALLOWED_INTENTS is a comma-separated list; YAML is a
    real list. Env wins if set. Invalid intent names are silently dropped
    (with a warning) so a config typo doesn't crash the module -- the
    intent-set is validated against _VALID_INTENTS at gate-check time
    inside route_turn_adk, not here."""
    if env_val is not None:
        raw = [s.strip() for s in env_val.split(",") if s.strip()]
    elif yaml_val:
        raw = list(yaml_val)
    else:
        raw = list(DEFAULTS["allowed_intents"])
    known = {"query", "appointment", "weather", "add_animal"}
    resolved = {i for i in raw if i in known}
    dropped = set(raw) - known
    if dropped:
        _log.warning("channels.whatsapp.allowed_intents dropped unknown intents: %s", sorted(dropped))
    return frozenset(resolved)


def load_config() -> WhatsAppChannelConfig:
    """Return the resolved config (env > YAML > DEFAULTS). Cached module-
    level so repeated calls are cheap. Call `reset_cache_for_tests()` in a
    test fixture to pick up env changes mid-suite."""
    global _cache
    if _cache is not None:
        return _cache
    yaml_cfg = _yaml_config()
    rate = yaml_cfg.get("rate_limit") or {}
    enrollment = yaml_cfg.get("enrollment") or {}

    _cache = WhatsAppChannelConfig(
        enabled=_env_bool("WHATSAPP_ENABLED", bool(yaml_cfg.get("enabled", DEFAULTS["enabled"]))),
        allowed_intents=_resolve_intents(
            yaml_cfg.get("allowed_intents"),
            os.getenv("WHATSAPP_ALLOWED_INTENTS"),
        ),
        default_language=(
            os.getenv("WHATSAPP_DEFAULT_LANGUAGE")
            or yaml_cfg.get("default_language")
            or DEFAULTS["default_language"]
        ),
        include_audio=_env_bool(
            "WHATSAPP_INCLUDE_AUDIO",
            bool(yaml_cfg.get("include_audio", DEFAULTS["include_audio"])),
        ),
        max_reply_chars=_env_int(
            "WHATSAPP_MAX_REPLY_CHARS",
            int(yaml_cfg.get("max_reply_chars", DEFAULTS["max_reply_chars"])),
        ),
        provider=(
            os.getenv("WHATSAPP_PROVIDER")
            or yaml_cfg.get("provider")
            or DEFAULTS["provider"]
        ),
        per_phone_per_min=_env_int(
            "WHATSAPP_RATE_LIMIT_PER_MIN",
            int(rate.get("per_phone_per_min", DEFAULTS["rate_limit"]["per_phone_per_min"])),
        ),
        per_phone_per_hour=_env_int(
            "WHATSAPP_RATE_LIMIT_PER_HOUR",
            int(rate.get("per_phone_per_hour", DEFAULTS["rate_limit"]["per_phone_per_hour"])),
        ),
        enrollment_enabled=_env_bool(
            "WHATSAPP_ENROLLMENT_ENABLED",
            bool(enrollment.get("enabled", DEFAULTS["enrollment"]["enabled"])),
        ),
        meta_phone_id=os.getenv("WHATSAPP_META_PHONE_ID") or None,
        meta_access_token=os.getenv("WHATSAPP_META_ACCESS_TOKEN") or None,
        meta_app_secret=os.getenv("WHATSAPP_META_APP_SECRET") or None,
        meta_verify_token=os.getenv("WHATSAPP_META_VERIFY_TOKEN") or None,
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID") or None,
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN") or None,
        twilio_whatsapp_from=os.getenv("TWILIO_WHATSAPP_FROM") or None,
    )
    return _cache


def reset_cache_for_tests() -> None:
    """Test helper: forget the cached config so a subsequent load_config()
    re-reads env + YAML. Do not call from production code paths -- the
    cache is intentional there (config never changes mid-process)."""
    global _cache
    _cache = None
