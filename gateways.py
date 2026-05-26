from __future__ import annotations

import os
from typing import Any, Optional

import requests

from auth import authenticate
from llm.adapters import get_text_adapter
from models import Animal, Farmer, HealthLog
from storage import (
    animals_for_farmer,
    append_consultation,
    append_health_log,
    consultations_for_farmer,
    farmer_accounts,
    health_logs_for_farmer,
)

SERVICE_MODE_ENV = "APP_MODE"
API_BASE_ENV = "API_SERVICE_URL"
LLM_BASE_ENV = "LLM_SERVICE_URL"


def is_remote_mode() -> bool:
    return os.environ.get(SERVICE_MODE_ENV, "monolith").strip().lower() == "services"


def _api_base() -> str:
    return os.environ.get(API_BASE_ENV, "http://localhost:8001").rstrip("/")


def _llm_base() -> str:
    return os.environ.get(LLM_BASE_ENV, "http://localhost:8002").rstrip("/")


def login(username: str, password: str) -> Optional[Farmer]:
    if not is_remote_mode():
        return authenticate(username, password)

    resp = requests.post(
        f"{_api_base()}/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    if resp.status_code == 401:
        return None
    resp.raise_for_status()
    data = resp.json()
    data["password_hash"] = ""
    return Farmer.model_validate(data)


def list_farmer_accounts() -> list[Farmer]:
    if not is_remote_mode():
        return farmer_accounts()
    resp = requests.get(f"{_api_base()}/farmers", params={"role": "farmer"}, timeout=20)
    resp.raise_for_status()
    rows = resp.json()
    out: list[Farmer] = []
    for r in rows:
        r["password_hash"] = ""
        out.append(Farmer.model_validate(r))
    return out


def list_animals_for_farmer(farmer_id: str) -> list[Animal]:
    if not is_remote_mode():
        return animals_for_farmer(farmer_id)
    resp = requests.get(f"{_api_base()}/farmers/{farmer_id}/animals", timeout=20)
    resp.raise_for_status()
    return [Animal.model_validate(x) for x in resp.json()]


def create_health_log(
    farmer_id: str,
    animal_id: str,
    issue: str,
    params: dict[str, Any],
    notes: str,
) -> HealthLog:
    if not is_remote_mode():
        return append_health_log(farmer_id, animal_id, issue, params, notes)
    resp = requests.post(
        f"{_api_base()}/farmers/{farmer_id}/health-logs",
        json={
            "animal_id": animal_id,
            "issue": issue,
            "params": params,
            "notes": notes,
        },
        timeout=20,
    )
    if resp.status_code == 400:
        raise ValueError(resp.json().get("detail", "Invalid request"))
    resp.raise_for_status()
    return HealthLog.model_validate(resp.json())


def list_health_logs_for_farmer(farmer_id: str) -> list[HealthLog]:
    if not is_remote_mode():
        return health_logs_for_farmer(farmer_id)
    resp = requests.get(f"{_api_base()}/farmers/{farmer_id}/health-logs", timeout=20)
    resp.raise_for_status()
    return [HealthLog.model_validate(x) for x in resp.json()]


def create_consultation(
    farmer_id: str,
    animal_id: Optional[str],
    messages: list[dict[str, str]],
    summary: str,
) -> dict[str, Any]:
    if not is_remote_mode():
        row = append_consultation(farmer_id, animal_id, messages, summary)
        return row.model_dump()
    resp = requests.post(
        f"{_api_base()}/farmers/{farmer_id}/consultations",
        json={
            "animal_id": animal_id,
            "messages": messages,
            "summary": summary,
        },
        timeout=20,
    )
    if resp.status_code == 400:
        raise ValueError(resp.json().get("detail", "Invalid request"))
    resp.raise_for_status()
    return resp.json()


def list_consultations_for_farmer(farmer_id: str) -> list[dict[str, Any]]:
    if not is_remote_mode():
        return consultations_for_farmer(farmer_id)
    resp = requests.get(f"{_api_base()}/farmers/{farmer_id}/consultations", timeout=20)
    resp.raise_for_status()
    return resp.json()


def complete_text(messages: list[dict[str, str]], system: str) -> str:
    if not is_remote_mode():
        return get_text_adapter().complete(messages, system=system)
    resp = requests.post(
        f"{_llm_base()}/chat/complete",
        json={"messages": messages, "system": system},
        timeout=45,
    )
    resp.raise_for_status()
    return str(resp.json().get("content", ""))
