"""Local mock of the flokiq backend, backed by the schema-only mirror DB
(docker-compose.yml + data/flokiq_mirror_schema.sql).

Lets farmer_chat's flokiq_sync client be tested end-to-end — real INSERTs,
real FK/enum constraint failures (species enum, doctorId FK) — without any
network call to the actual sandbox, and without a single row of real
farmer data ever leaving flokiq-sandbox.

Two endpoints:
  POST /appointments           — real, matches flokiquser's src/lib/apis.ts
                                  exactly (FormData, confirmed against the
                                  actual frontend source, not guessed).
  POST /internal/health-logs   — matches the real main_backend route
                                  (main_backend PR #14): JSON body,
                                  farmerId (not a raw user_id) resolved to
                                  farmers.userId server-side, same as the
                                  real controller does.

Run:
    docker compose -f services/flokiq_sync/docker-compose.yml up -d
    pip install fastapi uvicorn pymysql python-multipart
    uvicorn services.flokiq_sync.mock_server:app --port 8077
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, date
from typing import Optional

import pymysql
from fastapi import FastAPI, Form, HTTPException
from pydantic import BaseModel

app = FastAPI(title="flokiq mock backend (local mirror DB only)")

DB_CONFIG = dict(
    host=os.getenv("FLOKIQ_MIRROR_HOST", "127.0.0.1"),
    port=int(os.getenv("FLOKIQ_MIRROR_PORT", "3399")),
    user="root",
    password="localtest",
    database="flokiq_mirror",
    cursorclass=pymysql.cursors.DictCursor,
)


def _conn():
    return pymysql.connect(**DB_CONFIG, connect_timeout=5)


@app.post("/appointments")
def create_appointment(
    farmerId: str = Form(...),
    date_: str = Form(..., alias="date"),
    time: str = Form(...),
    doctorId: str = Form(...),
    addedByUserId: str = Form(...),
    notes: str = Form(""),
    healthLogId: Optional[str] = Form(None),
):
    appt_id = str(uuid.uuid4())
    now = datetime.utcnow()
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO appointments
                   (id, farmerId, date, time, status, addedByUserId, doctorId, notes, healthLogId, createdAt, updatedAt)
                   VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s)""",
                (appt_id, farmerId, date_, time, addedByUserId, doctorId, notes, healthLogId, now, now),
            )
        conn.commit()
        conn.close()
    except pymysql.err.IntegrityError as exc:
        raise HTTPException(status_code=400, detail=f"constraint violation: {exc}")
    return {"id": appt_id, "farmerId": farmerId, "date": date_, "time": time, "status": "pending"}


class HealthLogBody(BaseModel):
    farmerId: str
    pincode: str
    symptomsReported: list[str]
    animalId: Optional[str] = None
    riskLevel: Optional[str] = None
    aiDiagnosisSuggestion: Optional[str] = None
    potentialAilments: Optional[list[str]] = None
    firstAidAdvice: Optional[str] = None


@app.post("/internal/health-logs")
def create_health_log(body: HealthLogBody):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            # Same resolution the real main_backend route does: the
            # caller only ever knows its own farmerId, never main_backend's
            # internal user id.
            cur.execute("SELECT userId FROM farmers WHERE id = %s", (body.farmerId,))
            farmer = cur.fetchone()
            if farmer is None:
                raise HTTPException(status_code=404, detail="Farmer not found")
            user_id = farmer["userId"]

            log_id = str(uuid.uuid4())
            now = datetime.utcnow()
            cur.execute(
                """INSERT INTO health_logs
                   (log_id, user_id, animal_id, pincode, symptoms_reported, risk_level,
                    ai_diagnosis_suggestion, potential_ailments, first_aid_advice,
                    log_timestamp, createdAt, updatedAt)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    log_id, user_id, body.animalId, body.pincode,
                    json.dumps(body.symptomsReported), body.riskLevel,
                    body.aiDiagnosisSuggestion,
                    json.dumps(body.potentialAilments) if body.potentialAilments is not None else None,
                    body.firstAidAdvice, now, now, now,
                ),
            )
        conn.commit()
    except pymysql.err.IntegrityError as exc:
        raise HTTPException(status_code=400, detail=f"constraint violation: {exc}")
    finally:
        conn.close()
    return {"log_id": log_id}


@app.get("/_mirror/appointments/{appointment_id}")
def debug_get_appointment(appointment_id: str):
    """Test-only introspection endpoint, not part of the real flokiq API —
    lets tests assert on what actually landed in the mirror DB."""
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
        row = cur.fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404)
    return row
