from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from utils.env_check import validate_env
from pydantic import BaseModel, Field

from auth import authenticate
from models import Animal, Appointment, ChatMessage, Consultation, Farmer, HealthLog, WeatherNotification
from storage import (
    animals_for_farmer,
    appointments_for_farmer,
    append_weather_notification,
    append_animal,
    append_appointment,
    append_consultation,
    append_health_log,
    consultations_for_farmer,
    get_farmer_by_id,
    farmer_accounts,
    health_logs_for_farmer,
    update_farmer_weather_location,
    update_animal,
    weather_notifications_for_farmer,
)
from services.voice_agent.extractor import detect_intent, extract_health_log
from services.weather_alert.service import get_weather_alert
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


class CreateAnimalRequest(BaseModel):
    tag_or_name: str
    species: str
    sex: str = ""
    breed: str = ""
    age_years: Optional[float] = None
    feeding_details: str = ""


class UpdateAnimalRequest(BaseModel):
    animal_id: Optional[str] = None
    animal_name: Optional[str] = None
    species: Optional[str] = None
    sex: Optional[str] = None
    breed: Optional[str] = None
    age_years: Optional[float] = None
    feeding_details: Optional[str] = None


class CreateConsultationRequest(BaseModel):
    animal_id: Optional[str] = None
    messages: list[ChatMessage]
    summary: str


class CreateAppointmentRequest(BaseModel):
    date: str
    time: str
    doctor_id: str = ""
    notes: str = ""
    health_log_id: Optional[str] = None
    animal_id: Optional[str] = None
    issue_summary: str = ""
    triage: dict[str, Any] = Field(default_factory=dict)


class CreatePreconsultAppointmentRequest(BaseModel):
    animal_id: str
    issue: str
    date: str
    time: str
    duration: str = ""
    severity: str = ""
    current_medication: str = ""
    temperature_c: Optional[float] = None
    doctor_id: str = ""
    notes: str = ""


class VoiceHealthLogRequest(BaseModel):
    text: str


class VoiceHealthLogConfirmRequest(BaseModel):
    animal_id: str
    issue: str
    params: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class WeatherAlertRequest(BaseModel):
    location_or_pin: str
    country_code: str = "in"
    days: int = 3


class WeatherPreferenceRequest(BaseModel):
    weather_location: str


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


@app.post("/farmers/{farmer_id}/animals", response_model=Animal)
def create_animal(farmer_id: str, req: CreateAnimalRequest) -> Animal:
    return append_animal(
        farmer_id=farmer_id,
        tag_or_name=req.tag_or_name,
        species=req.species,
        sex=req.sex,
        breed=req.breed,
        age_years=req.age_years,
        feeding_details=req.feeding_details,
    )


@app.patch("/farmers/{farmer_id}/animals", response_model=Animal)
def patch_animal(farmer_id: str, req: UpdateAnimalRequest) -> Animal:
    try:
        return update_animal(
            farmer_id=farmer_id,
            animal_id=req.animal_id,
            animal_name=req.animal_name,
            updates={
                "species": req.species,
                "sex": req.sex,
                "breed": req.breed,
                "age_years": req.age_years,
                "feeding_details": req.feeding_details,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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


@app.get("/farmers/{farmer_id}/appointments")
def list_appointments(farmer_id: str) -> list[dict[str, Any]]:
    return [x.model_dump() for x in appointments_for_farmer(farmer_id)]


@app.post("/farmers/{farmer_id}/appointments", response_model=Appointment)
def create_appointment(farmer_id: str, req: CreateAppointmentRequest) -> Appointment:
    try:
        return append_appointment(
            farmer_id=farmer_id,
            date=req.date,
            time=req.time,
            doctor_id=req.doctor_id,
            notes=req.notes,
            health_log_id=req.health_log_id,
            animal_id=req.animal_id,
            issue_summary=req.issue_summary,
            triage=req.triage,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/farmers/{farmer_id}/appointments/preconsult")
def create_preconsult_appointment(
    farmer_id: str, req: CreatePreconsultAppointmentRequest
) -> dict[str, Any]:
    triage = {
        "duration": req.duration,
        "severity": req.severity,
        "current_medication": req.current_medication,
        "temperature_c": req.temperature_c,
    }

    try:
        health = append_health_log(
            farmer_id=farmer_id,
            animal_id=req.animal_id,
            issue=req.issue,
            params=triage,
            notes=req.notes,
        )
        appt = append_appointment(
            farmer_id=farmer_id,
            date=req.date,
            time=req.time,
            doctor_id=req.doctor_id,
            notes=req.notes,
            health_log_id=health.id,
            animal_id=req.animal_id,
            issue_summary=req.issue,
            triage=triage,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "ok",
        "health_log": health.model_dump(),
        "appointment": appt.model_dump(),
    }


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


@app.post("/weather/alert")
def weather_alert(req: WeatherAlertRequest) -> dict[str, Any]:
    try:
        return get_weather_alert(
            location_or_pin=req.location_or_pin,
            country_code=req.country_code,
            days=req.days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/farmers/{farmer_id}/weather-preference")
def get_weather_preference(farmer_id: str) -> dict[str, Any]:
    farmer = get_farmer_by_id(farmer_id)
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return {"farmer_id": farmer_id, "weather_location": farmer.weather_location}


@app.patch("/farmers/{farmer_id}/weather-preference")
def patch_weather_preference(farmer_id: str, req: WeatherPreferenceRequest) -> dict[str, Any]:
    try:
        farmer = update_farmer_weather_location(farmer_id, req.weather_location)
        return {"farmer_id": farmer_id, "weather_location": farmer.weather_location}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/farmers/{farmer_id}/weather-notifications")
def list_weather_notifications(farmer_id: str) -> list[dict[str, Any]]:
    return [x.model_dump() for x in weather_notifications_for_farmer(farmer_id)]


@app.post("/farmers/{farmer_id}/weather-notifications", response_model=WeatherNotification)
def create_weather_notification(farmer_id: str, req: WeatherAlertRequest) -> WeatherNotification:
    try:
        alert = get_weather_alert(
            location_or_pin=req.location_or_pin,
            country_code=req.country_code,
            days=req.days,
        )
        return append_weather_notification(
            farmer_id=farmer_id,
            location_query=req.location_or_pin,
            risk_level=str(alert.get("risk_level") or "low"),
            summary=str(alert.get("summary") or ""),
            details=alert,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
