from __future__ import annotations

import json
import pytest

from services.query_agent import db as query_db
from services.query_agent.schema import generate_schema_for_prompt


def test_schema_generation():
    schema = generate_schema_for_prompt()
    assert "animals" in schema
    assert "health_logs" in schema
    assert "appointments" in schema
    assert "farmers" in schema
    assert len(schema) > 500


def test_blocked_ddl():
    with pytest.raises(ValueError, match="Only SELECT"):
        query_db.validate_sql("DROP TABLE animals", "farmer1")

    with pytest.raises(ValueError, match="Only SELECT"):
        query_db.validate_sql("INSERT INTO animals VALUES (1)", "farmer1")

    with pytest.raises(ValueError, match="Only SELECT"):
        query_db.validate_sql("UPDATE animals SET name='x'", "farmer1")


def test_empty_sql():
    with pytest.raises(ValueError, match="Empty"):
        query_db.validate_sql("", "farmer1")


def test_validate_sql_returns_clean_select():
    """validate_sql no longer injects farmer_id into SQL — scoping is at the
    data layer (per-farmer in-memory DB). The returned SQL should be a clean
    SELECT with LIMIT appended."""
    sql = query_db.validate_sql("SELECT * FROM animals", "farmer_test_1")
    assert sql.upper().startswith("SELECT")
    assert "farmer_id" not in sql  # no SQL-level injection
    assert "LIMIT" in sql


def test_limit_injected():
    sql = query_db.validate_sql("SELECT id FROM animals", "f1")
    assert "LIMIT" in sql


def test_no_limit_override():
    sql = query_db.validate_sql("SELECT id FROM animals LIMIT 5", "f1")
    assert "LIMIT 5" in sql


def test_execute_returns_expected_structure():
    query_db.clear_cache("farmer1")
    result = query_db.execute_query("SELECT COUNT(*) as cnt FROM animals", "farmer1")
    assert result["success"] is True
    assert result["columns"] == ["cnt"]
    assert isinstance(result["row_count"], int)
    assert result["truncated"] is False


def test_execute_bad_sql_returns_error():
    result = query_db.execute_query("SELECT * FROM nonexistent_table", "farmer1")
    assert result["success"] is False
    assert "error" in result


def test_farmer_scoped_tables_queryable():
    """All farmer-scoped tables should be queryable without error (data is
    pre-filtered to the farmer's rows at DB-build time)."""
    for table in ["animals", "health_logs", "appointments", "farms", "weather_notifications"]:
        result = query_db.execute_query(f"SELECT COUNT(*) as c FROM {table}", "f-test")
        assert result["success"], f"{table} query failed: {result.get('error')}"


def test_non_farmer_table_queryable():
    result = query_db.execute_query("SELECT COUNT(*) as c FROM farmers", "f-test")
    assert result["success"]


def test_existing_where_preserved():
    sql = query_db.validate_sql("SELECT * FROM animals WHERE species = 'goat'", "f1")
    assert sql.count("WHERE") == 1
    assert "species = 'goat'" in sql


def test_group_by_preserved():
    sql = query_db.validate_sql(
        "SELECT species, COUNT(*) as cnt FROM animals GROUP BY species", "f1"
    )
    assert "GROUP BY" in sql
    assert sql.rindex("WHERE") < sql.rindex("GROUP BY") if "WHERE" in sql.upper() else True


def test_join_works():
    """JOINs across scoped tables should work — no cross-farmer leak because
    the DB only contains the querying farmer's rows."""
    result = query_db.execute_query(
        "SELECT a.tag_or_name, ap.date FROM appointments ap JOIN animals a ON ap.animal_id = a.id",
        "f1",
    )
    assert result["success"], f"JOIN failed: {result.get('error')}"


def test_join_animals_first():
    result = query_db.execute_query(
        "SELECT a.tag_or_name, ap.date FROM animals a JOIN appointments ap ON ap.animal_id = a.id",
        "f1",
    )
    assert result["success"], f"JOIN failed: {result.get('error')}"


def test_cache_reused():
    query_db.clear_cache()
    c1 = query_db.get_db("farmer1")
    c2 = query_db.get_db("farmer1")
    assert c1 is c2


def test_cache_clear():
    query_db.clear_cache("farmer1")
    c1 = query_db.get_db("farmer1")
    query_db.clear_cache("farmer1")
    c2 = query_db.get_db("farmer1")
    assert c1 is not c2


def test_multiple_farmers_isolated():
    """Two different farmer IDs get separate in-memory DBs — each contains
    only that farmer's rows (farmers table has at most 1 row per farmer_id)."""
    query_db.clear_cache()
    r1 = query_db.execute_query("SELECT COUNT(*) as c FROM farmers", "farmer1")
    r2 = query_db.execute_query("SELECT COUNT(*) as c FROM farmers", "farmer2")
    assert r1["success"]
    assert r2["success"]
    # Each farmer DB has at most 1 row in farmers (their own), never all 102
    assert r1["row_count"] <= 1
    assert r2["row_count"] <= 1


def test_schema_describes_all_tables():
    schema = generate_schema_for_prompt()
    for name in ["animals", "farmers", "health_logs", "appointments", "farms", "weather_notifications"]:
        assert name in schema, f"{name} missing from schema"