"""Shared magic-byte sample images for the photo-turn tests
(test_image_agent.py, test_chat_image_turn_route.py). Plain module constants,
not a conftest fixture: test_image_agent.py uses these inside
@pytest.mark.parametrize, which needs the values at collection time, before
any fixture would be available.
"""
from __future__ import annotations

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 2000
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2000
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 2000
