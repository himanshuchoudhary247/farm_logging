"""Best-effort ICAR / Kisan Suvidha advisory puller.

Kisan Suvidha publishes district-level agromet advisories (roughly 2x per
week). There is no public JSON API, so we scrape the advisory page and match
district keywords. Failures degrade gracefully: scan() treats a None digest
as "no advisory today" instead of raising.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from .config import KISAN_SUVIDHA_URL

_ADVISORY_URLS = [
    KISAN_SUVIDHA_URL,
    "https://farmer.gov.in/imdinterface/advisories.aspx",
    "https://kisansuvidha.gov.in/Default.aspx",
]

_HEADERS = {"User-Agent": "Mozilla/5.0 (farm-logging demo advisory fetcher)"}

_HARMFUL_WORDS = ["<script", "<style", "javascript:", "mailto:"]


def _clean_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _pick_advisory_paragraphs(text: str, district: str) -> list[str]:
    paragraphs = [p.strip() for p in text.split(".") if len(p.strip()) > 30]
    scored: list[tuple[int, str]] = []
    district_tokens = [t for t in re.split(r"[\s,/-]+", district.lower()) if t]
    for p in paragraphs:
        low = p.lower()
        if any(w in low for w in _HARMFUL_WORDS):
            continue
        district_score = sum(1 for t in district_tokens if t in low)
        if district_score == 0:
            continue
        score = district_score
        for kw in ("advisory", "agromet", "weather", "rain", "temperature", "livestock", "sheep", "goat"):
            if kw in low:
                score += 1
        scored.append((score, p))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [p for _, p in scored[:3]]


def fetch_district_advisory(district: str, state: str = "") -> dict[str, Any] | None:
    """Return {source, district, state, fetched_at, advisory} or None."""
    district = (district or "").strip()
    if not district:
        return None

    last_error: str | None = None
    for url in _ADVISORY_URLS:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            text = _clean_text(resp.text)
            if len(text) < 50:
                continue
            paragraphs = _pick_advisory_paragraphs(text, district)
            if paragraphs:
                return {
                    "source": "ICAR / Kisan Suvidha",
                    "source_url": url,
                    "district": district,
                    "state": state,
                    "advisory": " ".join(paragraphs),
                }
        except Exception as e:  # pragma: no cover - network dependent
            last_error = str(e)

    # No matching advisory found (or unreachable) -> not an emergency.
    return None


def advisory_digest(district: str, state: str = "") -> dict[str, Any]:
    result = fetch_district_advisory(district, state)
    if result:
        return result
    return {
        "source": "ICAR / Kisan Suvidha",
        "district": district,
        "state": state,
        "advisory": None,
        "note": "No district agromet advisory published yet this week.",
    }
