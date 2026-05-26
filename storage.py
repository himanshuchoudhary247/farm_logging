from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from filelock import FileLock

from models import Appointment, Animal, ChatMessage, Consultation, Farmer, HealthLog, utc_now_iso

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


def append_animal(
    farmer_id: str,
    tag_or_name: str,
    species: str,
    sex: str = "",
    breed: str = "",
    age_years: Optional[float] = None,
    feeding_details: str = "",
) -> Animal:
    path = _path("animals.json")

    def work() -> Animal:
        rows = _load_json_list(path)
        aid = str(uuid.uuid4())
        row = Animal(
            id=aid,
            farmer_id=farmer_id,
            tag_or_name=tag_or_name,
            species=species,
            sex=sex,
            breed=breed,
            age_years=age_years,
            feeding_details=feeding_details,
        )
        rows.append(row.model_dump())
        atomic_write_json(path, rows)
        return row

    return _with_file_lock(path, work)


def update_animal(
    farmer_id: str,
    animal_id: Optional[str] = None,
    animal_name: Optional[str] = None,
    updates: Optional[dict[str, Any]] = None,
) -> Animal:
    if not animal_id and not animal_name:
        raise ValueError("animal_id or animal_name is required")

    updates = updates or {}
    allowed_keys = {"species", "sex", "breed", "age_years", "feeding_details", "tag_or_name"}
    invalid = [k for k in updates if k not in allowed_keys]
    if invalid:
        raise ValueError(f"Unsupported update fields: {', '.join(invalid)}")

    path = _path("animals.json")

    def work() -> Animal:
        rows = _load_json_list(path)
        target_idx = -1
        for i, r in enumerate(rows):
            if r.get("farmer_id") != farmer_id:
                continue
            if animal_id and r.get("id") == animal_id:
                target_idx = i
                break
            if animal_name and str(r.get("tag_or_name", "")).strip().lower() == animal_name.strip().lower():
                target_idx = i
                break

        if target_idx < 0:
            raise ValueError("Animal not found for this farmer")

        row = dict(rows[target_idx])
        for k, v in updates.items():
            if v is not None and v != "":
                row[k] = v
        rows[target_idx] = row
        atomic_write_json(path, rows)
        return Animal.model_validate(row)

    return _with_file_lock(path, work)


def load_health_logs() -> list[HealthLog]:
    return [HealthLog.model_validate(x) for x in _load_json_list(_path("health_logs.json"))]


def health_logs_for_farmer(farmer_id: str) -> list[HealthLog]:
    return [h for h in load_health_logs() if h.farmer_id == farmer_id]


def load_appointments() -> list[Appointment]:
    return [Appointment.model_validate(x) for x in _load_json_list(_path("appointments.json"))]


def appointments_for_farmer(farmer_id: str) -> list[Appointment]:
    return [a for a in load_appointments() if a.farmer_id == farmer_id]


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


def append_appointment(
    farmer_id: str,
    date: str,
    time: str,
    doctor_id: str = "",
    notes: str = "",
    health_log_id: Optional[str] = None,
    animal_id: Optional[str] = None,
    issue_summary: str = "",
    triage: Optional[dict[str, Any]] = None,
) -> Appointment:
    if animal_id is not None and not ensure_farmer_animal(farmer_id, animal_id):
        raise ValueError("Animal not found for this farmer")

    if health_log_id is not None:
        if not any(h.id == health_log_id and h.farmer_id == farmer_id for h in load_health_logs()):
            raise ValueError("Health log not found for this farmer")

    path = _path("appointments.json")

    def work() -> Appointment:
        rows = _load_json_list(path)
        aid = str(uuid.uuid4())
        row = Appointment(
            id=aid,
            farmer_id=farmer_id,
            date=date,
            time=time,
            doctor_id=doctor_id,
            notes=notes,
            health_log_id=health_log_id,
            animal_id=animal_id,
            issue_summary=issue_summary,
            triage=triage or {},
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
