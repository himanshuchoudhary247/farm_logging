"""Offline checks of the layer 3 conversation file (no server, no LLM)."""
from evals.run import load_conversations

LANGS = ["en-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "ta-IN", "te-IN"]


def _layer3():
    return [c for c in load_conversations() if c["layer"] == 3]


def test_layer3_has_the_same_20_cases_in_every_language():
    convs = _layer3()
    assert sorted({c["language"] for c in convs}) == LANGS
    titles = {lang: [c["title"] for c in convs if c["language"] == lang] for lang in LANGS}
    assert all(len(t) == 20 for t in titles.values())
    assert len({tuple(t) for t in titles.values()}) == 1, "every language must test the same 20 cases"


def test_layer3_saves_nothing():
    # Bookings and registrations never get the final "yes".
    assert not any(c.get("data_checks") for c in _layer3())


def test_layer3_side_questions_check_the_booking_is_kept():
    # A question asked mid-booking must be answered AND the reply must still
    # show the booking's date, so a date changed by the question is caught.
    for c in _layer3():
        agents = [t["expect"].get("agent") for t in c["turns"]]
        for i, turn in enumerate(c["turns"][1:], 1):
            e = turn["expect"]
            if agents[i] == "appointment_supervisor" and agents[i - 1] == "appointment_supervisor" \
                    and (e.get("number") or e.get("has_number") or e.get("reply_contains_any")) \
                    and "{date" in str(c["turns"][0]["expect"]):
                assert any("{date" in s for s in e.get("reply_contains_all", [])), (c["id"], i)


def test_every_layer3_turn_checks_something_beyond_the_agent():
    # Plain "agent" checks are allowed only for turns whose reply has no fixed content
    # (a booking prompt, a cancel, "continue"); count how many carry real checks.
    turns = [t for c in _layer3() for t in c["turns"]]
    with_content = [t for t in turns if set(t["expect"]) - {"agent"}]
    assert len(with_content) / len(turns) > 0.75
    