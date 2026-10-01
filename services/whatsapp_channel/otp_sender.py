"""OTP senders for WhatsApp enrollment (finding 1 of the PR #24 review).

The code goes by SMS to the farmer's REGISTERED phone, never over
WhatsApp: whoever is messaging us on WhatsApp is exactly the party being
verified, so the code must reach a channel only the real farmer controls.

- mock: dev/tests only. Logs the code and keeps it in memory.
- msg91: the same MSG91 Flow API and MSG91_AUTH_KEY that main_backend's
  sendSMS uses (src/utils/smsUtils.js), with a DLT-approved OTP template
  whose code variable is WHATSAPP_MSG91_OTP_VAR (default "var1").
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

import requests

_log = logging.getLogger("whatsapp_channel.otp_sender")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_MSG91_FLOW_URL = "https://control.msg91.com/api/v5/flow/"


class OtpSender:
    def send(self, phone: str, code: str) -> bool:
        """Send `code` to `phone`. True only if the provider accepted it."""
        raise NotImplementedError


class MockOtpSender(OtpSender):
    """Dev/tests only: never configure this on a real deployment."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, phone: str, code: str) -> bool:
        self.sent.append((phone, code))
        _log.warning("mock OTP sender (dev only): code for %s is %s", phone, code)
        return True


def _msg91_mobile(phone: str) -> str:
    """Same rule as main_backend's formatMobile: digits only, and a bare
    10-digit number gets the 91 country prefix."""
    digits = re.sub(r"\D", "", phone or "")
    return f"91{digits}" if len(digits) == 10 else digits


class Msg91OtpSender(OtpSender):
    def __init__(self, auth_key: str, template_id: str, code_var: str = "var1", timeout: float = 10.0) -> None:
        self._auth_key = auth_key
        self._template_id = template_id
        self._code_var = code_var
        self._timeout = timeout

    def send(self, phone: str, code: str) -> bool:
        # The code itself is never logged for the real sender.
        payload = {
            "template_id": self._template_id,
            "recipients": [{"mobiles": _msg91_mobile(phone), self._code_var: code}],
        }
        try:
            resp = requests.post(
                _MSG91_FLOW_URL,
                json=payload,
                headers={"authkey": self._auth_key, "Content-Type": "application/json"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            _log.warning("msg91 OTP send failed: %s", exc)
            return False
        if resp.status_code != 200:
            _log.warning("msg91 OTP send failed: HTTP %s %s", resp.status_code, resp.text[:200])
            return False
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if isinstance(body, dict) and body.get("type") == "error":
            _log.warning("msg91 OTP send rejected: %s", body.get("message"))
            return False
        return True


def build_otp_sender(cfg: Any) -> Optional[OtpSender]:
    """The configured sender, or None when no usable OTP provider is set.
    None makes the router refuse enrollment (fail closed)."""
    provider = (getattr(cfg, "otp_provider", "") or "").strip().lower()
    if provider == "mock":
        return MockOtpSender()
    if provider == "msg91":
        if not cfg.msg91_auth_key or not cfg.msg91_otp_template_id:
            _log.warning(
                "WHATSAPP_OTP_PROVIDER=msg91 but MSG91_AUTH_KEY / "
                "WHATSAPP_MSG91_OTP_TEMPLATE_ID is missing -- enrollment disabled"
            )
            return None
        return Msg91OtpSender(cfg.msg91_auth_key, cfg.msg91_otp_template_id, cfg.msg91_otp_var or "var1")
    if provider:
        _log.warning("unknown WHATSAPP_OTP_PROVIDER=%r -- enrollment disabled", provider)
    return None
