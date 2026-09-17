from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def storage_mod(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FARMER_CHAT_DATA_DIR", str(tmp_path))
    import storage

    return storage


def test_append_animal_invalidates_query_cache(storage_mod) -> None:
    """Real repro path: storage.append_animal(...) alone -- no manual
    clear_cache call -- must make the new row visible on the very next
    query_agent query. This is the exact bug fixed: clear_cache existed but
    was never called from production code."""
    from models import Farmer
    from services.query_agent import db as query_db

    farmer_id = "cache-test-farmer-1"
    storage_mod.atomic_write_json(
        storage_mod._path("farmers.json"),
        [Farmer(id=farmer_id, name="Cache Test", login_username="cachetest1", password_hash="x").model_dump()],
    )
    query_db.clear_cache(farmer_id)

    result = query_db.execute_query("SELECT COUNT(*) as c FROM animals", farmer_id)
    assert result["success"]
    assert result["rows"][0][0] == 0

    storage_mod.append_animal(farmer_id, tag_or_name="TestGoat", species="goat")

    result = query_db.execute_query("SELECT COUNT(*) as c FROM animals", farmer_id)
    assert result["success"]
    assert result["rows"][0][0] == 1, "new animal invisible -- cache was not invalidated"


def test_append_appointment_invalidates_query_cache(storage_mod) -> None:
    """Same scenario, appointments -- the specific 'book then ask how many
    appointments' regression named in the plan."""
    from models import Farmer
    from services.query_agent import db as query_db

    farmer_id = "cache-test-farmer-2"
    storage_mod.atomic_write_json(
        storage_mod._path("farmers.json"),
        [Farmer(id=farmer_id, name="Cache Test 2", login_username="cachetest2", password_hash="x").model_dump()],
    )
    query_db.clear_cache(farmer_id)

    result = query_db.execute_query("SELECT COUNT(*) as c FROM appointments", farmer_id)
    assert result["rows"][0][0] == 0

    storage_mod.append_appointment(farmer_id, date="2026-09-20", time="10:00")

    result = query_db.execute_query("SELECT COUNT(*) as c FROM appointments", farmer_id)
    assert result["rows"][0][0] == 1, "new appointment invisible -- cache was not invalidated"


def test_append_vaccination_record_invalidates_query_cache(storage_mod) -> None:
    from models import Farmer
    from services.query_agent import db as query_db

    farmer_id = "cache-test-farmer-3"
    storage_mod.atomic_write_json(
        storage_mod._path("farmers.json"),
        [Farmer(id=farmer_id, name="Cache Test 3", login_username="cachetest3", password_hash="x").model_dump()],
    )
    animal = storage_mod.append_animal(farmer_id, tag_or_name="VaxGoat", species="goat")
    query_db.clear_cache(farmer_id)

    result = query_db.execute_query("SELECT COUNT(*) as c FROM vaccination_records", farmer_id)
    assert result["rows"][0][0] == 0

    storage_mod.append_vaccination_record(farmer_id, animal.id, "FMD", status="administered")

    result = query_db.execute_query(
        "SELECT COUNT(*) as c FROM vaccination_records WHERE status = 'administered'", farmer_id
    )
    assert result["rows"][0][0] == 1, "new vaccination record invisible -- cache was not invalidated"
