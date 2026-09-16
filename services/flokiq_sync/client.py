"""Outbound HTTP client for writing appointments/health-logs to flokiq's
real backend (or the local mock_server.py during dev/test).

Called from appointment_supervisor.submit() AFTER the local write already
succeeded -- this is best-effort sync, never the primary write path. A
failure here is logged and swallowed; the farmer's booking is never lost
because the local JSON store already has it.

Config (env, same precedence pattern as the rest of this app):
  FLOKIQ_SYNC_ENABLED       "true"/"1" to actually call out. Default off --
                            ships inert until explicitly turned on.
  FLOKIQ_API_BASE_URL       e.g. http://localhost:8077 (mock_server.py) or
                            the real sandbox base URL once that's decided.
  FLOKIQ_API_TOKEN          Bearer token for the outbound call. How
                            farmer_chat gets a valid one (forwarded farmer
                            token vs. a dedicated service-account token) is
                            still an open question -- this just reads
                            whatever's configured.
  FLOKIQ_PLACEHOLDER_DOCTOR_ID       real users.id in flokiq's DB for the
                                     "Pending Assignment" placeholder.
  FLOKIQ_PLACEHOLDER_ADDED_BY_USER_ID  same, for addedByUserId. Can reuse
                                     an existing system account -- doesn't
                                     have to be a new row.

If either placeholder id is unset, create_appointment() logs a warning and
returns None without calling out -- flokiq's appointments.doctorId/
addedByUserId are NOT NULL FKs, so a call with no value would just 400.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import requests

_log = logging.getLogger("flokiq_sync")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)


def is_enabled() -> bool:
    return os.getenv("FLOKIQ_SYNC_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def _base_url() -> Optional[str]:
    return os.getenv("FLOKIQ_API_BASE_URL")


def _headers() -> dict[str, str]:
    token = os.getenv("FLOKIQ_API_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def create_appointment(
    farmer_id: str,
    date: str,
    time: str,
    notes: str = "",
    health_log_id: Optional[str] = None,
    timeout_s: float = 5.0,
) -> Optional[dict[str, Any]]:
    """POST /appointments on flokiq. Returns the created record, or None if
    sync is disabled/unconfigured/failed -- caller should treat None as
    "not synced this time", not an error, and keep the local record as
    the source of truth for the booking."""
    if not is_enabled():
        return None
    base = _base_url()
    doctor_id = os.getenv("FLOKIQ_PLACEHOLDER_DOCTOR_ID")
    added_by = os.getenv("FLOKIQ_PLACEHOLDER_ADDED_BY_USER_ID")
    if not base:
        _log.warning("flokiq_sync enabled but FLOKIQ_API_BASE_URL unset — skipping")
        return None
    if not doctor_id or not added_by:
        _log.warning(
            "flokiq_sync enabled but placeholder ids unset "
            "(doctor_id=%s added_by=%s) — skipping, appointments.doctorId/"
            "addedByUserId are NOT NULL on flokiq's side",
            bool(doctor_id), bool(added_by),
        )
        return None

    payload = {
        "farmerId": farmer_id,
        "date": date,
        "time": time,
        "doctorId": doctor_id,
        "addedByUserId": added_by,
        "notes": notes,
    }
    if health_log_id:
        payload["healthLogId"] = health_log_id

    try:
        resp = requests.post(f"{base}/appointments", data=payload, headers=_headers(), timeout=timeout_s)
        resp.raise_for_status()
        result = resp.json()
        _log.info("flokiq_sync appointment created id=%s farmer=%s", result.get("id"), farmer_id)
        return result
    except requests.RequestException as exc:
        _log.warning("flokiq_sync create_appointment failed farmer=%s err=%s", farmer_id, exc)
        return None


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
    all today). Works against mock_server.py now; will 404 against the
    real sandbox until flokiq's team builds it. Same best-effort contract
    as create_appointment: None means "not synced," never raises."""
    if not is_enabled():
        return None
    base = _base_url()
    if not base:
        return None
    if not pincode:
        _log.warning("flokiq_sync create_health_log skipped — pincode required (NOT NULL), none available")
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
