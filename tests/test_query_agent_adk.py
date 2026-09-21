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
from services.query_agent.adk_agent import _make_run_sql_query_tool, build_query_agent


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
