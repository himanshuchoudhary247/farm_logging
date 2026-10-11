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

Cache lifetime: the data for a location is kept for
WEATHER_CACHE_TTL_HOURS (default 12), so repeat questions about the same
PIN or place are answered from the saved data instead of calling
Open-Meteo / Mandi again. Only the source data is cached -- the agent
still writes each farmer's answer in their own words and language.
  - "Pune", " pune " and "PUNE" are one entry.
  - A lookup whose weather fetch failed (bad PIN, API down) is kept for
    5 minutes only, so it is retried soon but not on every message.
  - If a refresh fails while good older data exists, the older data is
    returned with "stale": True instead of an error.
  - Only one live fetch per location runs at a time; others asking about
    the same place meanwhile wait and reuse it.

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
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from services.weather_alert.service import get_weather_alert, get_seasonal_advisory_data
from services.market_prices.mandi import get_feed_price_snapshot

_log = logging.getLogger("pincode_store")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

# 12h, not 24h, by default: forecasts and heat/rain alerts can change within
# a day. Override per deployment with WEATHER_CACHE_TTL_HOURS.
_DEFAULT_TTL_HOURS = 12
_DEFAULT_TTL_SEC = _DEFAULT_TTL_HOURS * 60 * 60
# A failed lookup is retried after this long instead of on every message,
# but is never kept for the full lifetime.
_FAILED_TTL_SEC = 5 * 60
_MAX_STORE_ENTRIES = 500  # bug found in robustness audit: this store was unbounded
_store: "OrderedDict[str, tuple[float, dict[str, Any]]]" = OrderedDict()
_lock = threading.Lock()
# One lock per location being fetched, so a cold location is fetched once
# even if several farmers ask about it at the same moment.
_build_locks: dict[str, threading.Lock] = {}


def _now() -> float:
    return time.time()


def _ttl_seconds() -> int:
    raw = os.getenv("WEATHER_CACHE_TTL_HOURS", "").strip()
    if not raw:
        return _DEFAULT_TTL_SEC
    try:
        hours = float(raw)
    except ValueError:
        _log.warning("WEATHER_CACHE_TTL_HOURS=%r is not a number -- using %dh", raw, _DEFAULT_TTL_HOURS)
        return _DEFAULT_TTL_SEC
    if hours <= 0:
        _log.warning("WEATHER_CACHE_TTL_HOURS=%r must be above 0 -- using %dh", raw, _DEFAULT_TTL_HOURS)
        return _DEFAULT_TTL_SEC
    return int(hours * 60 * 60)


def _cache_key(location: str) -> str:
    """One entry per place regardless of case/spacing."""
    return " ".join(str(location).split()).lower()


def _is_usable(data: dict[str, Any]) -> bool:
    """Weather is the core of this data; without it the entry is a failure."""
    return bool(data.get("weather"))


def _build(pin: str) -> dict[str, Any]:
    errors: list[str] = []

    # weather_alert and seasonal_advisory each resolve the PIN and hit
    # Open-Meteo independently; neither depends on the other's result, so
    # running them one after another just stacks two network round trips
    # (feed_market does depend on the state either of these resolves, so
    # it stays sequential, after both finish). Found in review of the
    # weather flow.
    with ThreadPoolExecutor(max_workers=2) as pool:
        weather_future = pool.submit(get_weather_alert, pin, days=3)
        seasonal_future = pool.submit(get_seasonal_advisory_data, pin, days=7)

        weather_alert: Optional[dict[str, Any]] = None
        try:
            weather_alert = weather_future.result()
        except Exception as exc:
            errors.append(f"weather_alert: {exc}")

        seasonal: Optional[dict[str, Any]] = None
        try:
            seasonal = seasonal_future.result()
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


def _fresh_entry(key: str, ttl_sec: int) -> Optional[dict[str, Any]]:
    """Cached data for `key` if still within its lifetime, else None."""
    with _lock:
        cached = _store.get(key)
        if not cached:
            return None
        fetched_at, data = cached
        limit = ttl_sec if _is_usable(data) else min(ttl_sec, _FAILED_TTL_SEC)
        if _now() - fetched_at < limit:
            _store.move_to_end(key)
            return data
    return None


def _save(key: str, data: dict[str, Any]) -> None:
    with _lock:
        _store[key] = (_now(), data)
        _store.move_to_end(key)
        while len(_store) > _MAX_STORE_ENTRIES:
            _store.popitem(last=False)


def get_pincode_data(pin: str, force_refresh: bool = False, ttl_sec: Optional[int] = None) -> dict[str, Any]:
    """The one call any agent makes. Returns the same shape every time,
    from memory if fresh, rebuilt from live sources if stale/missing.
    ttl_sec=None uses the configured lifetime (WEATHER_CACHE_TTL_HOURS,
    default 12h); a caller can still pass its own."""
    pin = " ".join(str(pin).split())
    if not pin:
        raise ValueError("pin is required")
    key = _cache_key(pin)
    ttl = _ttl_seconds() if ttl_sec is None else ttl_sec

    if not force_refresh:
        fresh = _fresh_entry(key, ttl)
        if fresh is not None:
            return fresh

    with _lock:
        key_lock = _build_locks.setdefault(key, threading.Lock())
    try:
        with key_lock:
            # Another request may have fetched this place while we waited.
            if not force_refresh:
                fresh = _fresh_entry(key, ttl)
                if fresh is not None:
                    return fresh

            data = _build(pin)
            if _is_usable(data):
                _save(key, data)
                _log.info("pincode_store refreshed pin=%s errors=%s", pin, data["errors"])
                return data

            with _lock:
                previous = _store.get(key)
            if previous is not None and _is_usable(previous[1]):
                _log.warning(
                    "pincode_store refresh failed pin=%s errors=%s -- serving older data",
                    pin, data["errors"],
                )
                return {**previous[1], "stale": True}

            _save(key, data)
            _log.warning("pincode_store refresh failed pin=%s errors=%s", pin, data["errors"])
            return data
    finally:
        with _lock:
            if _build_locks.get(key) is key_lock and not key_lock.locked():
                _build_locks.pop(key, None)


def peek(pin: str) -> Optional[dict[str, Any]]:
    """Read whatever's in memory without triggering a fetch. None if
    nothing's been loaded for this PIN yet."""
    with _lock:
        cached = _store.get(_cache_key(pin))
    return cached[1] if cached else None


def clear(pin: Optional[str] = None) -> None:
    """Drop one PIN's cached entry, or everything if pin is None. Mainly
    for tests."""
    with _lock:
        if pin is None:
            _store.clear()
        else:
            _store.pop(_cache_key(pin), None)
        