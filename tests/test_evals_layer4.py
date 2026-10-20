"""Offline checks of the layer 4 conversation file (no server, no LLM)."""
import json
import re
from pathlib import Path

from evals.run import fill, load_conversations, validate_conversations

LANGS = ["en-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "ta-IN", "te-IN"]
ANIMALS = Path(__file__).resolve().parents[1] / "data" / "animals.json"


def _layer4():
    return [c for c in load_conversations() if c["layer"] == 4]


def test_layer4_has_the_same_30_cases_in_every_language():
    convs = _layer4()
    assert sorted({c["language"] for c in convs}) == LANGS
    titles = {lang: [c["title"] for c in convs if c["language"] == lang] for lang in LANGS}
    assert all(len(t) == 30 for t in titles.values())
    assert len({tuple(t) for t in titles.values()}) == 1, "every language must test the same 30 cases"
    assert len(convs) == 210


def test_layer4_ids_are_001_to_030_per_language():
    for lang in LANGS:
        short = lang.split("-")[0]
        ids = [c["id"] for c in _layer4() if c["language"] == lang]
        assert ids == [f"L4-{short}-{n:03d}" for n in range(1, 31)]


def test_layer4_same_turn_count_and_agents_in_every_language():
    # The 7 languages must expect the same agents, numbers and dates turn by turn.
    convs = _layer4()
    shape = {}
    for c in convs:
        n = int(c["id"].rsplit("-", 1)[1])
        sig = [(t["expect"].get("agent"), t["expect"].get("number"), t["expect"].get("script", True))
               for t in c["turns"]]
        shape.setdefault(n, set()).add(json.dumps(sig))
    assert all(len(s) == 1 for s in shape.values()), shape


def test_layer4_placeholders_are_valid_and_all_filled():
    assert validate_conversations(_layer4()) == []
    for c in _layer4():
        left = re.findall(r"\{[^{}\s\"]+\}", json.dumps(fill(c, "t1"), ensure_ascii=False))
        assert left == [], (c["id"], left)


def test_layer4_saves_nothing():
    # Bookings and registrations never get the final "yes".
    assert not any(c.get("data_checks") for c in _layer4())


def test_layer4_switch_cases_check_the_new_agent():
    # Themes 1 and 2 are the flow switches: the turn that switches must name the new agent,
    # and the next turn must still be answered by it (the old flow must not take it back).
    for c in _layer4():
        n = int(c["id"].rsplit("-", 1)[1])
        agents = [t["expect"].get("agent") for t in c["turns"]]
        if n == 1:
            assert agents == ["appointment_supervisor", "animal_registration", "animal_registration"], c["id"]
        if n == 2:
            assert agents == ["animal_registration", "appointment_supervisor", "appointment_supervisor"], c["id"]


def test_layer4_booking_turns_keep_the_date_visible():
    # A twist must never silently change the booking: after a twist the reply (or the later
    # "what about my booking?") shows the date again. Cases 5, 7 and 12 check this on every turn.
    for c in _layer4():
        n = int(c["id"].rsplit("-", 1)[1])
        if n in (5, 12):
            for t in c["turns"][1:]:
                if t["expect"].get("agent") == "appointment_supervisor":
                    assert any("{date" in s for s in t["expect"].get("reply_contains_all", [])) \
                        or t["expect"].get("number") or t["expect"].get("reply_contains_any"), (c["id"], t)


def test_layer4_off_topic_case_rejects_the_real_answer():
    for c in _layer4():
        if c["id"].endswith("-005"):
            forbidden = c["turns"][1]["expect"]["reply_not_contains"]
            assert "Paris" in forbidden and len(forbidden) >= 7


def test_layer4_never_registered_animal_is_not_in_the_farm_data():
    # Case 14 asks about an animal that must NOT exist. If someone adds it to the data, the case is wrong.
    assert "BHOORI" not in ANIMALS.read_text(encoding="utf-8")


def test_layer4_language_switch_case_skips_script_only_on_the_english_turn():
    for c in _layer4():
        if c["id"].endswith("-010"):
            flags = [t["expect"].get("script", True) for t in c["turns"]]
            assert flags == [True, False, True], c["id"]


def test_layer4_most_turns_check_something_beyond_the_agent():
    # Bare "agent" turns are only for replies with no fixed content ("hmm", "?", hello).
    turns = [t for c in _layer4() for t in c["turns"]]
    with_content = [t for t in turns if set(t["expect"]) - {"agent"}]
    assert len(with_content) / len(turns) > 0.6


def test_layer4_cases_16_to_30_check_the_open_flow_survives():
    # Every later twist ends with a turn that proves the flow (or the clean state) is still right.
    for c in _layer4():
        n = int(c["id"].rsplit("-", 1)[1])
        last = c["turns"][-1]["expect"]
        if n in (17, 22, 23, 24, 25):
            assert last["agent"] == "appointment_supervisor" and "10:00" in last["reply_contains_all"], c["id"]
        if n == 30:
            assert last["agent"] == "query_agent" and last["number"] == 7, c["id"]
        if n == 16:
            assert [t["expect"].get("agent") for t in c["turns"]] == \
                ["weather_alert", "animal_registration", "animal_registration"], c["id"]
