"""Utility helpers for Indian Mandi (APMC) price feeds.

Consumes the public Mandi API (https://mandi-api.onrender.com/v1) to
retrieve wholesale market prices and prepare livestock feed commodity
snapshots for the Farmer Livestock Assistant.
"""

from __future__ import annotations

import time
from typing import Any, Iterable

import requests


MANDI_API_BASE = "https://mandi-api.onrender.com/v1"
_CACHE_TTL_SEC = 6 * 60 * 60  # six hours
_cache: dict[str, tuple[float, Any]] = {}

FEED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Maize": ("maize",),
    "Jowar (Sorghum)": ("jowar", "sorghum"),
    "Bajra (Pearl Millet)": ("bajra", "pearl millet", "cumbu"),
    "Soyabean": ("soyabean", "soybean"),
    "Groundnut": ("groundnut", "peanut"),
    "Wheat": ("wheat",),
    "Mustard Seed": ("mustard",),
}


def _cache_get(key: str) -> Any:
    item = _cache.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > _CACHE_TTL_SEC:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.time(), value)


def _request_json(path: str, params: dict[str, Any]) -> Any:
    url = f"{MANDI_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network failure path
            last_error = exc
            if attempt < 2:
                time.sleep(0.4 * (attempt + 1))
                continue
            raise RuntimeError(f"Mandi API request failed: {exc}") from exc
    raise RuntimeError(f"Mandi API request failed: {last_error}")


def fetch_prices(state: str, commodity: str | None = None) -> dict[str, Any]:
    state_param = (state or "").strip()
    if not state_param:
        raise ValueError("state is required")

    cache_key = f"prices:{state_param.lower()}:{(commodity or 'all').lower()}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    params: dict[str, Any] = {"state": state_param}
    if commodity:
        params["commodity"] = commodity

    data = _request_json("prices", params)
    _cache_set(cache_key, data)
    return data


def _matches_feed_keyword(name: str, tokens: tuple[str, ...]) -> bool:
    n = (name or "").lower()
    return any(token in n for token in tokens)


def summarize_feed_prices(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for label, tokens in FEED_KEYWORDS.items():
        matches = [r for r in records if _matches_feed_keyword(str(r.get("commodity", "")), tokens)]
        if not matches:
            continue

        modal_prices = [r.get("modal_price") for r in matches if isinstance(r.get("modal_price"), (int, float))]
        if not modal_prices:
            continue

        latest = max(
            (r for r in matches if isinstance(r.get("arrival_date"), str)),
            default=None,
            key=lambda r: (r.get("arrival_date") or "", r.get("fetched_at") or ""),
        )

        entry: dict[str, Any] = {
            "commodity": label,
            "modal_price_avg": round(sum(modal_prices) / len(modal_prices), 1),
            "modal_price_min": int(min(modal_prices)),
            "modal_price_max": int(max(modal_prices)),
            "market_count": len({r.get("market") for r in matches if r.get("market")}),
        }

        if latest:
            entry["arrival_date"] = latest.get("arrival_date")
            entry["latest_modal_price"] = latest.get("modal_price")
            market = latest.get("market") or ""
            district = latest.get("district") or ""
            if market or district:
                entry["sample_market"] = f"{market}{f' · {district}' if district else ''}".strip(" ·")

        summaries.append(entry)

    summaries.sort(key=lambda item: item["commodity"].lower())
    return summaries


def get_feed_price_snapshot(state: str, commodity: str | None = None) -> dict[str, Any]:
    payload = fetch_prices(state, commodity=commodity)
    data = payload.get("data") or []
    meta = payload.get("meta") or {}
    return {
        "state": meta.get("state") or state,
        "latest_fetched_at": meta.get("latest_fetched_at"),
        "commodities": summarize_feed_prices(data),
    }


__all__ = [
    "fetch_prices",
    "summarize_feed_prices",
    "get_feed_price_snapshot",
    "FEED_KEYWORDS",
]
