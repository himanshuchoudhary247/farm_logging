"""The router model gets its routing options from two places: the
_ROUTE_INSTRUCTION prompt, and the record_route tool's docstring (Google ADK
turns the docstring into the tool description the model sees). Both must list
every intent in _VALID_INTENTS. add_animal was added to the instruction and to
_VALID_INTENTS but not to the docstring, so the model saw 4 options in one
place and 3 in the other. These tests catch that drift if another intent is
added later."""
from __future__ import annotations

from services.chat_orchestrator.adk_router import (
    _ROUTE_INSTRUCTION,
    _VALID_INTENTS,
    _make_record_route_tool,
)


def test_record_route_docstring_lists_every_valid_intent():
    doc = _make_record_route_tool({}).__doc__ or ""
    missing = [intent for intent in _VALID_INTENTS if f'"{intent}"' not in doc]
    assert not missing, f"record_route docstring is missing intents: {missing}"


def test_route_instruction_lists_every_valid_intent():
    missing = [intent for intent in _VALID_INTENTS if f'"{intent}"' not in _ROUTE_INSTRUCTION]
    assert not missing, f"_ROUTE_INSTRUCTION is missing intents: {missing}"