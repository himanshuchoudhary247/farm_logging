"""Tests for services/common/adk_telemetry.py -- the unified LLM +
tool log emitter and the ADK callback factories that hook into it.

Doesn't require ADK to be installed (the emitter is plain Python); the
callback-factory test uses pytest.importorskip so it only runs where
google-adk is available (venv python3.13, not system python3.9).
"""
from __future__ import annotations

import logging

import pytest

from services.common.adk_telemetry import (
    _short,
    log_llm_call,
    log_tool_call,
)


def test_log_llm_call_emits_structured_line(caplog):
    with caplog.at_level(logging.INFO, logger="llm_telemetry"):
        log_llm_call(
            agent_name="query_agent",
            provider="bedrock",
            model="deepseek.v3-v1:0",
            task="extraction",
            latency_ms=123.4,
            in_tok=100,
            out_tok=50,
            stop_reason="tool_use",
            tool_name="run_sql_query",
        )
    lines = [r.message for r in caplog.records if r.name == "llm_telemetry"]
    assert len(lines) == 1
    msg = lines[0]
    assert msg.startswith("llm ")
    for expected in ("agent=query_agent", "provider=bedrock", "model=deepseek.v3-v1:0",
                     "task=extraction", "ms=123", "in_tok=100", "out_tok=50",
                     "stop=tool_use", "tool=run_sql_query"):
        assert expected in msg, f"missing '{expected}' in emitted log: {msg}"


def test_log_llm_call_omits_none_fields(caplog):
    """None/empty fields must not appear as `foo=None` in the log line --
    the emitter's job is to keep lines tight and grep-friendly."""
    with caplog.at_level(logging.INFO, logger="llm_telemetry"):
        log_llm_call(agent_name="a", provider="p", model="m")
    msg = [r.message for r in caplog.records if r.name == "llm_telemetry"][0]
    assert "task=" not in msg
    assert "in_tok=" not in msg
    assert "stop=" not in msg
    assert "error=" not in msg


def test_log_tool_call_bounds_and_captures_previews(caplog):
    with caplog.at_level(logging.INFO, logger="llm_telemetry"):
        log_tool_call(
            agent_name="query_agent",
            tool_name="run_sql_query",
            latency_ms=45.0,
            args_preview="SELECT * FROM animals",
            result_preview='{"row_count":12}',
        )
    msg = [r.message for r in caplog.records if r.name == "llm_telemetry"][0]
    assert msg.startswith("tool ")
    assert "tool=run_sql_query" in msg
    assert "ms=45" in msg
    assert "args=SELECT * FROM animals" in msg
    assert "result=" in msg


def test_short_truncates_and_strips_newlines():
    assert _short(None) is None
    assert _short("hello") == "hello"
    long = "x" * 200
    out = _short(long, n=50)
    assert len(out) == 51  # 50 chars + trailing ellipsis
    assert out.endswith("…")
    # newlines/carriage-returns collapse to spaces so single-line log parsing works
    assert _short("a\nb\rc") == "a b c"
    # dicts become JSON, single line
    assert _short({"k": "v"}) == '{"k":"v"}'


def test_error_field_is_recorded(caplog):
    with caplog.at_level(logging.INFO, logger="llm_telemetry"):
        log_llm_call(agent_name="x", provider="bedrock", model="m", error="ThrottlingException")
    msg = [r.message for r in caplog.records if r.name == "llm_telemetry"][0]
    assert "error=ThrottlingException" in msg


def test_make_adk_callbacks_returns_all_six_hooks():
    pytest.importorskip("google.adk")
    from services.common.adk_telemetry import make_adk_callbacks
    cb = make_adk_callbacks("query_agent")
    assert set(cb.keys()) == {
        "before_model_callback", "after_model_callback", "on_model_error_callback",
        "before_tool_callback", "after_tool_callback", "on_tool_error_callback",
    }
    # All must be callable so LlmAgent(...) doesn't reject them.
    for name, fn in cb.items():
        assert callable(fn), f"{name} is not callable"


def test_callback_swallows_exceptions_never_crashes_the_turn(caplog):
    """Defensive requirement: a telemetry bug MUST NOT crash a real
    chat turn. Every callback wraps its body in try/except; a broken
    context/response should produce a warning and return None."""
    pytest.importorskip("google.adk")
    from services.common.adk_telemetry import make_adk_callbacks
    cb = make_adk_callbacks("test_agent")

    class Broken:
        """Anything the callbacks might touch on this raises AttributeError."""
        def __getattr__(self, name):
            raise RuntimeError(f"induced failure on attr {name!r}")

    # Neither of these must raise -- they must swallow and log.
    assert cb["after_model_callback"](Broken(), Broken()) is None
    assert cb["on_model_error_callback"](Broken(), Broken(), RuntimeError("x")) is None
    assert cb["before_tool_callback"](Broken(), {}, Broken()) is None
    assert cb["after_tool_callback"](Broken(), {}, Broken(), Broken()) is None
    assert cb["on_tool_error_callback"](Broken(), {}, Broken(), RuntimeError("x")) is None
