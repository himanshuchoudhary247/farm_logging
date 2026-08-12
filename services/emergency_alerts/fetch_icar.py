"""ICAR-NIVEDI disease advisory fetcher using the static disease catalogue.

Loads disease_catalogue.json and, for a given district + state, looks up
active diseases for the current season, then returns an advisory digest
with prevention measures. This is genuine ICAR-NIVEDI NADRES data — no
network needed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .config import LANG_NAMES

_SEASON_MAP = {
    1: "winter", 2: "winter", 3: "spring", 4: "spring",
    5: "summer", 6: "monsoon", 7: "monsoon", 8: "monsoon",
    9: "monsoon", 10: "post-monsoon", 11: "post-monsoon", 12: "winter",
}


def _catalogue_path() -> Path:
    """Find disease_catalogue.json relative to this module or common layouts."""
    start = Path(__file__).resolve().parent
    for candidate in [start, *start.parents]:
        for name in ("disease_catalogue.json",):
            p = candidate / name
            if p.is_file():
                return p
        if (candidate / "data").is_dir() and (candidate / "data" / "disease_catalogue.json").is_file():
            return candidate / "data" / "disease_catalogue.json"
    return Path("disease_catalogue.json")


_cat_cache: dict[str, Any] | None = None


def _load_catalogue() -> dict[str, Any]:
    global _cat_cache
    if _cat_cache is not None:
        return _cat_cache
    try:
        _cat_cache = json.load(open(_catalogue_path(), encoding="utf-8"))
    except Exception:
        _cat_cache = {}
    return _cat_cache


def _normalize_state(state: str) -> str:
    return state.strip().replace(" ", "_")


def _current_season() -> str:
    from datetime import datetime
    return _SEASON_MAP.get(datetime.now().month, "monsoon")


def get_active_diseases(district: str, state: str) -> list[dict[str, Any]]:
    """Return active diseases for the district/season from the ICAR catalogue."""
    cat = _load_catalogue()
    if not cat:
        return []
    st_key = _normalize_state(state)
    state_info = cat.get("states", {}).get(st_key) or cat.get("states", {}).get(state)
    if not state_info:
        return []
    districts = [d.lower() for d in state_info.get("districts", [])]
    district_match = any(district.lower() in d or d in district.lower() for d in districts)
    active_names = state_info.get("active_diseases", [])
    diseases = cat.get("diseases", {})
    season = _current_season()
    result = []
    for dn in active_names:
        info = diseases.get(dn)
        if not info:
            continue
        seasons = info.get("season", [])
        if season in seasons or "year-round" in seasons:
            entry = {
                "disease": dn.replace("_", " "),
                "species": info.get("species", []),
                "symptoms": info.get("symptoms", []),
                "prevention": info.get("prevention", []),
                "icar_ref": info.get("icar_ref", ""),
                "season": season,
                "district_match": district_match,
            }
            result.append(entry)
    return result


def advisory_digest(district: str, state: str, language: str = "en") -> dict[str, Any]:
    """Build an ICAR disease advisory digest for the farmer's district."""
    active = get_active_diseases(district, state)
    if not active:
        return {
            "source": "ICAR-NIVEDI NADRES",
            "district": district,
            "state": state,
            "advisory": None,
            "note": f"No active ICAR disease alerts for {district} this season.",
        }
    parts = []
    for d in active[:4]:
        parts.append(
            f"{d['disease']} (affects {', '.join(d['species'])}, season: {d['season']}): "
            f"Symptoms: {', '.join(d['symptoms'][:3])}. "
            f"Prevention: {', '.join(d['prevention'][:2])}. {d['icar_ref']}"
        )
    return {
        "source": "ICAR-NIVEDI NADRES",
        "district": district,
        "state": state,
        "advisory": " ".join(parts),
        "active_diseases": [d["disease"] for d in active],
        "language": LANG_NAMES.get(language, "English"),
    }