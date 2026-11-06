"""Photo turns for Chocolate: a farmer sends a photo with an optional question.

base.py      the contract every photo agent follows (ImageRequest -> ImageResult)
stub.py      the placeholder agent used until real agents exist (no model call)
registry.py  which agent answers which task, chosen from .env
service.py   checks the upload and runs one turn for the route
"""
from services.image_agent.base import TASKS, ImageAgent, ImageRequest, ImageResult
from services.image_agent.service import MAX_IMAGE_BYTES, ImageTurnError, handle_image_turn

__all__ = [
    "TASKS", "ImageAgent", "ImageRequest", "ImageResult",
    "MAX_IMAGE_BYTES", "ImageTurnError", "handle_image_turn",
]
