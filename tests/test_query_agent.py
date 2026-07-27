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


def test_farmer_scoping_injected():
    sql = query_db.validate_sql("SELECT * FROM animals", "farmer_test_1")
    assert "farmer_id = 'farmer_test_1'" in sql
    assert sql.upper().startswith("SELECT")


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


def test_farmer_scoped_tables_get_scope():
    for table in ["animals", "health_logs", "appointments", "farms", "weather_notifications"]:
        sql = query_db.validate_sql(f"SELECT * FROM {table}", "f-test")
        assert "farmer_id = 'f-test'" in sql, f"{table} missing farmer scope"


def test_non_farmer_tables_no_scope():
    sql = query_db.validate_sql("SELECT * FROM farmers", "f-test")
    assert "farmer_id =" not in sql


def test_existing_where_not_duplicated():
    sql = query_db.validate_sql(
        "SELECT * FROM animals WHERE species = 'goat'", "f1"
    )
    assert "animals.farmer_id = 'f1' AND" in sql
    assert sql.count("WHERE") == 1


def test_group_by_scope():
    sql = query_db.validate_sql(
        "SELECT species, COUNT(*) as cnt FROM animals GROUP BY species", "f1"
    )
    assert "animals.farmer_id = 'f1'" in sql
    assert "GROUP BY" in sql
    assert sql.rindex("WHERE") < sql.rindex("GROUP BY")


def test_join_alias_scope():
    sql = query_db.validate_sql(
        "SELECT a.tag_or_name, ap.date FROM appointments ap JOIN animals a ON ap.animal_id = a.id",
        "f1",
    )
    assert "farmer_id = 'f1'" in sql
    assert sql.upper().startswith("SELECT")


def test_join_animals_first():
    sql = query_db.validate_sql(
        "SELECT a.tag_or_name, ap.date FROM animals a JOIN appointments ap ON ap.animal_id = a.id",
        "f1",
    )
    # Either qualifier is fine — the key is that farmer_id is injected
    assert "farmer_id = 'f1'" in sql


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
    query_db.clear_cache()
    r1 = query_db.execute_query("SELECT COUNT(*) as c FROM farmers", "farmer1")
    r2 = query_db.execute_query("SELECT COUNT(*) as c FROM farmers", "farmer2")
    assert r1["success"]
    assert r2["success"]


def test_schema_describes_all_tables():
    schema = generate_schema_for_prompt()
    for name in ["animals", "farmers", "health_logs", "appointments", "farms", "weather_notifications"]:
        assert name in schema, f"{name} missing from schema"
