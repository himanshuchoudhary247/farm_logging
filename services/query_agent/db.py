import json
import sqlite3
import threading
import re
from typing import Any, Optional

from services.query_agent.schema import QUERY_TABLES, table_names
from storage import (
    load_farmers,
    ai_health_logs_for_farmer,
    animals_for_farmer,
    appointments_for_farmer,
    farms_for_farmer,
    health_logs_for_farmer,
    load_weather_notifications,
    vaccination_records_for_farmer,
    weather_notifications_for_farmer,
)

# Cache: thread-local in-memory databases per farmer_id, scoped to that
# farmer's rows only. No cross-farmer data is ever loaded, so no SQL-level
# tenant filter is required (defence in depth via row-level scoping at the
# data layer rather than regex injection).
_db_cache: dict[str, sqlite3.Connection] = {}
_cache_lock = threading.Lock()

_BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|ATTACH|DETACH|PRAGMA|EXECUTE)\b",
    re.IGNORECASE,
)
_MAX_ROWS = 200
_QUERY_TIMEOUT_S = 5


def _load_data_for_farmer(farmer_id: str) -> dict[str, list]:
    """Load ONLY this farmer's rows. Other farmers' data never enters the DB."""
    farmer_rows = []
    for f in load_farmers():
        if f.id == farmer_id:
            farmer_rows.append(f.model_dump())
            break
    return {
        "animals": [a.model_dump() for a in animals_for_farmer(farmer_id)],
        "health_logs": [h.model_dump() for h in health_logs_for_farmer(farmer_id)],
        "appointments": [a.model_dump() for a in appointments_for_farmer(farmer_id)],
        "farms": [fm.model_dump() for fm in farms_for_farmer(farmer_id)],
        "farmers": farmer_rows,
        "weather_notifications": [w.model_dump() for w in weather_notifications_for_farmer(farmer_id)],
        "ai_health_logs": [a.model_dump() for a in ai_health_logs_for_farmer(farmer_id)],
        "vaccination_records": [v.model_dump() for v in vaccination_records_for_farmer(farmer_id)],
    }


def _serialize_value(v: Any) -> Any:
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return json.dumps(v, ensure_ascii=False)
    return v


def _build_db(farmer_id: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")

    data = _load_data_for_farmer(farmer_id)

    for table_name in table_names():
        config = QUERY_TABLES[table_name]
        model = config["model"]
        rows = data.get(table_name, [])

        model_fields = list(model.model_fields.keys())
        cols = ", ".join(f'"{c}"' for c in model_fields)
        placeholders = ", ".join("?" for _ in model_fields)
        conn.execute(f'CREATE TABLE "{table_name}" ({cols})')

        for row in rows:
            values = [_serialize_value(row.get(c, "")) for c in model_fields]
            try:
                conn.execute(f'INSERT INTO "{table_name}" VALUES ({placeholders})', values)
            except sqlite3.OperationalError:
                pass

        idx_col = "farmer_id"
        if idx_col in model_fields:
            try:
                conn.execute(f'CREATE INDEX idx_{table_name}_{idx_col} ON "{table_name}"({idx_col})')
            except sqlite3.OperationalError:
                pass

    conn.commit()
    return conn


def get_db(farmer_id: str) -> sqlite3.Connection:
    with _cache_lock:
        if farmer_id not in _db_cache:
            _db_cache[farmer_id] = _build_db(farmer_id)
        return _db_cache[farmer_id]


def clear_cache(farmer_id: Optional[str] = None) -> None:
    with _cache_lock:
        if farmer_id:
            _db_cache.pop(farmer_id, None)
        else:
            _db_cache.clear()


def validate_sql(sql: str, farmer_id: str) -> str:
    stripped = sql.strip().strip(";")
    if not stripped:
        raise ValueError("Empty SQL query")

    if _BLOCKED_KEYWORDS.search(stripped):
        raise ValueError("Only SELECT queries are allowed")

    upper = stripped.upper().strip()
    if not upper.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    limit_pattern = re.compile(r"\bLIMIT\b", re.IGNORECASE)
    if not limit_pattern.search(stripped):
        stripped += f" LIMIT {_MAX_ROWS}"

    return stripped


def execute_query(sql: str, farmer_id: str) -> dict[str, Any]:
    safe_sql = validate_sql(sql, farmer_id)
    conn = get_db(farmer_id)

    try:
        cur = conn.execute(f"PRAGMA query_only=ON")
        cur = conn.execute(safe_sql)
        rows = cur.fetchmany(_MAX_ROWS + 1)
        truncated = len(rows) > _MAX_ROWS
        rows = rows[:_MAX_ROWS]
        columns = [desc[0] for desc in cur.description]
        return {
            "success": True,
            "sql": safe_sql,
            "columns": columns,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
        }
    except Exception as e:
        return {
            "success": False,
            "sql": safe_sql,
            "error": str(e),
        }
