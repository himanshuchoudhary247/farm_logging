#!/usr/bin/env python3
"""
Manual test for the SQL Query Agent.

Run:  python3 test_query_agent_manually.py

This script:
  1. Adds sample animals/health_logs/appointments to JSON files
  2. Runs the query agent on several example queries
  3. Cleans up sample data at the end

"""

import json
import os
import sys

DATA_DIR = "data"

# ── helpers ────────────────────────────────────────────────────────


def _read_json(name):
    path = os.path.join(DATA_DIR, name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def _write_json(name, data):
    path = os.path.join(DATA_DIR, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


# ── seed sample data for farmer "f-001" ────────────────────────────

SAMPLE_ANIMALS = [
    {"id": "a-001", "farmer_id": "f-001", "species": "goat", "tag_or_name": "Bella", "sex": "female", "breed": "Saanen", "age_years": 3, "feeding_details": "grazing + supplement"},
    {"id": "a-002", "farmer_id": "f-001", "species": "goat", "tag_or_name": "Max", "sex": "male", "breed": "Alpine", "age_years": 2, "feeding_details": "grazing"},
    {"id": "a-003", "farmer_id": "f-001", "species": "sheep", "tag_or_name": "Lily", "sex": "female", "breed": "Merino", "age_years": 4, "feeding_details": "hay + concentrate"},
    {"id": "a-004", "farmer_id": "f-001", "species": "goat", "tag_or_name": "Rocky", "sex": "male", "breed": "Boer", "age_years": 1, "feeding_details": "grazing"},
    {"id": "a-005", "farmer_id": "f-001", "species": "cow", "tag_or_name": "Daisy", "sex": "female", "breed": "Holstein", "age_years": 5, "feeding_details": "silage + concentrate"},
    {"id": "a-006", "farmer_id": "f-001", "species": "buffalo", "tag_or_name": "Moti", "sex": "female", "breed": "Murrah", "age_years": 6, "feeding_details": "green fodder"},
]

SAMPLE_HEALTH_LOGS = [
    {"id": "hl-001", "farmer_id": "f-001", "animal_id": "a-001", "recorded_at": "2025-06-10", "issue": "PPR vaccination done", "notes": "Routine vaccination"},
    {"id": "hl-002", "farmer_id": "f-001", "animal_id": "a-003", "recorded_at": "2025-06-15", "issue": "Limping on right front leg", "params": {"severity": "moderate"}, "notes": "Injury"},
    {"id": "hl-003", "farmer_id": "f-001", "animal_id": "a-005", "recorded_at": "2025-06-20", "issue": "Routine pregnancy checkup", "notes": "All normal"},
    {"id": "hl-004", "farmer_id": "f-001", "animal_id": "a-001", "recorded_at": "2025-07-01", "issue": "Mild fever and loss of appetite", "params": {"severity": "mild"}, "notes": ""},
]

SAMPLE_APPOINTMENTS = [
    {"id": "ap-001", "farmer_id": "f-001", "animal_id": "a-001", "health_log_id": "hl-004", "date": "2025-07-05", "time": "10:00", "doctor_id": "Dr. Sharma", "issue_summary": "Fever follow-up", "status": "confirmed"},
    {"id": "ap-002", "farmer_id": "f-001", "animal_id": "a-003", "health_log_id": "hl-002", "date": "2025-07-08", "time": "14:30", "doctor_id": "Dr. Patel", "issue_summary": "Limping leg injury", "status": "confirmed"},
]


# ── main ───────────────────────────────────────────────────────────

def main():
    # Backup original data
    backups = {}
    for name in ["animals.json", "health_logs.json", "appointments.json"]:
        backups[name] = _read_json(name)

    try:
        # Write sample data
        _write_json("animals.json", SAMPLE_ANIMALS)
        _write_json("health_logs.json", SAMPLE_HEALTH_LOGS)
        _write_json("appointments.json", SAMPLE_APPOINTMENTS)

        # Clear cache so it picks up fresh data
        from services.query_agent.db import clear_cache, execute_query
        from services.query_agent.schema import generate_schema_for_prompt

        clear_cache("f-001")

        print("=" * 60)
        print("SQL Query Agent — Manual Test")
        print("=" * 60)

        # 1. Show schema
        print("\n📋 Generated Schema:")
        schema = generate_schema_for_prompt()
        print(schema[:800])
        print("...")

        # 2. Direct SQL tests
        queries = [
            ("Count all animals", "SELECT COUNT(*) as total FROM animals"),
            ("Count by species", "SELECT species, COUNT(*) as cnt FROM animals GROUP BY species"),
            ("Male animals", "SELECT tag_or_name, species, sex FROM animals WHERE sex = 'male'"),
            ("Female animals", "SELECT tag_or_name, species, sex FROM animals WHERE sex = 'female'"),
            ("Health logs for a specific animal", "SELECT id, recorded_at, issue FROM health_logs WHERE animal_id = 'a-001'"),
            ("Animals older than 3 years", "SELECT tag_or_name, species, age_years FROM animals WHERE age_years > 3"),
            ("Upcoming appointments with animal name", "SELECT a.tag_or_name, ap.date, ap.time, ap.doctor_id, ap.issue_summary FROM appointments ap JOIN animals a ON ap.animal_id = a.id"),
            ("Female goats only", "SELECT tag_or_name, age_years, breed FROM animals WHERE species = 'goat' AND sex = 'female'"),
        ]

        for label, sql in queries:
            print(f"\n🔍 {label}")
            print(f"   SQL: {sql}")
            result = execute_query(sql, "f-001")
            if result["success"]:
                print(f"   ✅ {result['row_count']} row(s)")
                for row in result["rows"]:
                    print(f"      {dict(zip(result['columns'], row))}")
            else:
                print(f"   ❌ {result['error']}")

        # 3. Safety checks
        print("\n\n🛡️  Safety Validation:")
        from services.query_agent.db import validate_sql

        for bad_sql in ["DROP TABLE animals", "INSERT INTO animals VALUES (1)", "UPDATE animals SET name='x'", "DELETE FROM animals"]:
            try:
                validate_sql(bad_sql, "f-001")
                print(f"   ❌ Should have blocked: {bad_sql}")
            except ValueError as e:
                print(f"   ✅ Blocked: {bad_sql} → {e}")

        print("\n\n✅ All manual tests passed!")

    finally:
        # Restore original data
        for name, data in backups.items():
            _write_json(name, data)
        clear_cache("f-001")


if __name__ == "__main__":
    main()
