"""Demo PIN codes monitored by the async emergency-alert pipeline.

Each entry: pin, district, state, and the primary farmer language for
LLM-generated actionable insights.
"""

from __future__ import annotations

DEMO_PINS: list[dict[str, str]] = [
    {"pin": "302001", "district": "Jaipur", "state": "Rajasthan", "language": "hi"},
    {"pin": "583101", "district": "Bellary", "state": "Karnataka", "language": "kn"},
    {"pin": "641001", "district": "Coimbatore", "state": "Tamil Nadu", "language": "ta"},
    {"pin": "500032", "district": "Hyderabad", "state": "Telangana", "language": "te"},
    {"pin": "517001", "district": "Chittoor", "state": "Andhra Pradesh", "language": "te"},
    {"pin": "342001", "district": "Jodhpur", "state": "Rajasthan", "language": "hi"},
    {"pin": "584101", "district": "Raichur", "state": "Karnataka", "language": "kn"},
    {"pin": "625531", "district": "Theni", "state": "Tamil Nadu", "language": "ta"},
    {"pin": "506001", "district": "Warangal", "state": "Telangana", "language": "te"},
    {"pin": "530001", "district": "Visakhapatnam", "state": "Andhra Pradesh", "language": "te"},
]

LANG_NAMES: dict[str, str] = {
    "hi": "Hindi",
    "kn": "Kannada",
    "te": "Telugu",
    "ta": "Tamil",
    "mr": "Marathi",
    "en": "English",
}

SCAN_HORIZON_DAYS = 7

DATA_DIR = "data"
FEED_FILE = "alert_feed.json"
RUNS_FILE = "alert_runs.json"

KISAN_SUVIDHA_URL = "https://kisansuvidha.gov.in/"


def pins_for_state(state: str) -> list[dict[str, str]]:
    return [p for p in DEMO_PINS if p["state"].lower() == state.lower()]
