from __future__ import annotations

from services.market_prices import mandi


def _record(commodity: str, modal_price: int, market: str, district: str, arrival: str = "2026-08-15"):
    return {
        "commodity": commodity,
        "modal_price": modal_price,
        "min_price": modal_price - 100,
        "max_price": modal_price + 100,
        "market": market,
        "district": district,
        "arrival_date": arrival,
        "fetched_at": f"{arrival}T12:00:00+00:00",
    }


def test_summarize_feed_prices_extracts_feed_commodities():
    records = [
        _record("Maize", 1800, "Belagavi APMC", "Belagavi"),
        _record("Jowar(Sorghum)", 2100, "Hubballi APMC", "Dharwad"),
        _record("Bajra(Pearl Millet/Cumbu)", 1950, "Raichur APMC", "Raichur"),
        _record("Soyabean", 5200, "Indore APMC", "Indore"),
        _record("Groundnut", 6100, "Anantapur APMC", "Anantapur"),
        _record("Wheat", 2400, "Lucknow APMC", "Lucknow"),
        _record("Mustard", 6200, "Jaipur APMC", "Jaipur"),
        _record("Tomato", 800, "Pune APMC", "Pune"),
    ]

    summary = mandi.summarize_feed_prices(records)
    commodities = {item["commodity"]: item for item in summary}

    assert "Maize" in commodities
    maize = commodities["Maize"]
    assert maize["modal_price_avg"] == 1800.0
    assert maize["modal_price_min"] == 1800
    assert maize["modal_price_max"] == 1800
    assert maize["sample_market"].startswith("Belagavi APMC")

    assert "Jowar (Sorghum)" in commodities
    assert "Tomato" not in commodities


def test_get_feed_price_snapshot_wraps_payload(monkeypatch):
    payload = {
        "meta": {"state": "Karnataka", "latest_fetched_at": "2026-08-15T10:00:00+00:00"},
        "data": [_record("Maize", 1750, "Belagavi APMC", "Belagavi")],
    }

    monkeypatch.setattr(mandi, "fetch_prices", lambda state, commodity=None: payload)

    snapshot = mandi.get_feed_price_snapshot("Karnataka")
    assert snapshot["state"] == "Karnataka"
    assert snapshot["commodities"]
    assert snapshot["commodities"][0]["commodity"] == "Maize"
