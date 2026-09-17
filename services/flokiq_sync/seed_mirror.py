"""Seed the local mirror DB (docker-compose.yml + flokiq_mirror_schema.sql)
with just enough parent rows to satisfy FK constraints for farmer_chat's
own seeded demo account (scripts/seed_demo_user.py), so a real booking turn
can be driven end-to-end through flokiq_sync without touching the real
sandbox.

IDs deliberately mirror scripts/seed_demo_user.py's DEMO_FARMER_ID and
animal ids -- farmer_chat's own appointment_supervisor.submit() passes the
same farmer_id string as BOTH appointments.farmerId (FK -> farmers.id) and
health_logs.user_id (FK -> users.id), so one users row and one farmers row,
both keyed 'demo-farmer', satisfy both call sites.

Run after `docker compose -f services/flokiq_sync/docker-compose.yml up -d`:
    python services/flokiq_sync/seed_mirror.py
"""
from __future__ import annotations

import os
from datetime import datetime

import pymysql

DB_CONFIG = dict(
    host=os.getenv("FLOKIQ_MIRROR_HOST", "127.0.0.1"),
    port=int(os.getenv("FLOKIQ_MIRROR_PORT", "3399")),
    user="root",
    password="localtest",
    database="flokiq_mirror",
)

DEMO_FARMER_ID = "demo-farmer"
DEMO_FARM_ID = "demo-farm"
DEMO_VET_ID = "demo-vet-user"

ANIMALS = [
    ("demo-animal-sheep-01", "sheep", "female"),
    ("demo-animal-sheep-02", "sheep", "female"),
    ("demo-animal-goat-01", "goat", "female"),
    ("demo-animal-goat-02", "goat", "male"),
]


def main() -> None:
    now = datetime.utcnow()
    conn = pymysql.connect(**DB_CONFIG, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            for user_id in (DEMO_FARMER_ID, DEMO_VET_ID):
                cur.execute(
                    """INSERT INTO users (id, firstName, role, createdAt, updatedAt)
                       VALUES (%s, %s, 'farmer', %s, %s)
                       ON DUPLICATE KEY UPDATE updatedAt = VALUES(updatedAt)""",
                    (user_id, user_id, now, now),
                )

            cur.execute(
                """INSERT INTO farmers (id, userId, createdAt, updatedAt)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE updatedAt = VALUES(updatedAt)""",
                (DEMO_FARMER_ID, DEMO_FARMER_ID, now, now),
            )

            cur.execute(
                """INSERT INTO farms (id, farmerId, name, phone, createdAt, updatedAt)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE updatedAt = VALUES(updatedAt)""",
                (DEMO_FARM_ID, DEMO_FARMER_ID, "Green Valley Demo Farm", "+910000000000", now, now),
            )

            for animal_id, species, sex in ANIMALS:
                cur.execute(
                    """INSERT INTO animals
                       (id, farmId, unique_animal_id, species, sex, createdAt, updatedAt)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE updatedAt = VALUES(updatedAt)""",
                    (animal_id, DEMO_FARM_ID, animal_id, species, sex, now, now),
                )
        conn.commit()
    finally:
        conn.close()

    print("Seeded flokiq_mirror:")
    print(f"  users:   {DEMO_FARMER_ID}, {DEMO_VET_ID}")
    print(f"  farmers: {DEMO_FARMER_ID}")
    print(f"  farms:   {DEMO_FARM_ID}")
    print(f"  animals: {', '.join(a[0] for a in ANIMALS)}")
    print()
    print("Set in .env for this test loop:")
    print("  FLOKIQ_SYNC_ENABLED=true")
    print("  FLOKIQ_API_BASE_URL=http://localhost:8077")
    print(f"  FLOKIQ_PLACEHOLDER_DOCTOR_ID={DEMO_VET_ID}")
    print(f"  FLOKIQ_PLACEHOLDER_ADDED_BY_USER_ID={DEMO_VET_ID}")


if __name__ == "__main__":
    main()
