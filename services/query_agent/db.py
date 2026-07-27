import json
import sqlite3
import threading
import re
from typing import Any, Optional

from models import Animal, Appointment, Farm, Farmer, HealthLog, WeatherNotification
from services.query_agent.schema import QUERY_TABLES, table_names

from storage import load_animals, load_appointments, load_farmers, load_farms, load_health_logs, load_weather_notifications

# Cache: thread-local in-memory databases per farmer_id
_db_cache: dict[str, sqlite3.Connection] = {}
_cache_lock = threading.Lock()

_FARMER_SCOPED_TABLES = {"animals", "health_logs", "appointments", "farms", "weather_notifications"}
_BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|ATTACH|DETACH|PRAGMA|EXECUTE)\b",
    re.IGNORECASE,
)
_MAX_ROWS = 200
_QUERY_TIMEOUT_S = 5


def _load_data() -> dict[str, list]:
    return {
        "animals": [a.model_dump() for a in load_animals()],
        "health_logs": [h.model_dump() for h in load_health_logs()],
        "appointments": [a.model_dump() for a in load_appointments()],
        "farms": [f.model_dump() for f in load_farms()],
        "farmers": [f.model_dump() for f in load_farmers()],
        "weather_notifications": [w.model_dump() for w in load_weather_notifications()],
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

    data = _load_data()

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


def _qualifier_for(sql: str, tbl: str) -> str:
    """Return the alias for *tbl* in the SQL, or *tbl* itself if unaliased.
    Handles: FROM animals a, JOIN animals AS a, FROM animals (no alias)
    """
    pat = re.compile(
        rf"\b(?:FROM|JOIN)\s+{re.escape(tbl)}(?:\s+AS)?\s+(\w+)",
        re.IGNORECASE,
    )
    m = pat.search(sql)
    if m:
        alias = m.group(1)
        # make sure it's not a keyword
        if alias.upper() not in {"WHERE", "ON", "AND", "OR", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "CROSS", "AS", "ON", "GROUP", "ORDER", "LIMIT", "HAVING"}:
            return alias
    return tbl


def _inject_scope(sql: str, farmer_id: str) -> str:
    """Inject WHERE farmer_id = '...' before GROUP BY / ORDER BY / LIMIT, or at the end.
    Qualifies with table name or alias to avoid ambiguity in JOINs.
    """
    tbls_in_sql = [t for t in _FARMER_SCOPED_TABLES if re.search(rf"\b{t}\b", sql, re.IGNORECASE)]
    if not tbls_in_sql:
        return sql

    qualifier = _qualifier_for(sql, tbls_in_sql[0])
    where_fragment = f"{qualifier}.farmer_id = '{farmer_id}'"

    if re.search(r"\bWHERE\b", sql, re.IGNORECASE):
        return re.sub(
            r"\bWHERE\b", f"WHERE {where_fragment} AND ", sql, count=1
        )

    clauses = ["GROUP BY", "ORDER BY", "LIMIT"]
    idx = len(sql)
    for clause in clauses:
        m = re.search(rf"\b{clause}\b", sql, re.IGNORECASE)
        if m and m.start() < idx:
            idx = m.start()
    before = sql[:idx].rstrip()
    after = sql[idx:]
    return f"{before} WHERE {where_fragment} {after}".strip()


def validate_sql(sql: str, farmer_id: str) -> str:
    stripped = sql.strip().strip(";")
    if not stripped:
        raise ValueError("Empty SQL query")

    if _BLOCKED_KEYWORDS.search(stripped):
        raise ValueError("Only SELECT queries are allowed")

    upper = stripped.upper().strip()
    if not upper.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    stripped = _inject_scope(stripped, farmer_id)

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
