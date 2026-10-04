"""Unified LLM + tool telemetry.

One canonical log emitter for every LLM round-trip and every tool call
across the app, plus ADK callback factories that hook the emitter into
LlmAgent's before/after model + tool callbacks.

Before this module, four different call sites in the adapters formatted
their own "LATENCY bedrock task=... model=... ms=... in_tok=..." log
lines with slightly different field orders, and the three ADK agents
(classifier, query_agent, weather_alert) had no per-turn telemetry at
all -- their LLM calls went through LiteLlm without any local logging
except what LiteLLM itself emitted. This gives us:

- ONE log-line format across every provider (Bedrock, Groq via
  freellmapi_adapter, LiteLlm-wrapped ADK agents) -- one grep target.
- ONE place to add cost tracking later (task #32).
- ONE place to add per-call structured fields (cache_hit, retry_count,
  etc) without touching each adapter.
- ADK agents get real per-call timing they never had before.

Design: space-separated `k=v` pairs so `_log.info` output stays
grep-friendly today, but the fields dict is a first-class object so
migrating to real JSON logging later is a one-line change in
`_emit()`.

Callbacks are defensive -- any exception inside a telemetry hook is
swallowed so a bug here can never crash a farmer's chat turn.
"""
from __future__ import annotations

import contextvars
import json
import logging
import time
from typing import Any, Optional

_log = logging.getLogger("llm_telemetry")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)


def _emit(kind: str, fields: dict) -> None:
    """Central log emit -- change once here to switch to JSON output."""
    parts = [f"{k}={v}" for k, v in fields.items() if v is not None and v != ""]
    _log.info("%s %s", kind, " ".join(parts))


def _short(obj: Any, n: int = 80) -> Optional[str]:
    """Bounded preview of an arg/result for logging. Never exceeds n chars,
    never contains newlines (would break single-line log ingestion)."""
    if obj is None:
        return None
    try:
        if isinstance(obj, (dict, list)):
            s = json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
        else:
            s = str(obj)
    except Exception:
        s = repr(obj)
    s = s.replace("\n", " ").replace("\r", " ")
    return s[:n] + ("…" if len(s) > n else "")


def log_llm_call(
    *,
    agent_name: str,
    provider: str,
    model: Optional[str],
    task: Optional[str] = None,
    latency_ms: Optional[float] = None,
    in_tok: Optional[int] = None,
    out_tok: Optional[int] = None,
    stop_reason: Optional[str] = None,
    tool_name: Optional[str] = None,
    cache_hit: Optional[bool] = None,
    error: Optional[str] = None,
) -> None:
    """Structured log for one LLM round-trip. Replaces the ad-hoc
    "LATENCY bedrock task=... model=..." format strings in the adapters."""
    fields = {
        "agent": agent_name,
        "provider": provider,
        "model": model,
        "task": task,
        "ms": f"{latency_ms:.0f}" if latency_ms is not None else None,
        "in_tok": in_tok,
        "out_tok": out_tok,
        "stop": stop_reason,
        "tool": tool_name,
        "cache_hit": cache_hit,
        "error": error,
    }
    _emit("llm", fields)


def log_tool_call(
    *,
    agent_name: str,
    tool_name: str,
    latency_ms: Optional[float] = None,
    args_preview: Optional[str] = None,
    result_preview: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Structured log for one tool execution. args/result are pre-bounded
    (see _short) so a huge SQL row-set or a long generated SQL string
    can't blow up the log line."""
    fields = {
        "agent": agent_name,
        "tool": tool_name,
        "ms": f"{latency_ms:.0f}" if latency_ms is not None else None,
        "args": args_preview,
        "result": result_preview,
        "error": error,
    }
    _emit("tool", fields)


# ---- ADK callback factories ---------------------------------------------
#
# ADK's LlmAgent invokes callbacks in a specific order:
#   before_model_callback -> model call -> after_model_callback
#   before_tool_callback  -> tool call  -> after_tool_callback
# with on_model_error_callback / on_tool_error_callback for failures.
#
# We need to pass a start-time from before -> after. Attaching to the
# LlmRequest / tool object fails on pydantic v2 (extra attrs forbidden),
# so we use contextvars -- clean, async-safe, no cross-call leakage
# because each ADK invocation gets its own context.

_llm_start_var: contextvars.ContextVar[Optional[float]] = contextvars.ContextVar("_llm_start", default=None)
_tool_start_var: contextvars.ContextVar[Optional[float]] = contextvars.ContextVar("_tool_start", default=None)


def _usage_field(usage: Any, *names: str) -> Optional[int]:
    """usage_metadata's shape drifts across ADK versions (attr vs dict;
    prompt_token_count vs input_tokens). Try each candidate name and
    return the first non-None hit."""
    if usage is None:
        return None
    for n in names:
        v = getattr(usage, n, None)
        if v is not None:
            return v
        if isinstance(usage, dict) and usage.get(n) is not None:
            return usage.get(n)
    return None


def _first_tool_name(llm_response: Any) -> Optional[str]:
    """Best-effort: pull the first function_call name out of an
    LlmResponse, if any. Returns None if the response was pure text."""
    try:
        content = getattr(llm_response, "content", None)
        parts = getattr(content, "parts", None) or []
        for p in parts:
            fc = getattr(p, "function_call", None)
            if fc is not None:
                return getattr(fc, "name", None)
    except Exception:
        pass
    return None


def make_adk_callbacks(agent_name: str) -> dict:
    """Return a kwargs dict to spread into LlmAgent(...) for auto
    telemetry. Every callback wraps its body in try/except so a bug in
    the telemetry code can never crash a farmer's chat turn -- if a
    callback raises, we log the traceback but let ADK proceed."""

    def _safe(body):
        try:
            body()
        except Exception as exc:
            _log.warning("telemetry callback failed (agent=%s): %s", agent_name, exc)

    def before_model(context, llm_request):
        _safe(lambda: _llm_start_var.set(time.time()))
        return None

    def after_model(context, llm_response):
        def body():
            start = _llm_start_var.get()
            latency = (time.time() - start) * 1000 if start else None
            usage = getattr(llm_response, "usage_metadata", None)
            log_llm_call(
                agent_name=agent_name,
                provider="adk",
                model=getattr(llm_response, "model_version", None),
                latency_ms=latency,
                in_tok=_usage_field(usage, "prompt_token_count", "input_tokens"),
                out_tok=_usage_field(usage, "candidates_token_count", "output_tokens"),
                stop_reason=str(getattr(llm_response, "finish_reason", None) or "") or None,
                tool_name=_first_tool_name(llm_response),
            )
        _safe(body)
        return None

    def on_model_error(context, llm_request, exc):
        _safe(lambda: log_llm_call(
            agent_name=agent_name, provider="adk", model=None,
            error=type(exc).__name__,
        ))
        return None

    def before_tool(tool, args, tool_context, *_extra):
        _safe(lambda: _tool_start_var.set(time.time()))
        return None

    def after_tool(tool, args, tool_context, *rest):
        def body():
            start = _tool_start_var.get()
            latency = (time.time() - start) * 1000 if start else None
            # `rest` typically has (tool_response,) on success; skip if unknown.
            tool_response = rest[-1] if rest else None
            log_tool_call(
                agent_name=agent_name,
                tool_name=getattr(tool, "name", None) or type(tool).__name__,
                latency_ms=latency,
                args_preview=_short(args),
                result_preview=_short(tool_response),
            )
        _safe(body)
        return None

    def on_tool_error(tool, args, tool_context, exc, *_extra):
        _safe(lambda: log_tool_call(
            agent_name=agent_name,
            tool_name=getattr(tool, "name", None) or type(tool).__name__,
            args_preview=_short(args),
            error=type(exc).__name__,
        ))
        return None

    return {
        "before_model_callback": before_model,
        "after_model_callback": after_model,
        "on_model_error_callback": on_model_error,
        "before_tool_callback": before_tool,
        "after_tool_callback": after_tool,
        "on_tool_error_callback": on_tool_error,
    }
