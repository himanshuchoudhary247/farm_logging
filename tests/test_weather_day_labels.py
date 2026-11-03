"""The weather tool tells the model which forecast date is today, tomorrow
and the day after tomorrow. Found in local testing: Kannada "ನಾಡದ್ದು" (day
after tomorrow) was answered with tomorrow's forecast, because the forecast
lists days by date only and the model had to work out the date itself."""
from datetime import date

from services.llm_service import bedrock_adapter
from services.weather_alert import adk_agent

FARMER = "9e95446d-c317-4074-b698-c8cc35325de6"


def test_day_labels_name_the_next_three_days():
    assert adk_agent._day_labels(date(2026, 11, 3)) == {
        "2026-11-03": "today",
        "2026-11-04": "tomorrow",
        "2026-11-05": "day after tomorrow",
    }


def test_day_labels_cross_a_month_and_a_year_end():
    assert list(adk_agent._day_labels(date(2026, 12, 31))) == ["2026-12-31", "2027-01-01", "2027-01-02"]


def test_day_labels_default_to_india_time():
    labels = adk_agent._day_labels()
    assert len(labels) == 3 and list(labels.values()) == ["today", "tomorrow", "day after tomorrow"]


def _tool(monkeypatch, farm=None):
    shared = {"pin": "411001", "forecast_days": [{"date": "2026-11-03"}, {"date": "2026-11-04"}, {"date": "2026-11-05"}]}
    monkeypatch.setattr(adk_agent, "get_farmer_by_id", lambda farmer_id: None)
    monkeypatch.setattr(adk_agent, "_farm_context", lambda farmer_id: farm)
    monkeypatch.setattr(adk_agent.flokiq_sync, "get_farm_pincode", lambda farmer_id: "411001")
    monkeypatch.setattr(adk_agent, "get_pincode_data", lambda loc: shared)
    fixed = adk_agent._day_labels(date(2026, 11, 3))
    monkeypatch.setattr(adk_agent, "_day_labels", lambda today=None: fixed)
    return adk_agent._make_get_weather_context_tool(FARMER), shared


def test_tool_result_carries_the_day_labels_without_touching_the_shared_data(monkeypatch):
    tool, shared = _tool(monkeypatch)
    result = tool("")
    assert result["day_labels"]["2026-11-05"] == "day after tomorrow"
    assert result["forecast_days"] == shared["forecast_days"]
    assert "day_labels" not in shared, "the cached pincode data is shared by every farmer"


def test_day_labels_come_with_the_farm_context_too(monkeypatch):
    tool, _ = _tool(monkeypatch, farm={"livestock": {"goat": 3}, "recent_health_issues": []})
    result = tool("")
    assert result["your_farm"] == {"livestock": {"goat": 3}, "recent_health_issues": []}
    assert result["day_labels"]["2026-11-04"] == "tomorrow"


def test_no_day_labels_on_an_error_result(monkeypatch):
    monkeypatch.setattr(adk_agent, "get_farmer_by_id", lambda farmer_id: None)
    monkeypatch.setattr(adk_agent.flokiq_sync, "get_farm_pincode", lambda farmer_id: None)
    result = adk_agent._make_get_weather_context_tool(FARMER)("")
    assert result["error"] == "no_location" and "day_labels" not in result


def test_instruction_tells_the_model_to_use_the_day_labels():
    assert "day_labels" in adk_agent._INSTRUCTION
    assert "ನಾಡದ್ದು" in adk_agent._INSTRUCTION and "ఎల్లుండి" in adk_agent._INSTRUCTION


def test_booking_extraction_knows_both_kannada_spellings():
    assert bedrock_adapter._says_day_after_tomorrow("ನಾಡಿದ್ದು ಬೆಳಿಗ್ಗೆ ಡಾಕ್ಟರ್ ಬೇಕು")
    assert bedrock_adapter._says_day_after_tomorrow("ನಾಡದ್ದು ಹವಾಮಾನ ಹೇಗಿರುತ್ತದೆ?")
    assert not bedrock_adapter._says_day_after_tomorrow("ನಾಳೆ ಹವಾಮಾನ ಹೇಗಿರುತ್ತದೆ?")
