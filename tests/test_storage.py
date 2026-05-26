from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def storage_mod(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FARMER_CHAT_DATA_DIR", str(tmp_path))
    import storage

    importlib.reload(storage)
    return storage


def test_append_health_log_scoped(storage_mod, tmp_path: Path) -> None:
    from models import Animal, Farmer

    farmers = [
        Farmer(
            id="f-1",
            name="A",
            login_username="a",
            password_hash="x",
            phone="",
        ).model_dump(),
        Farmer(
            id="f-2",
            name="B",
            login_username="b",
            password_hash="x",
            phone="",
        ).model_dump(),
    ]
    animals = [
        Animal(
            id="an-1",
            farmer_id="f-1",
            species="cattle",
            tag_or_name="T1",
        ).model_dump(),
        Animal(
            id="an-2",
            farmer_id="f-2",
            species="goat",
            tag_or_name="T2",
        ).model_dump(),
    ]
    storage_mod.atomic_write_json(tmp_path / "farmers.json", farmers)
    storage_mod.atomic_write_json(tmp_path / "animals.json", animals)
    storage_mod.atomic_write_json(tmp_path / "health_logs.json", [])
    storage_mod.atomic_write_json(tmp_path / "consultations.json", [])

    row = storage_mod.append_health_log("f-1", "an-1", "cough", {"appetite": "normal"}, "")
    assert row.farmer_id == "f-1"
    assert row.animal_id == "an-1"

    with pytest.raises(ValueError):
        storage_mod.append_health_log("f-1", "an-2", "x", {}, "")

    logs = storage_mod.health_logs_for_farmer("f-1")
    assert len(logs) == 1
    assert storage_mod.health_logs_for_farmer("f-2") == []


def test_atomic_write_json(storage_mod, tmp_path: Path) -> None:
    p = tmp_path / "test.json"
    storage_mod.atomic_write_json(p, {"a": 1})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1}
