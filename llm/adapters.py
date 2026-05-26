from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Optional

import requests
from openai import OpenAI

from llm.config import get_api_key, load_llm_config


class TextAdapter(ABC):
    @abstractmethod
    def complete(self, messages: list[dict[str, str]], system: Optional[str] = None) -> str:
        pass


class OpenAIAdapter(TextAdapter):
    def __init__(self, model: str, api_key_env: str) -> None:
        self._model = model
        self._client = OpenAI(api_key=get_api_key(api_key_env.strip()))

    def complete(self, messages: list[dict[str, str]], system: Optional[str] = None) -> str:
        api_messages: list[dict[str, str]] = []
        if system:
            api_messages.append({"role": "system", "content": system})
        api_messages.extend(messages)
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=api_messages,
        )
        choice = resp.choices[0].message.content
        return choice or ""


class GeminiAdapter(TextAdapter):
    def __init__(self, model: str, api_key_env: str) -> None:
        self._api_key = get_api_key(api_key_env.strip())
        self._model_name = model

    def complete(self, messages: list[dict[str, str]], system: Optional[str] = None) -> str:
        contents: list[dict[str, Any]] = []
        if system and system.strip():
            contents.append(
                {
                    "role": "user",
                    "parts": [{"text": f"System instruction: {system.strip()}"}],
                }
            )
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        if not contents:
            return ""

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model_name}:generateContent"
        )
        resp = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "X-goog-api-key": self._api_key,
            },
            json={"contents": contents},
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return ""


class BedrockAdapter(TextAdapter):
    """Amazon Bedrock via ``bedrock-runtime`` Converse API (IAM auth)."""

    def __init__(
        self,
        model_id: str,
        region: Optional[str] = None,
        profile_name: Optional[str] = None,
    ) -> None:
        import boto3
        from botocore.config import Config

        self._model_id = model_id
        resolved_region = (region or os.environ.get("AWS_REGION") or "us-east-1").strip()
        session_kw: dict[str, Any] = {}
        if profile_name and profile_name.strip():
            session_kw["profile_name"] = profile_name.strip()
        session = boto3.Session(**session_kw)
        self._client = session.client(
            "bedrock-runtime",
            region_name=resolved_region,
            config=Config(retries={"max_attempts": 5, "mode": "standard"}),
        )

    def complete(self, messages: list[dict[str, str]], system: Optional[str] = None) -> str:
        br_messages: list[dict[str, Any]] = []
        for m in messages:
            role = m["role"]
            if role == "user":
                br_messages.append({"role": "user", "content": [{"text": m["content"]}]})
            elif role == "assistant":
                br_messages.append({"role": "assistant", "content": [{"text": m["content"]}]})

        if not br_messages:
            return ""

        kwargs: dict[str, Any] = {
            "modelId": self._model_id,
            "messages": br_messages,
            "inferenceConfig": {"maxTokens": 4096},
        }
        sy = (system or "").strip()
        if sy:
            kwargs["system"] = [{"text": sy}]

        response = self._client.converse(**kwargs)
        out_msg = response.get("output", {}).get("message", {})
        blocks = out_msg.get("content") or []
        for block in blocks:
            if isinstance(block, dict) and "text" in block:
                return str(block["text"])
        return ""


def get_text_adapter() -> TextAdapter:
    cfg = load_llm_config().text
    p = cfg.provider.lower().strip()
    if p == "openai":
        return OpenAIAdapter(cfg.model, cfg.api_key_env)
    if p in ("gemini", "google"):
        return GeminiAdapter(cfg.model, cfg.api_key_env)
    if p in ("bedrock", "aws-bedrock"):
        return BedrockAdapter(
            cfg.model,
            region=cfg.region,
            profile_name=cfg.aws_profile,
        )
    raise ValueError(f"Unknown text.provider: {cfg.provider}")
