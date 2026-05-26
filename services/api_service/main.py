from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from utils.env_check import validate_env
from pydantic import BaseModel, Field

from auth import authenticate
from models import ChatMessage, Consultation, Farmer, HealthLog
from storage import (
    animals_for_farmer,
    append_consultation,
    append_health_log,
    consultations_for_farmer,
    farmer_accounts,
    health_logs_for_farmer,
)
from services.voice_agent.extractor import detect_intent, extract_health_log
from difflib import get_close_matches


app = FastAPI(title="Farmer Chat API Service", version="0.1.0")

# Validate env at startup
validate_env()


class LoginRequest(BaseModel):
    username: str
    password: str


class FarmerPublic(BaseModel):
    id: str
    name: str
    login_username: str
    phone: str = ""
    role: str


class CreateHealthLogRequest(BaseModel):
    animal_id: str
    issue: str
    params: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class CreateConsultationRequest(BaseModel):
    animal_id: Optional[str] = None
    messages: list[ChatMessage]
    summary: str


class VoiceHealthLogRequest(BaseModel):
    text: str


class VoiceHealthLogConfirmRequest(BaseModel):
    animal_id: str
    issue: str
    params: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


def to_public_farmer(f: Farmer) -> FarmerPublic:
    return FarmerPublic(
        id=f.id,
        name=f.name,
        login_username=f.login_username,
        phone=f.phone,
        role=f.role,
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/login", response_model=FarmerPublic)
def login(req: LoginRequest) -> FarmerPublic:
    f = authenticate(req.username, req.password)
    if f is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return to_public_farmer(f)


@app.get("/farmers", response_model=list[FarmerPublic])
def list_farmers(role: Optional[str] = None) -> list[FarmerPublic]:
    if role == "farmer":
        return [to_public_farmer(x) for x in farmer_accounts()]
    raise HTTPException(status_code=400, detail="Only role=farmer is supported")


@app.get("/farmers/{farmer_id}/animals")
def list_animals(farmer_id: str) -> list[dict[str, Any]]:
    return [a.model_dump() for a in animals_for_farmer(farmer_id)]


@app.get("/farmers/{farmer_id}/health-logs")
def list_health_logs(farmer_id: str) -> list[dict[str, Any]]:
    return [x.model_dump() for x in health_logs_for_farmer(farmer_id)]


@app.post("/farmers/{farmer_id}/health-logs", response_model=HealthLog)
def create_health_log(farmer_id: str, req: CreateHealthLogRequest) -> HealthLog:
    try:
        return append_health_log(
            farmer_id=farmer_id,
            animal_id=req.animal_id,
            issue=req.issue,
            params=req.params,
            notes=req.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/farmers/{farmer_id}/consultations")
def list_consultations(farmer_id: str) -> list[dict[str, Any]]:
    return consultations_for_farmer(farmer_id)


@app.post("/farmers/{farmer_id}/consultations", response_model=Consultation)
def create_consultation(farmer_id: str, req: CreateConsultationRequest) -> Consultation:
    try:
        return append_consultation(
            farmer_id=farmer_id,
            animal_id=req.animal_id,
            messages=[m.model_dump() for m in req.messages],
            summary=req.summary,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/farmers/{farmer_id}/voice/health-log")
def voice_health_log(farmer_id: str, req: VoiceHealthLogRequest) -> dict[str, Any]:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty input")

    intent = detect_intent(text)
    if "health" not in intent:
        return {"intent": intent, "message": "Not a health log request"}

    data = extract_health_log(text)

    # resolve animal name -> id (best-effort fuzzy match)
    animals = animals_for_farmer(farmer_id)
    name = (data.get("animal") or "").strip().lower()
    resolved_id = None
    if name and animals:
        labels = {f"{a.tag_or_name} {a.species}".lower(): a.id for a in animals}
        matches = get_close_matches(name, list(labels.keys()), n=1, cutoff=0.5)
        if matches:
            resolved_id = labels[matches[0]]
    if resolved_id:
        data["animal_id"] = resolved_id

    missing = []
    if not data.get("animal_id"):
        missing.append("animal_id")
    if not data.get("issue"):
        missing.append("issue")

    return {
        "intent": "health_log",
        "extracted": data,
        "missing_fields": missing,
    }


@app.post("/farmers/{farmer_id}/voice/health-log/confirm", response_model=HealthLog)
def confirm_voice_health_log(farmer_id: str, req: VoiceHealthLogConfirmRequest) -> HealthLog:
    try:
        return append_health_log(
            farmer_id=farmer_id,
            animal_id=req.animal_id,
            issue=req.issue,
            params=req.params,
            notes=req.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
