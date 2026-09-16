"""Local mock of the flokiq backend, backed by the schema-only mirror DB
(docker-compose.yml + data/flokiq_mirror_schema.sql).

Lets farmer_chat's flokiq_sync client be tested end-to-end — real INSERTs,
real FK/enum constraint failures (species enum, doctorId FK) — without any
network call to the actual sandbox, and without a single row of real
farmer data ever leaving flokiq-sandbox.

Two endpoints:
  POST /appointments        — real, matches flokiquser's src/lib/apis.ts
                               exactly (FormData, confirmed against the
                               actual frontend source, not guessed).
  POST /health-logs         — PROPOSED, does not exist on the real flokiq
                               backend yet. flokiquser's apis.ts has no
                               health-log creation call at all, only a GET
                               to fetch one and a POST for vaccination
                               schedules. This is here so we can validate
                               the payload shape we'd want flokiq's team to
                               build, against the real health_logs
                               constraints — not a claim that this URL
                               exists anywhere else.

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


@app.post("/health-logs")
def create_health_log(
    user_id: str = Form(...),
    animal_id: Optional[str] = Form(None),
    pincode: str = Form(...),
    symptoms_reported: str = Form(...),  # JSON-encoded list, e.g. '["fever","not eating"]'
    risk_level: Optional[str] = Form(None),
    ai_diagnosis_suggestion: Optional[str] = Form(None),
    potential_ailments: Optional[str] = Form(None),  # JSON-encoded list
    first_aid_advice: Optional[str] = Form(None),
):
    try:
        json.loads(symptoms_reported)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="symptoms_reported must be a JSON array string")

    log_id = str(uuid.uuid4())
    now = datetime.utcnow()
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO health_logs
                   (log_id, user_id, animal_id, pincode, symptoms_reported, risk_level,
                    ai_diagnosis_suggestion, potential_ailments, first_aid_advice,
                    log_timestamp, createdAt, updatedAt)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (log_id, user_id, animal_id, pincode, symptoms_reported, risk_level,
                 ai_diagnosis_suggestion, potential_ailments, first_aid_advice, now, now, now),
            )
        conn.commit()
        conn.close()
    except pymysql.err.IntegrityError as exc:
        raise HTTPException(status_code=400, detail=f"constraint violation: {exc}")
    return {"log_id": log_id, "user_id": user_id, "risk_level": risk_level}


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
