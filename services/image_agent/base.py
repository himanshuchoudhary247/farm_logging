"""The contract every photo agent follows.

A farmer sends one photo, an optional question, and (when they tapped a
suggestion chip in the app) a task. An agent gets an ImageRequest and returns
an ImageResult. The route (/farmers/{id}/chat/image-turn) and the app only
know this contract, so a new agent -- a real vision sub-agent, a model call,
an outside service -- is added without touching either of them. See
registry.py for how the agent for a task is chosen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# What the photo is about. The app's suggestion chips send one of these, so
# an agent knows the job without spending a model call to work it out.
# "general" covers a typed question, or a photo sent with no question.
TASKS = ("general", "health", "breed", "weight", "count")


@dataclass(frozen=True)
class ImageRequest:
    farmer_id: str
    session_id: str
    language: str  # one of SUPPORTED_LANGUAGES, e.g. "hi-IN"
    task: str  # one of TASKS
    text: str  # the farmer's question; may be empty
    image: bytes
    content_type: str  # "image/jpeg", "image/png" or "image/webp"


@dataclass
class ImageResult:
    reply_text: str  # shown in the chat bubble, in the farmer's language
    # Structured answer for the task, e.g. {"count": 10} or
    # {"weight_kg": 32.5, "range_kg": [29, 36]}. Free-form so a new task does
    # not need a new contract; empty when the agent has no structured answer.
    data: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ImageAgent(Protocol):
    name: str

    def analyze(self, request: ImageRequest) -> ImageResult:
        """Answer one photo turn. Raise on failure; the route turns any
        exception into a clean error for the app."""
        ...
