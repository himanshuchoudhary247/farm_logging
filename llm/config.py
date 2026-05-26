from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TextLLMConfig(BaseModel):
    provider: str = Field(
        description="openai, gemini, google, or bedrock"
    )
    model: str
    api_key_env: str = ""
    region: Optional[str] = Field(
        default=None,
        description="AWS region for bedrock-runtime (falls back to AWS_REGION env)",
    )
    aws_profile: Optional[str] = Field(
        default=None,
        description="Optional named AWS profile for boto3",
    )


class VoiceLLMConfig(BaseModel):
    provider: str
    model: str
    api_key_env: str = ""
    region: Optional[str] = None
    aws_profile: Optional[str] = None


class LLMConfigFile(BaseModel):
    text: TextLLMConfig
    voice: VoiceLLMConfig


def load_llm_config_path() -> Path:
    env = os.environ.get("LLM_CONFIG_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return PROJECT_ROOT / "config" / "llm.yaml"


def load_llm_config(path: Optional[Path] = None) -> LLMConfigFile:
    p = path or load_llm_config_path()
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return LLMConfigFile.model_validate(raw)


def get_api_key(env_var: str) -> str:
    if not env_var or not env_var.strip():
        raise RuntimeError("api_key_env is empty; this provider requires an API key env var name")
    key = os.environ.get(env_var, "")
    if not key:
        raise RuntimeError(f"Missing API key: set environment variable {env_var}")
    return key
