"""OpenAI-Chat-Completions bridge used as an optional Bedrock fallback.

Enabled per-process by setting `LLM_PROVIDER=freellmapi`. When active,
BedrockTextAdapter.complete() and .converse_with_tool() route to
`${FREELLM_BASE_URL}/v1/chat/completions` (default:
`http://localhost:3001/v1`) instead of AWS Bedrock. Every other code
path in the app is untouched -- adapters keep their existing signatures
and callers change nothing.

Intended as a personal-dev escape hatch while the AWS Bedrock account
outage persists: point a locally-running freellmapi router (or any other
OpenAI-compatible endpoint -- llama.cpp, LM Studio, Ollama, etc.) at
this bridge and the same code that normally hits Bedrock runs against
free-tier providers instead. NOT for production, NOT for the shared
demo backend -- the upstream free-tier providers' ToS universally
forbid serving other users' traffic through them.

Translation shape:
- Bedrock Converse `messages` `[{role, content: str}]` -> OpenAI Chat
  `[{role, content: str}]` (same shape, no change).
- Bedrock `system` (str) -> prepended as a `{"role": "system"}` message.
- Bedrock `toolConfig.tools[0].toolSpec` -> OpenAI `tools[0].function`.
- Bedrock `toolChoice.tool.name=X` -> OpenAI
  `tool_choice={"type":"function","function":{"name":X}}`.
- OpenAI response `choices[0].message.tool_calls[0].function.arguments`
  (JSON string) is parsed and returned in the Bedrock-shaped dict
  `{tool_name, tool_input, text, stop_reason}` -- callers do not know
  which provider produced the response.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

_log = logging.getLogger("freellmapi")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)


def is_active() -> bool:
    """True iff the fallback bridge should intercept adapter calls this
    process. Checked once per call, cheap. Default off."""
    return os.getenv("LLM_PROVIDER", "").strip().lower() == "freellmapi"


def _base_url() -> str:
    return (os.getenv("FREELLM_BASE_URL") or "http://localhost:3001/v1").rstrip("/")


def _api_key() -> str:
    return os.getenv("FREELLM_API_KEY", "")


def _model_for(task: str) -> str:
    """Per-task model override. `auto` (freellmapi's own router) is the
    default -- users can pin a specific model per tier via
    FREELLM_MODEL_EXTRACTION / _GENERATION / _LONG_FORM / _LEGACY."""
    tier = task.upper() if task else "LEGACY"
    return os.getenv(f"FREELLM_MODEL_{tier}") or os.getenv("FREELLM_MODEL") or "auto"


def _headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _to_openai_messages(messages: List[Dict[str, Any]], system: Optional[str]) -> List[Dict[str, str]]:
    """Bedrock-adapter callers pass plain `{role, content: str}` dicts, so
    the message list itself needs no shape change. A system prompt travels
    as a separate arg -- prepend it as an OpenAI system message."""
    out: List[Dict[str, str]] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            # Defensive: some callers might already build Bedrock's rich
            # content list -- flatten text blocks back to a plain string.
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        out.append({"role": role, "content": content})
    return out


def _tool_spec_to_openai(tool_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Bedrock toolSpec `{name, description, inputSchema.json}` ->
    OpenAI function `{name, description, parameters}`."""
    schema = tool_spec.get("inputSchema", {}).get("json") or {}
    return {
        "type": "function",
        "function": {
            "name": tool_spec["name"],
            "description": tool_spec.get("description", ""),
            "parameters": schema,
        },
    }


def complete(task: str, messages: List[Dict[str, Any]], system: Optional[str],
             max_tokens: int, temperature: float) -> str:
    """Free-text completion. Returns the assistant's message content as a
    plain string, matching BedrockTextAdapter.complete()."""
    payload = {
        "model": _model_for(task),
        "messages": _to_openai_messages(messages, system),
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    t0 = time.time()
    resp = requests.post(
        f"{_base_url()}/chat/completions",
        json=payload,
        headers=_headers(),
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    choices = body.get("choices") or []
    text = ""
    if choices:
        message = choices[0].get("message") or {}
        text = message.get("content") or ""
    usage = body.get("usage") or {}
    _log.info(
        "LATENCY freellmapi task=%s model=%s ms=%.0f in_tok=%s out_tok=%s",
        task, payload["model"], (time.time() - t0) * 1000,
        usage.get("prompt_tokens"), usage.get("completion_tokens"),
    )
    return text


def converse_with_tool(task: str, messages: List[Dict[str, Any]],
                        tool_spec: Dict[str, Any], system: Optional[str],
                        tool_choice_name: Optional[str],
                        max_tokens: int, temperature: float) -> Dict[str, Any]:
    """Forced tool call. Returns the Bedrock-shaped
    `{tool_name, tool_input, text, stop_reason}` dict so callers don't
    have to know which provider produced the response."""
    openai_tool = _tool_spec_to_openai(tool_spec)
    tool_choice: Any
    if tool_choice_name:
        tool_choice = {"type": "function", "function": {"name": tool_choice_name}}
    else:
        tool_choice = "required"
    payload = {
        "model": _model_for(task),
        "messages": _to_openai_messages(messages, system),
        "tools": [openai_tool],
        "tool_choice": tool_choice,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    t0 = time.time()
    resp = requests.post(
        f"{_base_url()}/chat/completions",
        json=payload,
        headers=_headers(),
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()

    choices = body.get("choices") or []
    tool_name: Optional[str] = None
    tool_input: Dict[str, Any] = {}
    text: Optional[str] = None
    stop_reason: Optional[str] = None
    if choices:
        choice = choices[0]
        stop_reason = choice.get("finish_reason")
        message = choice.get("message") or {}
        text = message.get("content") or None
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            first = tool_calls[0]
            fn = first.get("function") or {}
            tool_name = fn.get("name")
            raw_args = fn.get("arguments")
            if isinstance(raw_args, str):
                try:
                    tool_input = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    # A provider that streamed a truncated/malformed
                    # tool-call payload -- match Bedrock's "no tool call"
                    # shape rather than crash the request handler.
                    _log.warning("freellmapi tool_call arguments were not valid JSON: %r", raw_args[:200])
                    tool_input = {}
            elif isinstance(raw_args, dict):
                tool_input = raw_args

    usage = body.get("usage") or {}
    _log.info(
        "LATENCY freellmapi task=%s model=%s ms=%.0f in_tok=%s out_tok=%s stop=%s tool=%s",
        task, payload["model"], (time.time() - t0) * 1000,
        usage.get("prompt_tokens"), usage.get("completion_tokens"),
        stop_reason, tool_name,
    )
    return {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "text": text,
        "stop_reason": stop_reason,
    }
