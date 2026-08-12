"""Persistence for the emergency-alert feed and scan run log.

JSON files under data/ (FARMER_CHAT_DATA_DIR override supported), mirroring
the filelock + atomic-write pattern used by storage.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from filelock import FileLock

from .config import DATA_DIR, FEED_FILE, RUNS_FILE


def get_data_dir() -> Path:
    raw = os.environ.get("FARMER_CHAT_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    # Walk up from this file to find the project root (marked by a data/ dir
    # or the disease catalogue), covering both local services/ and EC2 flat
    # emergency_alerts/ layouts.
    start = Path(__file__).resolve().parent
    for candidate in [start, *start.parents]:
        if (candidate / "data").is_dir():
            return candidate / "data"
        if (candidate / "disease_catalogue.json").is_file():
            return candidate / DATA_DIR
    return Path(__file__).resolve().parents[2] / DATA_DIR


def _path(name: str) -> Path:
    return get_data_dir() / name


def _read_json(path: Path) -> Any:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _with_lock(path: Path, fn):
    with FileLock(str(path) + ".lock"):
        return fn()


def load_feed() -> dict[str, list[dict[str, Any]]]:
    """Return feed keyed by pin -> list of alert records (newest first)."""
    path = _path(FEED_FILE)
    data = _read_json(path)
    if isinstance(data, list):
        return _index_feed(data)
    return data or {}


def _index_feed(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(str(row.get("pin")), []).append(row)
    for rows_by_pin in out.values():
        rows_by_pin.sort(key=lambda r: r.get("date", ""), reverse=True)
    return out


def load_feed_flat() -> list[dict[str, Any]]:
    path = _path(FEED_FILE)
    data = _read_json(path)
    if isinstance(data, dict):
        return [r for rows in data.values() for r in rows]
    return data


def save_feed(feed: dict[str, list[dict[str, Any]]]) -> None:
    path = _path(FEED_FILE)
    _write_json(path, feed)


def upsert_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Insert alerts that are new (dedup key = pin+date+type); return inserted."""
    path = _path(FEED_FILE)
    inserted: list[dict[str, Any]] = []

    def work() -> None:
        rows = load_feed_flat()
        existing: set[str] = {_dedup_key(r) for r in rows}
        for a in alerts:
            key = _dedup_key(a)
            if key in existing:
                continue
            a["id"] = str(uuid.uuid4())
            a["created_at"] = _now_iso()
            rows.append(a)
            existing.add(key)
            inserted.append(a)
        _write_json(path, rows)

    _with_lock(path, work)
    return inserted


def _dedup_key(record: dict[str, Any]) -> str:
    """Stable identity for an alert: pin + date + type + reasons fingerprint."""
    reasons = record.get("reasons") or []
    fingerprint = hashlib.md5("|".join(sorted(map(str, reasons))).encode("utf-8")).hexdigest()[:10]
    return f"{record.get('pin')}:{record.get('date')}:{record.get('type')}:{fingerprint}"


def load_runs() -> list[dict[str, Any]]:
    return _read_json(_path(RUNS_FILE))


def append_run(run: dict[str, Any]) -> None:
    path = _path(RUNS_FILE)

    def work() -> None:
        runs = load_runs()
        runs.append(run)
        _write_json(path, runs[-200:])

    _with_lock(path, work)


def last_run() -> dict[str, Any] | None:
    runs = load_runs()
    return runs[-1] if runs else None


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_today() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sleep_seconds() -> float:
    return float(os.environ.get("EMERGENCY_SCAN_SLEEP", "0") or "0")


def monotonic() -> float:
    return time.monotonic()
