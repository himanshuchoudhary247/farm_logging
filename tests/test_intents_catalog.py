"""Tests for the shared intent catalog and the classifier prompt it drives.

Also guards the byte-identical property between the catalog-rendered
_ROUTE_INSTRUCTION and the (now-deleted) hand-written literal it
replaces -- without this test, a well-intended reword to the catalog
could silently change what the classifier sees and drift downstream
behavior.
"""
from __future__ import annotations

import pytest

from services.chat_orchestrator import adk_router
from services.chat_orchestrator.intents import (
    INTENTS,
    LANGUAGES,
    VALID_INTENTS,
    IntentSpec,
    build_route_instruction,
)


def test_catalog_covers_the_four_intents_the_router_dispatches():
    """The dispatch table in adk_router.py MUST match the catalog exactly
    -- an intent in one but not the other means the classifier can pick
    something the dispatcher can't handle, OR we've got a dead handler."""
    assert set(INTENTS.keys()) == set(adk_router._DISPATCH_TABLE.keys()), (
        "INTENTS catalog and adk_router._DISPATCH_TABLE must agree exactly"
    )


def test_valid_intents_stays_in_sync_with_catalog():
    assert VALID_INTENTS == tuple(INTENTS.keys())
    assert adk_router._VALID_INTENTS == VALID_INTENTS


def test_every_intent_has_a_label_in_every_language():
    """IntentSpec.__post_init__ enforces this at construction time, but
    verify the invariant holds after the whole catalog is loaded too --
    the check is cheap and catches a partial-language rollout."""
    for name, spec in INTENTS.items():
        assert set(spec.labels.keys()) >= set(LANGUAGES), (
            f"INTENTS[{name!r}].labels missing some languages: "
            f"{set(LANGUAGES) - set(spec.labels.keys())}"
        )
        for lang in LANGUAGES:
            assert spec.labels[lang].strip(), (
                f"INTENTS[{name!r}].labels[{lang!r}] is blank"
            )


def test_missing_language_label_fails_at_construction_time():
    """The IntentSpec dataclass rejects a partial-language entry -- a
    later WhatsApp reply in the missing language shouldn't be the way
    we discover the gap; the process should refuse to boot instead."""
    with pytest.raises(ValueError, match="missing labels"):
        IntentSpec(
            name="not_real",
            classifier_description="test",
            labels={"en": "hello only"},  # missing hi/ta/te/kn
        )


def test_route_instruction_matches_the_original_hand_written_string():
    """The refactor is meant to be BEHAVIORALLY IDENTICAL -- the catalog-
    rendered prompt must reproduce the pre-refactor string byte-for-byte,
    otherwise the classifier's decisions could subtly drift on the same
    inputs. Original string embedded verbatim below (last hand-written
    revision, git-checkable if this test fails)."""
    ORIGINAL = """Classify what area of a livestock farm-management app a farmer's message belongs to, then call record_route exactly once with your decision. Never answer the farmer directly yourself -- only classify.

Categories:
- "appointment": booking a vet appointment, reporting a sick/injured animal, requesting a farm visit or treatment, OR reporting/logging a health event for an animal ALREADY on the farm (a treatment given, a vaccination done, a symptom noticed, a checkup completed).
- "add_animal": registering a brand-new animal that isn't on the farm's records yet -- the farmer wants to ADD it as a new entry (a new goat/sheep they bought, were given, or that was born). This is about the animal's identity itself (ID, species, breed, sex), not a health event.
- "weather": weather, rain, temperature, heat/cold stress, whether to move animals indoors, or feed-price/market questions tied to weather/season.
- "query": LOOKING UP the farmer's own EXISTING animals or records -- counts, lists, history, "how many", "when was", past vaccination records, past health logs, past appointments, general greetings, or anything unclear. This category is READ-ONLY -- it can only look up data that's already saved, never record something new. If a message could be read as either reporting a new event or asking about past ones, and it describes something that just happened, prefer "appointment" or "add_animal" (whichever fits) -- a farmer telling you what happened wants it recorded, not silently discarded.

"appointment" vs "add_animal": both can write data, but about different things -- "my goat has a fever" or "book a vet visit" is "appointment" (an EXISTING animal's health). "I got a new goat, register it" or "add a new sheep to my farm" is "add_animal" (the animal's own identity record, brand new).

When genuinely ambiguous with no hint of a new event to record, prefer "query" -- it is the general-purpose fallback."""
    assert build_route_instruction() == ORIGINAL, (
        "catalog-rendered classifier prompt drifted from the pre-refactor "
        "hand-written string -- if this is intentional, update the ORIGINAL "
        "constant AND double-check the classifier still routes correctly "
        "against the existing eval fixtures (scripts/eval_*)"
    )


def test_labels_used_by_router_module_are_the_same_object():
    """A refactor consumer sanity check -- the module-level _ROUTE_INSTRUCTION
    in adk_router is what the classifier LlmAgent's instruction= reads,
    so it MUST be the value produced by build_route_instruction(). Guards
    against a future edit that accidentally re-hardcodes the string."""
    assert adk_router._ROUTE_INSTRUCTION == build_route_instruction()


def test_dispatch_table_handlers_all_callable():
    """Cheap defensive check: adding a new entry to _DISPATCH_TABLE with
    a typo'd handler name would only surface when that intent actually
    got classified live. This catches it at import time."""
    for intent, handler in adk_router._DISPATCH_TABLE.items():
        assert callable(handler), f"_DISPATCH_TABLE[{intent!r}] is not callable"
