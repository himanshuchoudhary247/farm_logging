"""Offline PIN code -> location table, so a farmer's 6-digit PIN does not need
a Nominatim call (public OSM endpoint: 1 request/sec, no SLA, and some Indian
PINs are not in it at all).

Data: data/pin_lookup.csv next to this file, built by
scripts/build_pin_lookup.py (see data/README.md). A PIN that is not in the
table returns None and the caller falls back to Nominatim. A missing or
unreadable file also returns None for every PIN, never an error.

PIN_LOOKUP_LOCAL=0 turns the table off without a deploy.
"""
from __future__ import annotations

import csv
import logging
import os
import threading
from pathlib import Path
from typing import NamedTuple, Optional

_log = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).resolve().parent / "data" / "pin_lookup.csv"


class PinPlace(NamedTuple):
    pin: str
    office: str
    district: str
    state: str
    lat: float
    lon: float

    @property
    def display_name(self) -> str:
        # Same order as Nominatim's PIN results ("411001, <place>, <district>,
        # <state>, India"), so _parse_district/_parse_state read both alike.
        return f"{self.pin}, {self.office}, {self.district}, {self.state}, India"


_table: Optional[dict[str, PinPlace]] = None
_lock = threading.Lock()


def enabled() -> bool:
    return os.getenv("PIN_LOOKUP_LOCAL", "1").strip().lower() not in ("0", "false", "no", "off")


def _load(path: Path) -> dict[str, PinPlace]:
    table: dict[str, PinPlace] = {}
    try:
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                try:
                    place = PinPlace(
                        pin=row["pin"].strip(),
                        office=row["office"].strip(),
                        district=row["district"].strip(),
                        state=row["state"].strip(),
                        lat=float(row["lat"]),
                        lon=float(row["lon"]),
                    )
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue
                table[place.pin] = place
    except OSError as exc:
        _log.warning("PIN lookup table unavailable (%s): %s -- using Nominatim only", path, exc)
        return {}
    if not table:
        _log.warning("PIN lookup table %s has no usable rows -- using Nominatim only", path)
    else:
        _log.info("PIN lookup table loaded: %d PINs", len(table))
    return table


def _get_table() -> dict[str, PinPlace]:
    # Loaded once, on first use, and shared by all requests.
    global _table
    if _table is None:
        with _lock:
            if _table is None:
                _table = _load(_DATA_PATH)
    return _table


def lookup(pin: str) -> Optional[PinPlace]:
    """The table's location for this PIN, or None (not in the table, table
    missing, or turned off with PIN_LOOKUP_LOCAL=0)."""
    if not enabled():
        return None
    return _get_table().get((pin or "").strip())
