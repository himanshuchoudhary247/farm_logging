"""IMD (India Meteorological Department) warning fetcher.

Attempts to pull district-level weather warnings from IMD's public endpoints.
As of Aug 2026, IMD's mausam.imd.gov.in RSS feeds and API paths are returning
404 due to a site restructure. This module attempts known endpoints, parses any
JSON/XML it finds, and degrades gracefully with an honest status label so the
UI can show "IMD: endpoint unavailable" instead of faking data.

When IMD re-enables their public API or the user registers an API key, this
module is the single place to update.
"""

from __future__ import annotations

import re
from typing import Any

import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (farm-logging alert fetcher)"}

_IMD_ENDPOINTS = [
    "https://mausam.imd.gov.in/responsive/rss/daily_warning.php",
    "https://mausam.imd.gov.in/api/nwp_data_rev1.json",
    "https://api.imd.gov.in/apiproxy/api/climate/weather",
]

_STATE_CODE = {
    "rajasthan": "rj", "karnataka": "ka", "tamil nadu": "tn",
    "telangana": "tg", "andhra pradesh": "ap",
}


def _parse_rss_warnings(xml_text: str, state: str, district: str) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    items = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)
    state_low = state.lower()
    district_low = district.lower()
    for item in items[:30]:
        title = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
        desc = re.search(r"<description>(.*?)</description>", item, re.DOTALL)
        if not title:
            continue
        text = title.group(1).strip()
        if state_low in text.lower() or district_low in text.lower():
            warnings.append({
                "source": "IMD",
                "title": text,
                "description": desc.group(1).strip() if desc else "",
                "district": district,
                "state": state,
            })
    return warnings


def fetch_imd_warnings(district: str, state: str) -> dict[str, Any]:
    """Attempt to fetch IMD district warnings. Returns {status, warnings}."""
    for url in _IMD_ENDPOINTS:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=12)
            if resp.status_code != 200 or len(resp.text) < 50:
                continue
            if "xml" in resp.headers.get("content-type", "").lower() or "<rss" in resp.text[:500]:
                warnings = _parse_rss_warnings(resp.text, state, district)
                if warnings:
                    return {"source": "IMD", "status": "ok", "warnings": warnings}
                return {"source": "IMD", "status": "no_match", "warnings": [], "note": f"No IMD warnings found for {district}."}
        except Exception:
            continue

    return {
        "source": "IMD",
        "status": "unavailable",
        "warnings": [],
        "note": "IMD public API endpoint currently unavailable (site restructure). Register an IMD API key for official feeds.",
    }