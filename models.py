from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Farmer(BaseModel):
    id: str
    name: str
    login_username: str
    password_hash: str
    phone: str = ""
    role: Literal["farmer", "admin"] = "farmer"


class Animal(BaseModel):
    id: str
    farmer_id: str
    species: str
    tag_or_name: str
    breed: str = ""
    age_years: Optional[float] = None


class HealthLog(BaseModel):
    id: str
    farmer_id: str
    animal_id: str
    recorded_at: str
    issue: str
    params: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class Consultation(BaseModel):
    id: str
    farmer_id: str
    animal_id: Optional[str] = None
    started_at: str
    messages: list[ChatMessage]
    status: Literal["draft", "saved"] = "draft"
    summary: str = ""
