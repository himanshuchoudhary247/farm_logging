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
    weather_location: str = ""


class Animal(BaseModel):
    id: str
    farmer_id: str
    species: str
    tag_or_name: str
    sex: str = ""
    breed: str = ""
    age_years: Optional[float] = None
    feeding_details: str = ""


class HealthLog(BaseModel):
    id: str
    farmer_id: str
    animal_id: str
    recorded_at: str
    issue: str
    params: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class Appointment(BaseModel):
    id: str
    farmer_id: str
    date: str
    time: str
    status: Literal["pending", "completed", "cancelled", "confirmed", "missed"] = "pending"
    doctor_id: str = ""
    notes: str = ""
    health_log_id: Optional[str] = None
    animal_id: Optional[str] = None
    issue_summary: str = ""
    triage: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


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


class Farm(BaseModel):
    id: str
    farmer_id: str
    name: str = ""
    email: str = ""
    phone: str = ""
    alternate_phone: str = ""
    address: str = ""
    city: str = ""
    district: str = ""
    pincode: Optional[int] = None
    state: str = ""
    country: str = "India"
    total_animal_capacity: Optional[int] = None
    current_animal_count: int = 0
    sheep_count: int = 0
    goat_count: int = 0
    image: str = ""
    notes: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class WeatherNotification(BaseModel):
    id: str
    farmer_id: str
    location_query: str
    risk_level: Literal["low", "medium", "high"]
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
