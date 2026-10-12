"""Outbound HTTP client that writes farm_logging's appointment bookings to
the main FlokIQ backend (main_backend), so a booking made through the
Chocolate chatbot also shows in the app's appointment list.

Called from appointment_supervisor.submit() AFTER the local write already
succeeded -- this is best-effort sync, never the primary write path. A
failure here is logged and swallowed; the farmer's booking is never lost
because the local JSON store already has it.

Appointments go to main_backend's server-to-server route
POST {FLOKIQ_API_BASE_URL}/internal/appointments, authenticated with a
shared key in the X-Internal-Api-Key header (main_backend's logins all need
an OTP, so this service cannot log in as a user). main_backend then runs its
normal booking logic: it assigns the farmer's store doctor and sends the
booking SMS, same as an in-app booking.

Config (env, same precedence pattern as the rest of this app):
  FLOKIQ_SYNC_ENABLED       "true"/"1" to actually call out. Default off --
                            ships inert until explicitly turned on.
  FLOKIQ_API_BASE_URL       main_backend base URL including /v1, e.g.
                            https://api.example.com/v1
  FLOKIQ_INTERNAL_API_KEY   the same value as INTERNAL_API_KEY on main_backend.
  FLOKIQ_SYNC_HEALTH_LOGS   "true" to also call POST /health-logs. Off by
                            default: that endpoint does not exist on
                            main_backend yet (only on mock_server.py).
  FLOKIQ_API_TOKEN          Bearer token, used only for /health-logs.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

import requests

_log = logging.getLogger("flokiq_sync")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_TRUTHY = {"1", "true", "yes", "on"}
# main_backend's validation limit for appointment notes.
_MAX_NOTES = 1000
# main_backend farmer ids are UUIDs. Local demo farmers ("f-001") don't
# exist there, so calling for them would only ever fail.
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def is_enabled() -> bool:
    return os.getenv("FLOKIQ_SYNC_ENABLED", "").lower() in _TRUTHY


def _health_logs_enabled() -> bool:
    return os.getenv("FLOKIQ_SYNC_HEALTH_LOGS", "").lower() in _TRUTHY


def _base_url() -> Optional[str]:
    return os.getenv("FLOKIQ_API_BASE_URL")


def _headers() -> dict[str, str]:
    token = os.getenv("FLOKIQ_API_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def build_appointment_notes(values: dict[str, Any]) -> str:
    """Short note for the vet in the app: which animal, what is wrong, and
    that it was booked through the chatbot. The local booking keeps the
    full details, but main_backend only stores a free-text note.
    e.g. "GAURI (goat): not eating. Booked via Chocolate." """
    animal = str(values.get("animal_name") or "").strip()
    species = str(values.get("species") or "").strip()
    issue = str(values.get("issue") or "").strip()
    if not issue:
        symptoms = [str(s).strip() for s in (values.get("symptoms") or []) if str(s).strip()]
        issue = ", ".join(symptoms)
    extra = str(values.get("miscellaneous_notes") or values.get("notes") or "").strip()

    head = f"{animal} ({species})" if animal and species else (animal or species)
    parts: list[str] = []
    if head and issue:
        parts.append(f"{head}: {issue}.")
    elif head or issue:
        parts.append(f"{head or issue}.")
    if extra:
        parts.append(extra if extra.endswith(".") else f"{extra}.")
    parts.append("Booked via Chocolate.")
    return " ".join(parts)[:_MAX_NOTES]


def create_appointment(
    farmer_id: str,
    date: str,
    time: str,
    notes: str = "",
    health_log_id: Optional[str] = None,
    timeout_s: float = 5.0,
) -> Optional[dict[str, Any]]:
    """POST /internal/appointments on main_backend. Returns the created (or
    already existing) appointment, or None if sync is disabled,
    unconfigured or failed -- caller should treat None as "not synced this
    time", not an error, and keep the local record as the source of truth
    for the booking. main_backend returns the existing appointment instead
    of a duplicate if the same farmer/date/time is sent twice."""
    if not is_enabled():
        return None
    base = (_base_url() or "").rstrip("/")
    key = os.getenv("FLOKIQ_INTERNAL_API_KEY", "")
    if not base or not key:
        _log.warning("flokiq_sync enabled but FLOKIQ_API_BASE_URL or FLOKIQ_INTERNAL_API_KEY unset -- skipping")
        return None
    if not _UUID_RE.match(str(farmer_id or "")):
        _log.info("flokiq_sync skipped farmer=%s -- not a main_backend farmer id", farmer_id)
        return None

    payload: dict[str, Any] = {
        "farmerId": farmer_id,
        "date": date,
        "time": time,
        "notes": (notes or "")[:_MAX_NOTES],
    }
    if health_log_id:
        payload["healthLogId"] = health_log_id

    try:
        resp = requests.post(
            f"{base}/internal/appointments",
            json=payload,
            headers={"X-Internal-Api-Key": key},
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        _log.warning("flokiq_sync create_appointment failed farmer=%s err=%s", farmer_id, exc)
        return None

    if resp.status_code not in (200, 201):
        _log.warning(
            "flokiq_sync create_appointment failed farmer=%s status=%s body=%s",
            farmer_id, resp.status_code, resp.text[:200],
        )
        return None
    try:
        result = resp.json()
    except ValueError:
        result = {}
    _log.info("flokiq_sync appointment synced id=%s farmer=%s", result.get("id"), farmer_id)
    return result


def create_health_log(
    user_id: str,
    pincode: str,
    symptoms: list[str],
    animal_id: Optional[str] = None,
    risk_level: Optional[str] = None,
    ai_diagnosis_suggestion: Optional[str] = None,
    potential_ailments: Optional[list[str]] = None,
    first_aid_advice: Optional[str] = None,
    timeout_s: float = 5.0,
) -> Optional[dict[str, Any]]:
    """POST /health-logs. PROPOSED endpoint -- does not exist on the real
    flokiq backend yet (flokiquser has no health-log creation call at
    all today). Works against mock_server.py now; would 404 against
    main_backend, so it is off unless FLOKIQ_SYNC_HEALTH_LOGS is set.
    Same best-effort contract as create_appointment: None means "not
    synced," never raises."""
    if not is_enabled() or not _health_logs_enabled():
        return None
    base = _base_url()
    if not base:
        return None
    if not pincode:
        _log.warning("flokiq_sync create_health_log skipped -- pincode required (NOT NULL), none available")
        return None

    payload = {
        "user_id": user_id,
        "pincode": pincode,
        "symptoms_reported": json.dumps(symptoms or []),
    }
    if animal_id:
        payload["animal_id"] = animal_id
    if risk_level:
        payload["risk_level"] = risk_level
    if ai_diagnosis_suggestion:
        payload["ai_diagnosis_suggestion"] = ai_diagnosis_suggestion
    if potential_ailments:
        payload["potential_ailments"] = json.dumps(potential_ailments)
    if first_aid_advice:
        payload["first_aid_advice"] = first_aid_advice

    try:
        resp = requests.post(f"{base}/health-logs", data=payload, headers=_headers(), timeout=timeout_s)
        resp.raise_for_status()
        result = resp.json()
        _log.info("flokiq_sync health_log created id=%s user=%s", result.get("log_id"), user_id)
        return result
    except requests.RequestException as exc:
        _log.warning("flokiq_sync create_health_log failed user=%s err=%s", user_id, exc)
        return None
    