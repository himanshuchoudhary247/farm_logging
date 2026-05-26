#!/usr/bin/env python3
"""Insert an admin row into farmers.json if it does not exist (keeps existing farmers)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth import hash_password
from models import Farmer
from storage import atomic_write_json, get_data_dir, load_farmers

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"


def main() -> None:
    rows = [f.model_dump() for f in load_farmers()]
    if any(r.get("login_username", "").strip().lower() == DEFAULT_USERNAME for r in rows):
        print(f"User '{DEFAULT_USERNAME}' already exists — not changed.")
        return
    rows.insert(
        0,
        Farmer(
            id="admin",
            name="Administrator",
            login_username=DEFAULT_USERNAME,
            password_hash=hash_password(DEFAULT_PASSWORD),
            phone="",
            role="admin",
        ).model_dump(),
    )
    atomic_write_json(get_data_dir() / "farmers.json", rows)
    print(f"Added admin user: {DEFAULT_USERNAME} / {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    main()
