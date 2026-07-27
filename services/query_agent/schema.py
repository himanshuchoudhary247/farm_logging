from typing import Any, Optional, Union, get_type_hints, get_origin, get_args

from models import (
    Animal,
    Appointment,
    Farm,
    Farmer,
    HealthLog,
    WeatherNotification,
)
from models import utc_now_iso

QUERY_TABLES = {
    "animals": {
        "model": Animal,
        "description": "Individual animals registered on the farm. Each row is one animal.",
        "joins": {
            "farmer_id": "farmers.id",
            "id -> animal_id": "health_logs.animal_id, appointments.animal_id",
        },
    },
    "health_logs": {
        "model": HealthLog,
        "description": "Health events recorded for animals: symptoms, treatments, illnesses, checkups. Each row is one health event.",
        "joins": {
            "animal_id": "animals.id",
            "farmer_id": "farmers.id",
        },
    },
    "appointments": {
        "model": Appointment,
        "description": "Veterinary appointments booked for animals. Each row is one appointment.",
        "joins": {
            "animal_id": "animals.id",
            "farmer_id": "farmers.id",
        },
    },
    "farms": {
        "model": Farm,
        "description": "Farm registration/profile details. One row per farmer.",
        "joins": {
            "farmer_id": "farmers.id",
        },
    },
    "farmers": {
        "model": Farmer,
        "description": "Farmer account information. One row per farmer.",
        "joins": {
            "id": "animals.farmer_id, health_logs.farmer_id, appointments.farmer_id, farms.farmer_id",
        },
    },
    "weather_notifications": {
        "model": WeatherNotification,
        "description": "Weather alert notifications generated for farmers. Each row is one notification.",
        "joins": {
            "farmer_id": "farmers.id",
        },
    },
}

PYTYPE_TO_SQL = {
    str: "TEXT",
    int: "INTEGER",
    float: "REAL",
    bool: "INTEGER",
}


def _resolve_sql_type(py_type) -> str:
    origin = get_origin(py_type)
    args = get_args(py_type)

    if origin is None or origin is type(None):
        if py_type in PYTYPE_TO_SQL:
            return PYTYPE_TO_SQL[py_type]
        if hasattr(py_type, "__name__"):
            name = py_type.__name__
            if name.startswith("Literal"):
                return "TEXT"
        return "TEXT"

    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _resolve_sql_type(non_none[0])
        return "TEXT"

    if origin is dict:
        return "TEXT"
    if origin is list:
        return "TEXT"
    return "TEXT"


def _is_optional(field_type) -> bool:
    origin = get_origin(field_type)
    if origin is Union:
        return type(None) in get_args(field_type)
    if origin is type(None):
        return True
    return False


def _field_doc(name: str, field_info, model) -> str:
    hints = get_type_hints(model)
    py_type = hints.get(name, str)
    sql_type = _resolve_sql_type(py_type)
    nullable = "NULL" if _is_optional(py_type) else "NOT NULL"
    default = field_info.default
    default_str = ""
    if default not in (None, "", ...):
        if isinstance(default, str) and default:
            default_str = f" (default: '{default}')"
        elif isinstance(default, (int, float)):
            default_str = f" (default: {default})"
    return f"  {name} {sql_type} {nullable}{default_str}"


def generate_create_sql(model) -> str:
    lines = [f"CREATE TABLE {model.__name__.lower()}s ("]
    schema = model.model_fields
    for name, field_info in schema.items():
        lines.append(_field_doc(name, field_info, model))
        lines[-1] += ","
    lines.append(");")
    return "\n".join(lines)


def generate_schema_ddl() -> str:
    parts = []
    for table_name, config in QUERY_TABLES.items():
        parts.append(f"-- {config['description']}")
        parts.append(generate_create_sql(config["model"]))
        parts.append("")
    return "\n".join(parts)


def generate_schema_for_prompt() -> str:
    lines = []
    for table_name, config in QUERY_TABLES.items():
        lines.append(f"Table: {table_name}")
        lines.append(f"  Description: {config['description']}")
        model = config["model"]
        schema = model.model_fields
        for name, field_info in schema.items():
            hints = get_type_hints(model)
            py_type = hints.get(name, str)
            sql_type = _resolve_sql_type(py_type)
            nullable = "nullable" if _is_optional(py_type) else "required"
            lines.append(f"  - {name} ({sql_type}, {nullable})")
        if config["joins"]:
            lines.append("  Joins:")
            for left, right in config["joins"].items():
                lines.append(f"    {table_name}.{left} = {right}")
        lines.append("")
    return "\n".join(lines)


def table_names() -> list[str]:
    return list(QUERY_TABLES.keys())


def column_names(table: str) -> list[str]:
    config = QUERY_TABLES.get(table)
    if not config:
        return []
    return list(config["model"].model_fields.keys())
