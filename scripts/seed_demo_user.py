#!/usr/bin/env python3
"""Seed one clearly synthetic FarmHerd showcase account.

This script only replaces records with the reserved demo identifiers and
preserves all other data in the configured data directory.
"""

from __future__ import annotations

import sys

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth import hash_password
from models import Animal, Appointment, Farm, Farmer, HealthLog, utc_now_iso
from storage import atomic_write_json, get_data_dir


DEMO_FARMER_ID = "demo-farmer"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "farmherd-demo"


def _load(path):
    if not path.exists():
        return []
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _replace_by_id(rows, row):
    rows = [item for item in rows if item.get("id") != row["id"]]
    rows.append(row)
    return rows


def main() -> None:
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    farmer = Farmer(
        id=DEMO_FARMER_ID,
        name="Ravi (Demo Farmer)",
        login_username=DEMO_USERNAME,
        password_hash=hash_password(DEMO_PASSWORD),
        phone="+910000000000",
        role="farmer",
        weather_location="583101",
    ).model_dump()
    farm = Farm(
        id="demo-farm",
        farmer_id=DEMO_FARMER_ID,
        name="Green Valley Demo Farm",
        district="Ballari",
        state="Karnataka",
        pincode=583101,
        country="India",
        current_animal_count=12,
        sheep_count=8,
        goat_count=4,
        notes="Synthetic showcase farm. Not real farmer data.",
    ).model_dump()
    animals = [
        Animal(id="demo-animal-sheep-01", farmer_id=DEMO_FARMER_ID, species="sheep", tag_or_name="Lakshmi", breed="Deccani", sex="female", age_years=2.5, feeding_details="Green fodder morning and evening").model_dump(),
        Animal(id="demo-animal-sheep-02", farmer_id=DEMO_FARMER_ID, species="sheep", tag_or_name="Malli", breed="Deccani", sex="female", age_years=3.0, feeding_details="Dry fodder and mineral mix").model_dump(),
        Animal(id="demo-animal-goat-01", farmer_id=DEMO_FARMER_ID, species="goat", tag_or_name="Gauri", breed="Sirohi", sex="female", age_years=2.0, feeding_details="Browse and supplemental maize").model_dump(),
        Animal(id="demo-animal-goat-02", farmer_id=DEMO_FARMER_ID, species="goat", tag_or_name="Kanna", breed="Sirohi", sex="male", age_years=1.5, feeding_details="Browse and clean water").model_dump(),
    ]
    health_logs = [
        HealthLog(id="demo-health-01", farmer_id=DEMO_FARMER_ID, animal_id="demo-animal-sheep-01", recorded_at="2026-08-12T07:30:00+00:00", issue="mild foot swelling after wet grazing", params={"severity": "mild", "temperature_c": 39.1}, notes="Rinsed hoof and moved flock to dry bedding.").model_dump(),
        HealthLog(id="demo-health-02", farmer_id=DEMO_FARMER_ID, animal_id="demo-animal-goat-01", recorded_at="2026-08-14T08:15:00+00:00", issue="reduced appetite", params={"severity": "monitor"}, notes="Eating less than usual; monitoring water intake.").model_dump(),
    ]
    appointment = Appointment(id="demo-appointment-01", farmer_id=DEMO_FARMER_ID, date="2026-08-20", time="10:00", status="pending", doctor_id="demo-vet", notes="Follow up on foot swelling", animal_id="demo-animal-sheep-01", issue_summary="Foot health review", triage={}).model_dump()

    files = {
        "farmers.json": [farmer],
        "farms.json": [farm],
        "animals.json": animals,
        "health_logs.json": health_logs,
        "appointments.json": [appointment],
        "consultations.json": [],
        "weather_notifications.json": [],
    }
    for filename, rows in files.items():
        path = data_dir / filename
        existing = _load(path)
        if filename == "farmers.json":
            existing = [item for item in existing if item.get("id") != DEMO_FARMER_ID and item.get("login_username") != DEMO_USERNAME]
            rows = existing + rows
        elif filename == "farms.json":
            rows = [item for item in existing if item.get("farmer_id") != DEMO_FARMER_ID] + rows
        elif filename in {"animals.json", "health_logs.json", "appointments.json"}:
            rows = [item for item in existing if item.get("farmer_id") != DEMO_FARMER_ID] + rows
        atomic_write_json(path, rows)

    print(f"Seeded synthetic demo account in {data_dir}")
    print(f"Login: {DEMO_USERNAME} / {DEMO_PASSWORD}")
    print(f"Farmer ID: {DEMO_FARMER_ID}; PIN: 583101")


if __name__ == "__main__":
    main()
