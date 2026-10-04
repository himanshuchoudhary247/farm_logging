"""Builds the LiteLlm model object used by the ADK agents.

The ADK agents (router classifier, query agent, weather agent) talk to the
LLM through LiteLLM directly, not through BedrockTextAdapter, so the
LLM_PROVIDER=freellmapi fallback in freellmapi_adapter.py never reached
them and /chat/turn kept hitting Bedrock. This helper is the single place
that decides which backend an ADK agent uses:

- LLM_PROVIDER unset (default): Bedrock, exactly as before.
- LLM_PROVIDER=freellmapi: the same OpenAI-compatible endpoint the adapter
  fallback uses (FREELLM_BASE_URL, FREELLM_API_KEY, FREELLM_MODEL, the
  per-tier FREELLM_MODEL_<TIER> overrides and FREELLM_EXTRA_BODY).

Personal-dev only, same as the adapter fallback.
"""
from __future__ import annotations

import logging
from typing import Any

from google.adk.models.lite_llm import LiteLlm

from services.llm_service import freellmapi_adapter

_log = logging.getLogger(__name__)


def build_adk_model(task: Any, bedrock_model_id: str, temperature: float) -> LiteLlm:
    """Return the LiteLlm model for an ADK Agent.

    Args:
        task: the TaskTier (or its string value) the agent runs at; picks
            the per-tier FREELLM_MODEL_<TIER> override in fallback mode.
        bedrock_model_id: the Bedrock model id from model_for_task(); used
            unchanged when the fallback is off.
        temperature: sampling temperature, passed through in both modes.
    """
    if not freellmapi_adapter.is_active():
        return LiteLlm(model=f"bedrock/{bedrock_model_id}", temperature=temperature)

    cfg = freellmapi_adapter.openai_compat_config(getattr(task, "value", task))
    _log.info("ADK agent using LLM_PROVIDER=freellmapi model=%s base=%s", cfg["model"], cfg["base_url"])
    kwargs: dict[str, Any] = {
        "model": f"openai/{cfg['model']}",
        "api_base": cfg["base_url"],
        # The OpenAI client refuses an empty key; local routers that do not
        # check auth simply ignore this placeholder.
        "api_key": cfg["api_key"] or "unused",
        "temperature": temperature,
    }
    if cfg["extra_body"]:
        kwargs["extra_body"] = cfg["extra_body"]
    return LiteLlm(**kwargs)
