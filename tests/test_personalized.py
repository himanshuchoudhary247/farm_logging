from __future__ import annotations

from services.advisory.personalized import generate_personalized_recommendation


def test_generate_personalized_recommendation_merges_actions():
    farmer_profile = {
        "farmer_id": "F001",
        "name": "Ramu",
        "livestock": [
            {"type": "sheep", "count": 120},
            {"type": "dairy_cattle", "count": 30},
        ],
        "current_issues": ["Foot rot in flock"],
        "recent_vet_visits": ["2026-08-10"],
    }

    general_alert = {
        "pin": "583101",
        "weather": {
            "risk_level": "medium",
            "summary": "Moderate storms expected",
            "advisories": ["Move livestock to covered shelter before evening."],
        },
        "heat": {"level": "high", "reason": "THI 84"},
        "feed_market": {
            "commodities": [
                {"commodity": "Maize", "modal_price_avg": 1820, "modal_price_min": 1750, "modal_price_max": 1900}
            ]
        },
    }

    rec = generate_personalized_recommendation(farmer_profile, general_alert)

    assert rec["farmer_id"] == "F001"
    assert any("hoof" in action.lower() for action in rec["actions"])
    assert any("electrolyte" in action.lower() for action in rec["actions"])
    assert rec["feed_market_highlights"][0]["commodity"] == "Maize"
