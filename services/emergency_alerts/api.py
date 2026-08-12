"""Shared read API for the emergency-alert feed (used by UI + api_server)."""

from __future__ import annotations

from typing import Any, Optional

from .config import DEMO_PINS
from .storage import last_run, load_feed, load_feed_flat


def fetch_alert_feed(pin: Optional[str] = None) -> dict[str, Any]:
    feed = load_feed()
    pins = [p for p in DEMO_PINS if pin is None or p["pin"] == pin]
    records: list[dict[str, Any]] = []
    for p in pins:
        records.extend(feed.get(p["pin"], []))
    return {
        "pins": pins,
        "records": records,
        "feed_generated_at": _feed_generated_at(),
        "last_run": last_run(),
    }


def _feed_generated_at() -> str | None:
    rows = load_feed_flat()
    dates = [r.get("date") for r in rows if r.get("date")]
    return max(dates) if dates else None
