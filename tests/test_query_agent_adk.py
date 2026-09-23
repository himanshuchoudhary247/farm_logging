"""Tests for the ADK-native query_agent rebuild (Phase 1 of the orchestration
migration, see /Users/sudhanshu/.claude/plans/elegant-roaming-river.md).

google-adk requires Python 3.10+ and is only installed in the project's venv
(python3.13), not in whatever system `python3` this repo's test suite has
historically been run with (3.9.6) -- importorskip keeps `python3 -m pytest`
green as before, while `venv/bin/python3.13 -m pytest` runs these for real.
No test here makes a live Bedrock call -- only the deterministic, farmer-
scoped tool closure is exercised directly, matching this suite's existing
convention of never calling the real LLM in automated tests.
"""
from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

from services.query_agent import db as query_db
from services.query_agent.adk_agent import (
    _localize_columns,
    _localize_numbers,
    _make_run_sql_query_tool,
    build_query_agent,
    detect_language,
)


def test_run_sql_query_tool_is_scoped_to_its_farmer():
    """farmer_id is bound into the closure at construction time -- the tool
    signature exposed to the model takes only `sql`, so no prompt can ever
    redirect a query at a different farmer's data."""
    query_db.clear_cache("adk-tool-farmer")
    tool = _make_run_sql_query_tool("adk-tool-farmer")
    result = tool(sql="SELECT COUNT(*) as c FROM farmers")
    assert result["success"] is True
    assert result["row_count"] <= 1  # this farmer's own row only, never all farmers


def test_run_sql_query_tool_rejects_blocked_sql_as_dict_not_raise():
    """execute_query raises ValueError for a rejected (non-SELECT) query --
    the tool must catch it and return a dict, since ADK tools report failure
    to the model as a normal result, not an exception."""
    tool = _make_run_sql_query_tool("adk-tool-farmer-2")
    result = tool(sql="DROP TABLE animals")
    assert result == {"success": False, "error": "Only SELECT queries are allowed"}


def test_build_query_agent_wires_model_and_tool():
    agent = build_query_agent("adk-build-farmer")
    assert agent.name == "query_agent"
    assert len(agent.tools) == 1
    assert "bedrock/" in agent.model.model


def test_detect_language_from_script():
    assert detect_language("मेरे पास कितने जानवर हैं") == "hi"
    assert detect_language("எனக்கு எத்தனை மாடுகள் உள்ளன") == "ta"
    assert detect_language("నా దగ్గర ఎన్ని జంతువులు ఉన్నాయి") == "te"
    assert detect_language("ನನ್ನ ಬಳಿ ಎಷ್ಟು ಪ್ರಾಣಿಗಳಿವೆ") == "kn"
    assert detect_language("how many animals do I have") == "en"
    assert detect_language("12") == "en"


def test_localize_numbers_converts_digits_recursively():
    assert _localize_numbers("You have 53 animals", "hi") == "You have ५३ animals"
    assert _localize_numbers(53, "hi") == "५३"
    assert _localize_numbers(53, "en") == 53, "English must be a no-op, not stringified"
    assert _localize_numbers({"count": 12, "label": "goats"}, "ta") == {"count": "௧௨", "label": "goats"}
    assert _localize_numbers([1, 2, 3], "te") == ["౧", "౨", "౩"]
    assert _localize_numbers(True, "hi") is True, "a bool must never be treated as a number to convert"


def test_localize_columns_translates_known_fields_leaves_unknown_alone():
    result = _localize_columns(["species", "breed", "COUNT(*)"], "kn")
    assert result == ["ಪ್ರಭೇದ", "ತಳಿ", "COUNT(*)"], "an aggregate/alias column isn't in the catalog, left as-is rather than guessed"
    assert _localize_columns(["species"], "en") == ["species"], "English must be a no-op"
    assert _localize_columns(None, "hi") is None
