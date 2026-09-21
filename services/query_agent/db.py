import json
import sqlite3
import threading
import re
from collections import OrderedDict
from typing import Any, Optional, get_type_hints

from services.query_agent.schema import QUERY_TABLES, table_names, _resolve_sql_type
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

# Cache: in-memory databases per farmer_id, scoped to that farmer's rows
# only. No cross-farmer data is ever loaded, so no SQL-level tenant filter
# is required (defence in depth via row-level scoping at the data layer
# rather than regex injection).
#
# Real bug, found in a robustness audit: this was documented as
# "thread-local" but never actually was -- _db_cache is a plain dict shared
# by every thread, and sqlite3.connect() defaults to check_same_thread=True.
# Both /query and /chat/turn are sync `def` endpoints, so FastAPI runs them
# on arbitrary anyio worker threads; a second request for the same
# farmer_id landing on a different thread than the one that built the
# cached connection hit sqlite3.ProgrammingError, which execute_query()
# silently swallowed into {"success": False}, burned a wasted second LLM
# "fix the SQL" call, failed again identically, and surfaced the raw
# Python thread-id error message as the farmer-facing answer -- a real,
# live, intermittent failure of the entire query_agent path.
#
# Fix: check_same_thread=False (in _build_db) lets the same connection be
# reused from any thread, and a per-farmer lock here serializes actual use
# of it -- SQLite connections still aren't safe for genuinely simultaneous
# access from multiple threads even with that flag off.
_db_cache: "OrderedDict[str, sqlite3.Connection]" = OrderedDict()
_db_locks: dict[str, threading.Lock] = {}
_cache_lock = threading.Lock()
_MAX_CACHED_FARMERS = 200  # bug found in robustness audit: this cache was unbounded

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
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")

    data = _load_data_for_farmer(farmer_id)

    for table_name in table_names():
        config = QUERY_TABLES[table_name]
        model = config["model"]
        rows = data.get(table_name, [])

        model_fields = list(model.model_fields.keys())
        # TEXT columns get COLLATE NOCASE so a generated `WHERE name = 'Gauri'`
        # still matches a stored 'GAURI' -- LLM-written SQL uses whatever
        # casing the farmer said, not necessarily the casing data was stored
        # in. Fixed at the schema/table level (not the prompt) so it applies
        # uniformly to every table/column without relying on the LLM to
        # remember LOWER()/LIKE everywhere.
        hints = get_type_hints(model)
        col_defs = []
        for c in model_fields:
            sql_type = _resolve_sql_type(hints.get(c, str))
            collate = " COLLATE NOCASE" if sql_type == "TEXT" else ""
            col_defs.append(f'"{c}"{collate}')
        cols = ", ".join(col_defs)
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


def _find_or_build_locked(farmer_id: str) -> tuple[sqlite3.Connection, threading.Lock]:
    """Must be called with _cache_lock already held. Finds or builds a
    farmer's connection+lock and returns both -- does NOT acquire the
    per-farmer lock itself (get_db()'s public contract is "no lock held
    on return", used directly by callers/tests that just want the
    connection object). execute_query's own locked variant below acquires
    the returned lock before this function's caller releases _cache_lock."""
    if farmer_id in _db_cache:
        _db_cache.move_to_end(farmer_id)
        return _db_cache[farmer_id], _db_locks[farmer_id]

    conn = _build_db(farmer_id)
    lock = threading.Lock()
    _db_cache[farmer_id] = conn
    _db_locks[farmer_id] = lock

    while len(_db_cache) > _MAX_CACHED_FARMERS:
        _evict_oldest_locked()

    return conn, lock


def _evict_oldest_locked() -> None:
    """Must be called with _cache_lock already held. Pops the LRU-oldest
    entry and closes it -- while still holding _cache_lock, acquires that
    farmer's OWN per-farmer lock first, so a query already in flight on
    that exact connection (holding the same lock object) finishes before
    the connection underneath it is closed. Safe from deadlock only
    because no code path in this module ever holds a per-farmer lock
    while trying to acquire _cache_lock -- always the other order."""
    evicted_id, evicted_conn = _db_cache.popitem(last=False)
    evicted_lock = _db_locks.pop(evicted_id, None)
    if evicted_lock is not None:
        with evicted_lock:
            evicted_conn.close()
    else:
        evicted_conn.close()


def get_db(farmer_id: str) -> sqlite3.Connection:
    with _cache_lock:
        conn, _lock = _find_or_build_locked(farmer_id)
        return conn


def _get_conn_locked(farmer_id: str) -> tuple[sqlite3.Connection, threading.Lock]:
    """execute_query's own accessor -- returns (conn, lock) with lock
    ALREADY ACQUIRED. Caller MUST release it (try/finally) when done.

    Real bug, found in code review, found again live via a direct stress
    test after the first fix attempt: even fetching (conn, lock) as one
    atomic pair under _cache_lock and then separately doing `with lock:`
    left a gap -- a thread could release _cache_lock, get preempted before
    reaching `with lock:`, and a concurrent clear_cache()/eviction could
    pop+close that exact connection in that gap (it also only needs
    _cache_lock to pop, then acquires the same lock uncontended since this
    thread hadn't gotten there yet). Reproduced directly: 12 worker
    threads hammering execute_query + clear_cache concurrently on the same
    3 farmer_ids raised "Cannot operate on a closed database." Fix:
    acquire the per-farmer lock BEFORE releasing _cache_lock, so there is
    no gap between "this connection is the current one" and "it's
    protected from being closed" for this thread to be preempted in."""
    with _cache_lock:
        conn, lock = _find_or_build_locked(farmer_id)
        lock.acquire()
        return conn, lock


def clear_cache(farmer_id: Optional[str] = None) -> None:
    # Real bug, found in code review: this used to pop and close(1) a
    # farmer's connection while holding only _cache_lock, never the
    # per-farmer lock execute_query() holds during an in-flight query on
    # that same connection -- storage.py calls this synchronously after
    # every write, so a write landing mid-query could close the connection
    # out from under an in-flight cursor and raise sqlite3.ProgrammingError.
    # Same fix as eviction: acquire the per-farmer lock (still under
    # _cache_lock, safe per the lock-ordering note above) before closing,
    # so this waits for any in-flight query on that connection to finish.
    with _cache_lock:
        if farmer_id:
            conn = _db_cache.pop(farmer_id, None)
            lock = _db_locks.pop(farmer_id, None)
            if conn is not None:
                if lock is not None:
                    with lock:
                        conn.close()
                else:
                    conn.close()
        else:
            for fid in list(_db_cache.keys()):
                conn = _db_cache.pop(fid)
                lock = _db_locks.pop(fid, None)
                if lock is not None:
                    with lock:
                        conn.close()
                else:
                    conn.close()


_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


def validate_sql(sql: str, farmer_id: str) -> str:
    stripped = sql.strip().strip(";")
    if not stripped:
        raise ValueError("Empty SQL query")

    # Bug found in robustness audit: blocked-keyword scan ran over the raw SQL
    # text, so a legit query like WHERE notes LIKE '%update%' got rejected --
    # "update" sat inside a string literal, not as a SQL verb. Scan a copy with
    # string literals blanked out; the real query (with literals intact) still
    # executes.
    without_literals = _STRING_LITERAL.sub("''", stripped)
    if _BLOCKED_KEYWORDS.search(without_literals):
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
    # _get_conn_locked returns with the per-farmer lock already held --
    # see its docstring for why acquiring it separately (even from an
    # atomically-fetched pair) still left a real, reproduced race.
    conn, lock = _get_conn_locked(farmer_id)

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
    finally:
        lock.release()
