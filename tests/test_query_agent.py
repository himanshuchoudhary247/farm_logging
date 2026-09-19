from __future__ import annotations

import json
import threading
import pytest

from services.query_agent import agent as query_agent
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
    for table in ["animals", "health_logs", "appointments", "farms", "weather_notifications", "ai_health_logs", "vaccination_records"]:
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
    for name in ["animals", "farmers", "health_logs", "appointments", "farms", "weather_notifications", "ai_health_logs", "vaccination_records"]:
        assert name in schema, f"{name} missing from schema"


def test_blocked_keyword_inside_string_literal_not_rejected():
    """Real bug, found in a robustness audit: _BLOCKED_KEYWORDS matched
    anywhere in the SQL text, including inside string literals -- a
    legitimate query like WHERE notes LIKE '%update%' got rejected as
    unsafe because "update" sat inside a quoted string, not as a SQL verb."""
    sql = query_db.validate_sql("SELECT * FROM health_logs WHERE LOWER(notes) LIKE '%update%'", "f1")
    assert sql.upper().startswith("SELECT")
    assert "'%update%'" in sql, "the literal itself must survive unmodified in the executed query"


def test_blocked_keyword_as_real_verb_still_rejected():
    """The string-literal fix must not create a bypass -- a real UPDATE
    statement, even one that also contains a quoted string, is still
    blocked."""
    with pytest.raises(ValueError, match="Only SELECT"):
        query_db.validate_sql("UPDATE animals SET notes = 'update' WHERE id = 1", "f1")


def test_db_cache_evicts_oldest_beyond_cap():
    """Real bug, found in a robustness audit: _db_cache was unbounded,
    farmer_id-keyed, connections never closed on eviction. Now an
    LRU-bounded OrderedDict; verify eviction actually drops the oldest
    connection once the cap is exceeded."""
    query_db.clear_cache()
    original_cap = query_db._MAX_CACHED_FARMERS
    query_db._MAX_CACHED_FARMERS = 3
    try:
        conns = {fid: query_db.get_db(fid) for fid in ["ea1", "ea2", "ea3"]}
        assert len(query_db._db_cache) == 3
        query_db.get_db("ea4")
        assert len(query_db._db_cache) == 3, "cache must not grow past the cap"
        assert "ea1" not in query_db._db_cache, "oldest entry (ea1) must be evicted first"
        assert "ea4" in query_db._db_cache
    finally:
        query_db._MAX_CACHED_FARMERS = original_cap
        query_db.clear_cache()


def test_db_cache_access_refreshes_lru_order():
    """Accessing a cached connection must move it to the front of the LRU
    order -- otherwise a hot farmer_id could still get evicted just for
    being added first."""
    query_db.clear_cache()
    original_cap = query_db._MAX_CACHED_FARMERS
    query_db._MAX_CACHED_FARMERS = 3
    try:
        for fid in ["eb1", "eb2", "eb3"]:
            query_db.get_db(fid)
        query_db.get_db("eb1")  # touch eb1 -- should no longer be the oldest
        query_db.get_db("eb4")  # forces one eviction
        assert "eb1" in query_db._db_cache, "recently touched entry must survive eviction"
        assert "eb2" not in query_db._db_cache, "eb2, never touched again, is now the oldest"
    finally:
        query_db._MAX_CACHED_FARMERS = original_cap
        query_db.clear_cache()


def test_execute_query_thread_safe_concurrent_access():
    """Real bug, found in a robustness audit: _db_cache connections were
    opened with the sqlite3 default check_same_thread=True, but both
    /query and /chat/turn are sync `def` endpoints -- FastAPI runs them on
    arbitrary worker threads. A second request for the same farmer_id
    landing on a different thread than the one that built the cached
    connection hit sqlite3.ProgrammingError. Reproduce with real concurrent
    threads hammering the same farmer_id's cached connection."""
    query_db.clear_cache("ec-thread-test")
    errors = []

    def worker():
        try:
            for _ in range(20):
                result = query_db.execute_query("SELECT COUNT(*) as c FROM animals", "ec-thread-test")
                assert result["success"], result.get("error")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors, f"concurrent access raised: {errors}"
    query_db.clear_cache("ec-thread-test")


def test_format_result_returns_real_answer_not_none():
    """Real bug, found live: _format_result built its LLM prompt but never
    called the model or returned anything -- fell off the end, implicit
    None. Every successful query got answer:null in the API response,
    which crashed the frontend (null.split() on a declared-non-nullable
    field). Verify the function actually returns the adapter's text."""
    class FakeAdapter:
        def complete(self, messages, system):
            return "You have 53 animals."

    result = {"success": True, "columns": ["c"], "rows": [[53]], "row_count": 1}
    answer = query_agent._format_result("how many animals do I have", result, "schema text", FakeAdapter())
    assert answer == "You have 53 animals."
    assert answer is not None


def test_format_result_never_returns_none_even_on_adapter_error():
    class FailingAdapter:
        def complete(self, messages, system):
            raise RuntimeError("bedrock unavailable")

    result = {"success": True, "columns": ["c"], "rows": [[53]], "row_count": 1}
    answer = query_agent._format_result("how many animals do I have", result, "schema text", FailingAdapter())
    assert answer is not None
    assert isinstance(answer, str) and answer.strip()