"""Offline tests for the evals package (no server, no LLM)."""
import json
from pathlib import Path

import pytest

from evals.judge import check_turn, normalize_digits, script_share, turn_passed
from evals.run import fill, load_conversations, validate_conversations

REPO = Path(__file__).resolve().parents[1]


def test_conversation_files_are_valid():
    convs = load_conversations()
    assert convs, "no conversations found"
    assert validate_conversations(convs) == []


def test_indian_digits_are_normalized():
    assert normalize_digits("२२ बकरियाँ") == "22 बकरियाँ"
    assert normalize_digits("௨௨ ౧౪ ೫೩ ൭") == "22 14 53 7"


def test_number_check_accepts_native_digits():
    checks = check_turn({"agent": "query_agent", "number": 14}, agent="query_agent",
                        reply="आपके पास कुल १४ बकरियाँ हैं।", ms=900, language="hi-IN")
    assert turn_passed(checks), checks


def test_number_check_does_not_match_inside_bigger_number():
    checks = check_turn({"number": 14}, agent=None, reply="You have 140 goats.", ms=1, language="en-IN")
    assert not turn_passed(checks)


def test_wrong_agent_fails():
    checks = check_turn({"agent": "appointment_supervisor"}, agent="query_agent",
                        reply="Here is your report", ms=1, language="en-IN")
    assert not turn_passed(checks)


def test_reply_in_wrong_language_fails_script_check():
    checks = check_turn({}, agent=None, reply="You have 14 goats on your farm.", ms=1, language="hi-IN")
    assert not turn_passed(checks)
    assert script_share("आपके पास GAURI है", "hi-IN") > 0.4


def test_request_error_fails():
    checks = check_turn({"agent": "query_agent"}, agent=None, reply="", ms=1, language="en-IN",
                        error="HTTP 500: boom")
    assert not turn_passed(checks)


def test_fill_replaces_tag_everywhere():
    conv = {"turns": [{"user": "EVAL-{tag}-X", "expect": {"reply_contains_any": ["EVAL-{tag}-X"]}}]}
    out = fill(conv, "123")
    assert out["turns"][0]["user"] == "EVAL-123-X"
    assert out["turns"][0]["expect"]["reply_contains_any"] == ["EVAL-123-X"]


def _f001_species_counts():
    path = REPO / "data" / "animals.json"
    if not path.exists():
        pytest.skip("data/animals.json not found")
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else next((v for v in raw.values() if isinstance(v, list)), [])
    counts = {}
    for r in rows:
        if not isinstance(r, dict) or "f-001" not in {str(v) for v in r.values()}:
            continue
        sp = str(r.get("species", "")).strip().lower()
        counts[sp] = counts.get(sp, 0) + 1
    if not counts:
        pytest.skip("could not read f-001 animals from data/animals.json")
    return counts


def test_layer1_numbers_match_the_data():
    """If data/animals.json changes, the expected numbers in layer 1 must change too."""
    counts = _f001_species_counts()
    want = {"goat": 14, "sheep": 7, "buffalo": 16, "cow": 9, "chicken": 7}
    assert {k: counts.get(k, 0) for k in want} == want
    assert sum(counts.values()) == 53
