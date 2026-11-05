"""Which agent answers a photo turn.

Chosen per task from the environment, so a real agent replaces the stub with
one registry line and one .env change -- no route or app change:

  CHAT_IMAGE_AGENT          agent for every task (default "stub");
                            "off" switches photo turns off (the route answers 503)
  CHAT_IMAGE_AGENT_<TASK>   agent for one task only, e.g.
                            CHAT_IMAGE_AGENT_WEIGHT=animal_weight;
                            "off" switches only that task off

To add a real agent:
  1. write a class with `name` and `analyze(ImageRequest) -> ImageResult`
     (see base.py), e.g. services/image_agent/animal_weight.py;
  2. add it to _AGENTS below;
  3. set CHAT_IMAGE_AGENT_WEIGHT=animal_weight (or CHAT_IMAGE_AGENT for all).

An unknown agent name falls back to the stub with a warning, so a typo in
.env never breaks photo turns.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

from services.image_agent.base import TASKS, ImageAgent
from services.image_agent.stub import StubImageAgent

# A child of the "api" logger, so these lines print in the same terminal as
# the other route logs (main.py gives "api" its handler and INFO level).
_log = logging.getLogger("api.image_agent")

_OFF = {"off", "0", "false", "no", "none"}

# name -> factory. Factories, not instances, so an agent that loads a model
# or opens a client is only built when it is actually chosen.
_AGENTS: dict[str, Callable[[], ImageAgent]] = {
    "stub": StubImageAgent,
}

_cache: dict[str, ImageAgent] = {}
_cache_lock = threading.Lock()


def normalize_task(task: Optional[str]) -> str:
    """The task as one of TASKS; anything else is "general"."""
    value = (task or "").strip().lower()
    return value if value in TASKS else "general"


def agent_name_for(task: str) -> str:
    """The configured agent name for this task (may be an "off" value)."""
    specific = os.getenv(f"CHAT_IMAGE_AGENT_{task.upper()}", "").strip().lower()
    if specific:
        return specific
    return os.getenv("CHAT_IMAGE_AGENT", "stub").strip().lower() or "stub"


def get_agent(task: str) -> Optional[ImageAgent]:
    """The agent for this task, or None when photo turns are switched off."""
    name = agent_name_for(task)
    if name in _OFF:
        return None
    if name not in _AGENTS:
        _log.warning("image_agent unknown agent=%r task=%s -- using stub", name, task)
        name = "stub"
    with _cache_lock:
        if name not in _cache:
            _cache[name] = _AGENTS[name]()
        return _cache[name]
