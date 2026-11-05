"""One photo turn: check the upload, pick the agent, return the reply in the
same shape /chat/turn returns, so the app shows it like any other reply.

Kept free of FastAPI so it can be tested on its own; the route only reads the
upload and turns an ImageTurnError into an HTTP error.

This module never writes the photo to disk -- but Starlette's own multipart
parser may spool an upload over ~1 MB to a transient OS temp file while
parsing the request, independent of anything here; that file is
auto-deleted once the request completes.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from services.common.draft_supervisor import SUPPORTED_LANGUAGES
from services.image_agent.base import ImageRequest
from services.image_agent.registry import get_agent, normalize_task

# A child of the "api" logger, so these lines print in the same terminal as
# the other route logs (main.py gives "api" its handler and INFO level).
_log = logging.getLogger("api.image_agent")


def _safe(value: str) -> str:
    """value with newlines stripped, for %s-interpolation into a log line --
    farmer_id/session_id come from the request and are never validated
    against a charset, so logging them raw would let a crafted value forge
    extra log lines."""
    return (value or "").replace("\r", "").replace("\n", "")

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 1000

# The first bytes of each accepted format. The declared content type alone is
# not trusted: a renamed or broken file is refused before any agent sees it.
_SIGNATURES = {
    "image/jpeg": lambda b: b[:3] == b"\xff\xd8\xff",
    "image/png": lambda b: b[:8] == b"\x89PNG\r\n\x1a\n",
    "image/webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
}


class ImageTurnError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def handle_image_turn(farmer_id: str, session_id: str, language: str, text: str, task: str,
                      content_type: str, image: bytes) -> dict[str, Any]:
    """Raises ImageTurnError with the HTTP status the route should answer:
    400 bad input, 413 photo too large, 415 not a supported photo,
    503 photo turns switched off, 502 the agent failed."""
    if not (session_id or "").strip():
        raise ImageTurnError(400, "session_id is required")
    if language not in SUPPORTED_LANGUAGES:
        raise ImageTurnError(400, f"Unsupported language: {language}")
    kind = (content_type or "").split(";", 1)[0].strip().lower()
    if kind == "image/jpg":
        kind = "image/jpeg"
    if kind not in _SIGNATURES:
        raise ImageTurnError(415, "Upload a JPG, PNG or WEBP photo")
    if not image:
        raise ImageTurnError(400, "The photo is empty")
    if len(image) > MAX_IMAGE_BYTES:
        raise ImageTurnError(413, "Photo is larger than 5 MB")
    if not _SIGNATURES[kind](image):
        raise ImageTurnError(415, "The file is not a valid JPG, PNG or WEBP photo")

    task_name = normalize_task(task)
    agent = get_agent(task_name)
    if agent is None:
        _log.info("chat_image_turn off farmer=%s task=%s", _safe(farmer_id), task_name)
        raise ImageTurnError(503, "Photo questions are not available right now")

    request = ImageRequest(
        farmer_id=farmer_id,
        session_id=session_id,
        language=language,
        task=task_name,
        text=(text or "").strip()[:MAX_TEXT_CHARS],
        image=image,
        content_type=kind,
    )
    t0 = time.time()
    try:
        result = agent.analyze(request)
    except Exception:
        _log.exception(
            "chat_image_turn failed farmer=%s session=%s agent=%s task=%s",
            _safe(farmer_id), _safe(session_id), agent.name, task_name,
        )
        raise ImageTurnError(502, "Could not read the photo. Please try again.")
    total_ms = round((time.time() - t0) * 1000)
    _log.info(
        "chat_image_turn farmer=%s session=%s agent=%s task=%s bytes=%d ms=%d",
        _safe(farmer_id), _safe(session_id), agent.name, task_name, len(image), total_ms,
    )
    return {
        "agent": "image_agent",
        "intent": task_name,
        "result": {
            "task": task_name,
            "image_agent": agent.name,
            "data": dict(result.data or {}),
            "response_text": result.reply_text,
        },
        "reply_text": result.reply_text,
        "timing": {"total_ms": total_ms},
    }
