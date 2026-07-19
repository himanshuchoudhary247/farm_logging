"""
FastAPI app for the Farmer Onboarding Service.
Deploy on EC2 alongside the existing Streamlit/FastAPI apps.

Endpoints:
  POST /onboarding  — process a conversation turn
  GET  /onboarding/health — health check

Run:  uvicorn services.farmer_onboarding_service.api:app --host 0.0.0.0 --port 8004
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import FastAPI, Request
from pydantic import BaseModel

from services.farmer_onboarding_service.extraction import quality_check as _quality_check
from services.farmer_onboarding_service.models import OnboardingRequest, OnboardingResponse
from services.farmer_onboarding_service.service import build_final_output, process_turn
from services.weather_alert.service import get_weather_alert, get_seasonal_advisory_data
from storage import save_farmer as _save_farmer, save_farm as _save_farm

# ── Structured logging ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
log = logging.getLogger("onboarding.api")

app = FastAPI(title="Farmer Onboarding Service", version="0.1.0")


class ProcessTurnIn(BaseModel):
    text: str
    existing: Optional[dict[str, Any]] = None
    language: str = "en"
    current_field: Optional[str] = None
    current_section: Optional[str] = None


class SaveRequest(BaseModel):
    farmer: dict[str, Any]
    farm: dict[str, Any]
    login_username: str = ""
    password_hash: str = ""


class SaveResponse(BaseModel):
    farmer_id: str
    farm_id: str
    status: str = "saved"


class HealthOut(BaseModel):
    status: str
    service: str = "farmer-onboarding"


@app.middleware("http")
async def log_timing(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    elapsed = time.time() - t0
    log.info("HTTP %s %s status=%d elapsed=%.2fs", request.method, request.url.path, response.status_code, elapsed)
    return response


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "farmer-onboarding", "docs": "/docs", "health": "/onboarding/health"}


@app.get("/onboarding/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok")


@app.post("/onboarding", response_model=OnboardingResponse)
def onboarding_turn(req: ProcessTurnIn) -> OnboardingResponse:
    log.info("TURN_START lang=%s text=%r current_field=%s farmer_filled=%d farm_filled=%d",
             req.language, req.text, req.current_field,
             len(req.existing.get("farmer", {})) if req.existing else 0,
             len(req.existing.get("farm", {})) if req.existing else 0)
    inner = OnboardingRequest(text=req.text, existing=req.existing, language=req.language)
    resp = process_turn(inner, current_field=req.current_field, current_section=req.current_section)
    log.info("TURN_END extracted_farmer=%d extracted_farm=%d complete=%s missing=%d",
             len(resp.farmer), len(resp.farm), resp.complete, len(resp.missing_fields))
    return resp


@app.post("/onboarding/finalize")
def finalize(data: dict[str, Any]) -> dict[str, Any]:
    farmer = data.get("farmer", {})
    farm = data.get("farm", {})
    log.info("FINALIZE farmer_fields=%d farm_fields=%d", len(farmer), len(farm))
    return build_final_output(farmer, farm)


@app.post("/onboarding/quality-check")
def check_quality(data: dict[str, Any]) -> dict[str, Any]:
    farmer = data.get("farmer", {})
    farm = data.get("farm", {})
    language = data.get("language", "en")
    log.info("QUALITY_CHECK_START farmer=%d farm=%d", len(farmer), len(farm))
    result = _quality_check(farmer, farm, language=language)
    return result


@app.post("/onboarding/save", response_model=SaveResponse)
def onboarding_save(req: SaveRequest) -> SaveResponse:
    farmer_data = req.farmer
    farm_data = req.farm
    log.info("SAVE_START farmer_fields=%d farm_fields=%d", len(farmer_data), len(farm_data))

    farmer = _save_farmer(
        name=farmer_data.get("name", ""),
        phone=farmer_data.get("phone", ""),
        login_username=req.login_username,
        password_hash=req.password_hash,
        onboarding_data=farmer_data,
    )

    farm = _save_farm(
        farmer_id=farmer.id,
        data={
            "name": farm_data.get("name", ""),
            "email": farm_data.get("email", ""),
            "phone": farm_data.get("phone", ""),
            "alternate_phone": farm_data.get("alternate_phone", ""),
            "address": farm_data.get("address", ""),
            "city": farm_data.get("city", ""),
            "district": farm_data.get("district", ""),
            "pincode": farm_data.get("pincode"),
            "state": farm_data.get("state", ""),
            "country": farm_data.get("country", "India"),
            "total_animal_capacity": farm_data.get("total_animal_capacity"),
            "current_animal_count": farm_data.get("current_animal_count", 0),
            "sheep_count": farm_data.get("sheep_count", 0),
            "goat_count": farm_data.get("goat_count", 0),
            "notes": farm_data.get("notes", ""),
        },
    )
    log.info("SAVE_DONE farmer_id=%s farm_id=%s", farmer.id, farm.id)
    return SaveResponse(farmer_id=farmer.id, farm_id=farm.id)


# ── Weather Advisory (LLM-powered) ───────────────────────────────────


class WeatherAlertIn(BaseModel):
    location_or_pin: str
    country_code: str = "in"
    days: int = 3


class SeasonalAdvisoryIn(BaseModel):
    location_or_pin: str
    country_code: str = "in"
    days: int = 7


@app.post("/weather/alert")
def weather_alert(req: WeatherAlertIn) -> dict[str, Any]:
    try:
        return get_weather_alert(
            location_or_pin=req.location_or_pin,
            country_code=req.country_code,
            days=req.days,
        )
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/weather/seasonal-advisory")
def seasonal_advisory(req: SeasonalAdvisoryIn) -> dict[str, Any]:
    try:
        data = get_seasonal_advisory_data(
            location_or_pin=req.location_or_pin,
            country_code=req.country_code,
            days=req.days,
        )
        # Generate LLM advisory using the app's LLM adapter
        import json as _json
        from llm.adapters import get_text_adapter

        llm = get_text_adapter()
        daily = data["forecast"].get("daily") or {}
        dates = daily.get("time") or []
        tmax = daily.get("temperature_2m_max") or []
        tmin = daily.get("temperature_2m_min") or []
        rain = daily.get("precipitation_sum") or []
        wind = daily.get("wind_speed_10m_max") or []

        forecast_lines = []
        for i, d in enumerate(dates):
            forecast_lines.append(
                f"  {d}: high {tmax[i] if i < len(tmax) else '?'}C, low {tmin[i] if i < len(tmin) else '?'}C, "
                f"rain {rain[i] if i < len(rain) else 0}mm, wind {wind[i] if i < len(wind) else 0}km/h"
            )
        forecast_text = "\n".join(forecast_lines) or "No forecast data"
        hist_years = _json.dumps(data["historical"].get("years") or [], indent=2, default=str)
        hist_summary = _json.dumps(data["historical"].get("summary") or {}, indent=2, default=str)

        prompt = f"""You are an expert veterinary epidemiologist assessing weather risk for livestock.

LOCATION: {data['district'] or data['location']}

CURRENT WEEK FORECAST:
{forecast_text}

HISTORICAL DATA (same week, past 5 years):
{hist_summary}

Year-by-year:
{hist_years}

Write an SMS-style weather alert and advisory for sheep and goat farmers in {data['district'] or data['location']}.

Requirements:
1. Compare this week's forecast against the 5-year historical average.
2. If weather is near normal, say "No major deviation from historical pattern. Routine management advised."
3. If unusual (heat wave, heavy rain, cold spell, strong wind), give specific precautions.
4. SEPARATE advisory for:
   - Lambs (young animals)
   - Adults (mature animals)
5. Also separate for:
   - Nomadic farmers
   - Organized/settled farmers
6. Reference ICAR or Department of Animal Husbandry guidelines where relevant.
7. Keep SMS-style: short sentences, bullet points with * prefix, max ~600 characters.
8. Write in clear English suitable for translation.
9. End with: "-- {data['district'] or data['location']} Veterinary Warning"."""

        advisory = llm.complete(
            messages=[{"role": "user", "content": prompt}],
            system="You are an expert veterinary epidemiologist. Write SMS-style livestock weather advisories.",
        )
        advisory = (advisory or "").strip() or "Advisory generation failed."

        return {
            "district": data.get("district") or data.get("location", ""),
            "location": data.get("location", ""),
            "advisory": advisory,
        }
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        msg = str(e)
        if "API key" in msg or "Missing" in msg:
            return {"district": "", "location": req.location_or_pin, "advisory": None, "error": msg}
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=msg)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))
