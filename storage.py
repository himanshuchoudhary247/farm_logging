from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from filelock import FileLock

from models import Animal, ChatMessage, Consultation, Farmer, HealthLog, utc_now_iso

T = TypeVar("T")

DATA_DIR_ENV = "FARMER_CHAT_DATA_DIR"


def get_data_dir() -> Path:
    import os

    raw = os.environ.get(DATA_DIR_ENV)
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parent / "data"


def _path(name: str) -> Path:
    return get_data_dir() / name


def _load_json_list(path: Path) -> list[Any]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(obj, indent=2, ensure_ascii=False)
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def _with_file_lock(path: Path, fn: Callable[[], T]) -> T:
    lock = FileLock(str(path) + ".lock")
    with lock:
        return fn()


def load_farmers() -> list[Farmer]:
    return [Farmer.model_validate(x) for x in _load_json_list(_path("farmers.json"))]


def get_farmer_by_username(username: str) -> Optional[Farmer]:
    u = username.strip().lower()
    for f in load_farmers():
        if f.login_username.strip().lower() == u:
            return f
    return None


def farmer_accounts() -> list[Farmer]:
    return [f for f in load_farmers() if f.role == "farmer"]


def load_animals() -> list[Animal]:
    return [Animal.model_validate(x) for x in _load_json_list(_path("animals.json"))]


def animals_for_farmer(farmer_id: str) -> list[Animal]:
    return [a for a in load_animals() if a.farmer_id == farmer_id]


def load_health_logs() -> list[HealthLog]:
    return [HealthLog.model_validate(x) for x in _load_json_list(_path("health_logs.json"))]


def health_logs_for_farmer(farmer_id: str) -> list[HealthLog]:
    return [h for h in load_health_logs() if h.farmer_id == farmer_id]


def append_health_log(
    farmer_id: str,
    animal_id: str,
    issue: str,
    params: dict[str, Any],
    notes: str,
) -> HealthLog:
    if not ensure_farmer_animal(farmer_id, animal_id):
        raise ValueError("Animal not found for this farmer")
    path = _path("health_logs.json")

    def work() -> HealthLog:
        rows = _load_json_list(path)
        hid = str(uuid.uuid4())
        row = HealthLog(
            id=hid,
            farmer_id=farmer_id,
            animal_id=animal_id,
            recorded_at=utc_now_iso(),
            issue=issue,
            params=params,
            notes=notes,
        )
        rows.append(row.model_dump())
        atomic_write_json(path, rows)
        return row

    return _with_file_lock(path, work)


def load_consultations() -> list[dict[str, Any]]:
    return _load_json_list(_path("consultations.json"))


def consultations_for_farmer(farmer_id: str) -> list[dict[str, Any]]:
    return [c for c in load_consultations() if c.get("farmer_id") == farmer_id]


def append_consultation(
    farmer_id: str,
    animal_id: Optional[str],
    messages: list[dict[str, str]],
    summary: str,
) -> Consultation:
    if animal_id is not None and not ensure_farmer_animal(farmer_id, animal_id):
        raise ValueError("Animal not found for this farmer")
    path = _path("consultations.json")

    def work() -> Consultation:
        rows = _load_json_list(path)
        cid = str(uuid.uuid4())
        cms = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in messages
            if m["role"] in ("user", "assistant")
        ]
        c = Consultation(
            id=cid,
            farmer_id=farmer_id,
            animal_id=animal_id,
            started_at=utc_now_iso(),
            messages=cms,
            status="saved",
            summary=summary,
        )
        rows.append(c.model_dump())
        atomic_write_json(path, rows)
        return c

    return _with_file_lock(path, work)


def ensure_farmer_animal(farmer_id: str, animal_id: str) -> bool:
    for a in animals_for_farmer(farmer_id):
        if a.id == animal_id:
            return True
    return False
