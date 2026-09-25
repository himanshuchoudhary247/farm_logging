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
    storage_mod.atomic_write_json(tmp_path / "appointments.json", [])
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


def test_append_appointment_links_health_log(storage_mod, tmp_path: Path) -> None:
    from models import Animal, Farmer

    farmers = [
        Farmer(
            id="f-1",
            name="A",
            login_username="a",
            password_hash="x",
            phone="",
        ).model_dump()
    ]
    animals = [
        Animal(
            id="an-1",
            farmer_id="f-1",
            species="goat",
            tag_or_name="T1",
        ).model_dump()
    ]
    storage_mod.atomic_write_json(tmp_path / "farmers.json", farmers)
    storage_mod.atomic_write_json(tmp_path / "animals.json", animals)
    storage_mod.atomic_write_json(tmp_path / "health_logs.json", [])
    storage_mod.atomic_write_json(tmp_path / "appointments.json", [])
    storage_mod.atomic_write_json(tmp_path / "consultations.json", [])

    health = storage_mod.append_health_log(
        "f-1",
        "an-1",
        "fever",
        {"duration": "2 days", "severity": "moderate"},
        "",
    )
    appt = storage_mod.append_appointment(
        farmer_id="f-1",
        date="2026-05-27",
        time="17:00",
        animal_id="an-1",
        health_log_id=health.id,
        issue_summary="fever",
        triage={"duration": "2 days"},
    )

    assert appt.farmer_id == "f-1"
    assert appt.health_log_id == health.id
    assert appt.issue_summary == "fever"
    assert len(storage_mod.appointments_for_farmer("f-1")) == 1


def test_farmer_weather_location_and_notifications(storage_mod, tmp_path: Path) -> None:
    from models import Farmer

    farmers = [
        Farmer(
            id="f-1",
            name="A",
            login_username="a",
            password_hash="x",
            phone="",
        ).model_dump()
    ]
    storage_mod.atomic_write_json(tmp_path / "farmers.json", farmers)
    storage_mod.atomic_write_json(tmp_path / "weather_notifications.json", [])

    updated = storage_mod.update_farmer_weather_location("f-1", "560001")
    assert updated.weather_location == "560001"
    loaded = storage_mod.get_farmer_by_id("f-1")
    assert loaded is not None
    assert loaded.weather_location == "560001"

    note = storage_mod.append_weather_notification(
        farmer_id="f-1",
        location_query="560001",
        risk_level="high",
        summary="High weather risk",
        details={"risk_level": "high"},
    )
    assert note.farmer_id == "f-1"
    assert len(storage_mod.weather_notifications_for_farmer("f-1")) == 1


def test_purge_stale_files_removes_only_old_ones(storage_mod, tmp_path: Path) -> None:
    """Gap found in review: session/draft files (voice_sessions,
    appointment_intakes, animal_registration_intakes) accumulated forever
    with no cleanup. purge_stale_files is the fix, wired at API startup."""
    import os
    import time

    target = tmp_path / "some_intakes"
    target.mkdir()
    old_file = target / "old.json"
    fresh_file = target / "fresh.json"
    old_file.write_text("{}", encoding="utf-8")
    fresh_file.write_text("{}", encoding="utf-8")

    old_time = time.time() - 40 * 86400
    os.utime(old_file, (old_time, old_time))

    removed = storage_mod.purge_stale_files(target, max_age_days=30)
    assert removed == 1
    assert not old_file.exists()
    assert fresh_file.exists()


def test_purge_stale_files_missing_directory_is_a_noop(storage_mod, tmp_path: Path) -> None:
    removed = storage_mod.purge_stale_files(tmp_path / "does_not_exist", max_age_days=30)
    assert removed == 0


def test_load_without_migrations_returns_rows_unchanged(storage_mod, tmp_path: Path) -> None:
    """Architecture review Point 3: with no migrations registered (today),
    loading must behave exactly as before."""
    rows = [{"id": "an-1", "farmer_id": "f-1", "tag_or_name": "T1"}]
    storage_mod.atomic_write_json(tmp_path / "animals.json", rows)
    assert storage_mod._load_json_list(tmp_path / "animals.json") == rows


def test_registered_migration_applies_on_load_without_rewriting_file(storage_mod, tmp_path: Path, monkeypatch) -> None:
    original = [{"id": "an-1"}, {"id": "an-2", "weight": 30}]
    storage_mod.atomic_write_json(tmp_path / "animals.json", original)

    def add_weight(row):
        row.setdefault("weight", None)
        return row

    monkeypatch.setattr(storage_mod, "_MIGRATIONS", {"animals.json": [(2, add_weight)]})
    rows = storage_mod._load_json_list(tmp_path / "animals.json")
    assert rows == [{"id": "an-1", "weight": None}, {"id": "an-2", "weight": 30}]
    on_disk = json.loads((tmp_path / "animals.json").read_text(encoding="utf-8"))
    assert on_disk == original, "a read must never rewrite the file"


def test_migrations_run_in_version_order_and_only_for_their_file(storage_mod, tmp_path: Path, monkeypatch) -> None:
    storage_mod.atomic_write_json(tmp_path / "animals.json", [{"id": "an-1"}])
    storage_mod.atomic_write_json(tmp_path / "health_logs.json", [{"id": "h-1"}])

    def v2_add_weight(row):
        row.setdefault("weight", 10)
        return row

    def v3_weight_to_kg(row):
        row.setdefault("weight_kg", row["weight"])
        return row

    # Registered out of order on purpose: v3 depends on v2 having run first.
    monkeypatch.setattr(storage_mod, "_MIGRATIONS", {"animals.json": [(3, v3_weight_to_kg), (2, v2_add_weight)]})
    assert storage_mod._load_json_list(tmp_path / "animals.json") == [{"id": "an-1", "weight": 10, "weight_kg": 10}]
    assert storage_mod._load_json_list(tmp_path / "health_logs.json") == [{"id": "h-1"}]


def test_migrated_rows_are_persisted_on_next_write(storage_mod, tmp_path: Path, monkeypatch) -> None:
    storage_mod.atomic_write_json(tmp_path / "consultations.json", [{"id": "c-old", "farmer_id": "f-1"}])

    def add_channel(row):
        row.setdefault("channel", "chat")
        return row

    monkeypatch.setattr(storage_mod, "_MIGRATIONS", {"consultations.json": [(2, add_channel)]})
    storage_mod.append_consultation("f-1", None, [{"role": "user", "content": "hi"}], "summary")

    on_disk = json.loads((tmp_path / "consultations.json").read_text(encoding="utf-8"))
    assert on_disk[0]["id"] == "c-old"
    assert on_disk[0]["channel"] == "chat", "the old record must be saved in the upgraded form"


def test_migration_registry_versions_are_valid(storage_mod) -> None:
    """Guards future edits: every registered step must target a version in
    2..CURRENT_SCHEMA_VERSION, with no duplicate versions per file."""
    for file_name, steps in storage_mod._MIGRATIONS.items():
        versions = [version for version, _ in steps]
        assert len(versions) == len(set(versions)), f"{file_name}: duplicate migration versions"
        for version in versions:
            assert 2 <= version <= storage_mod.CURRENT_SCHEMA_VERSION, f"{file_name}: bad version {version}"
