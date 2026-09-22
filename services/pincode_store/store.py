"""Shared in-memory store, keyed by PIN code, for any agent that needs
weather/seasonal/feed-market context (chat_orchestrator's weather branch,
generate_health_recommendation, query_agent, appointment_supervisor).

Unlike services.cache_refresh.ensure_general_alert, this does NOT require
the PIN to be pre-listed in config/pincode_profiles.yaml -- works for any
PIN a farmer actually gives, resolving location live on first access.
Process-local Python dict, not Redis or any external cache -- matches this
project's existing constraint (t2.micro, single small deployment; see the
original optimization plan's C1 note on why Redis was ruled out there).
Lost on process restart, same tradeoff the disk-backed session store
documents; rebuilds itself lazily from real sources on next access.

Sources actually wired in, all verified working live:
  - Open-Meteo forecast + 5-year archive (services.weather_alert.service)
  - Mandi (APMC) feed prices (services.market_prices.mandi)
Not wired in (see services/emergency_alerts/README-equivalent discussion):
  - Kisan Suvidha scraper -- confirmed broken, site moved to a JS SPA
  - IMD's real API -- confirmed gated behind IP whitelisting, not
    accessible without an approved registration
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

from services.weather_alert.service import get_weather_alert, get_seasonal_advisory_data
from services.market_prices.mandi import get_feed_price_snapshot

_log = logging.getLogger("pincode_store")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_DEFAULT_TTL_SEC = 60 * 60  # 1 hour -- forecast/feed prices are hourly-ish signals
_MAX_STORE_ENTRIES = 500  # bug found in robustness audit: this store was unbounded
_store: "OrderedDict[str, tuple[float, dict[str, Any]]]" = OrderedDict()
_lock = threading.Lock()


def _build(pin: str) -> dict[str, Any]:
    errors: list[str] = []

    weather_alert: Optional[dict[str, Any]] = None
    try:
        weather_alert = get_weather_alert(pin, days=3)
    except Exception as exc:
        errors.append(f"weather_alert: {exc}")

    seasonal: Optional[dict[str, Any]] = None
    try:
        seasonal = get_seasonal_advisory_data(pin, days=7)
    except Exception as exc:
        errors.append(f"seasonal_advisory: {exc}")

    state = (weather_alert or {}).get("resolved_location", {}).get("state") or (seasonal or {}).get("state")
    feed_market: Optional[dict[str, Any]] = None
    if state:
        try:
            feed_market = get_feed_price_snapshot(state)
        except Exception as exc:
            errors.append(f"feed_prices: {exc}")
    else:
        errors.append("feed_prices: could not resolve state for this PIN")

    return {
        "pin": pin,
        "district": (seasonal or {}).get("district"),
        "state": state,
        "weather": weather_alert,
        "seasonal": seasonal,
        "feed_market": feed_market,
        "errors": errors,
        "fetched_at": time.time(),
    }


def get_pincode_data(pin: str, force_refresh: bool = False, ttl_sec: int = _DEFAULT_TTL_SEC) -> dict[str, Any]:
    """The one call any agent makes. Returns the same shape every time,
    from memory if fresh, rebuilt from live sources if stale/missing."""
    pin = str(pin).strip()
    if not pin:
        raise ValueError("pin is required")

    with _lock:
        cached = _store.get(pin)
        if cached and not force_refresh:
            fetched_at, data = cached
            if time.time() - fetched_at < ttl_sec:
                _store.move_to_end(pin)
                return data

    data = _build(pin)
    with _lock:
        _store[pin] = (time.time(), data)
        _store.move_to_end(pin)
        while len(_store) > _MAX_STORE_ENTRIES:
            _store.popitem(last=False)
    _log.info("pincode_store refreshed pin=%s errors=%s", pin, data["errors"])
    return data


def peek(pin: str) -> Optional[dict[str, Any]]:
    """Read whatever's in memory without triggering a fetch. None if
    nothing's been loaded for this PIN yet."""
    with _lock:
        cached = _store.get(str(pin).strip())
    return cached[1] if cached else None


def clear(pin: Optional[str] = None) -> None:
    """Drop one PIN's cached entry, or everything if pin is None. Mainly
    for tests."""
    with _lock:
        if pin is None:
            _store.clear()
        else:
            _store.pop(str(pin).strip(), None)
