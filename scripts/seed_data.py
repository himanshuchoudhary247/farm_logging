#!/usr/bin/env python3
"""Generate farmers.json, animals.json, and empty log files under data/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as `python scripts/seed_data.py` from repo root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth import hash_password
from models import Animal, Farmer
from storage import atomic_write_json, get_data_dir

SPECIES = ("cattle", "buffalo", "goat", "sheep", "poultry")
BREEDS = ("Local", "Gir", "Cross", "Desi", "Broiler")


def main() -> None:
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    default_password = "changeme"
    h = hash_password(default_password)
    admin_password = "admin123"
    admin_hash = hash_password(admin_password)

    farmers: list[dict] = [
        Farmer(
            id="admin",
            name="Administrator",
            login_username="admin",
            password_hash=admin_hash,
            phone="",
            role="admin",
        ).model_dump()
    ]
    animals: list[dict] = []
    for i in range(1, 101):
        fid = f"f-{i:03d}"
        farmers.append(
            Farmer(
                id=fid,
                name=f"Farmer {i}",
                login_username=f"farmer{i:03d}",
                password_hash=h,
                phone=f"+910000{i:06d}",
            ).model_dump()
        )
        # 1–3 animals per farmer
        n_anim = 1 + (i % 3)
        for j in range(n_anim):
            aid = f"a-{fid}-{j+1}"
            spec = SPECIES[(i + j) % len(SPECIES)]
            animals.append(
                Animal(
                    id=aid,
                    farmer_id=fid,
                    species=spec,
                    tag_or_name=f"TAG-{i:03d}-{j+1}",
                    breed=BREEDS[(i + j) % len(BREEDS)],
                    age_years=float(1 + (i + j) % 8),
                ).model_dump()
            )

    atomic_write_json(data_dir / "farmers.json", farmers)
    atomic_write_json(data_dir / "animals.json", animals)
    empty: list = []
    atomic_write_json(data_dir / "health_logs.json", empty)
    atomic_write_json(data_dir / "consultations.json", empty)

    print(f"Wrote {len(farmers)} farmers, {len(animals)} animals to {data_dir}")
    print(f"Default login: farmer001 / {default_password}")
    print(f"Admin login: admin / {admin_password}")


if __name__ == "__main__":
    main()
