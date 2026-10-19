"""Offline tests for the evals package (no server, no LLM)."""
import json
from pathlib import Path

import pytest

from evals.compare import aggregate, compare, verdict
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


def test_fill_replaces_date_placeholders():
    from datetime import date
    out = fill({"t": ["on {date+2}", "{date}", "{date-1}", "EVAL-{tag}"]}, "7", today=date(2026, 10, 17))
    assert out["t"] == ["on 2026-10-19", "2026-10-17", "2026-10-16", "EVAL-7"]


def test_fill_date_crosses_month_end():
    from datetime import date
    assert fill("{date+2}", "x", today=date(2026, 10, 31)) == "2026-11-02"


def test_validate_flags_unknown_placeholders():
    bad = [{"id": "X", "language": "en-IN", "turns": [{"user": "hi {dat+2}", "expect": {}}]}]
    assert validate_conversations(bad) == ["X: unknown placeholder {dat+2}"]


def test_weekday_placeholders():
    from datetime import date
    saturday = date(2026, 10, 17)
    out = fill(["{next-mon}", "{next-mon+7}", "{this-thu}", "{next-sat}", "{this-sat}"], "x", today=saturday)
    assert out == ["2026-10-19", "2026-10-26", "2026-10-22", "2026-10-24", "2026-10-17"]


def test_day_of_month_placeholder():
    from datetime import date
    assert fill("{dom-25}", "x", today=date(2026, 10, 18)) == "2026-10-25"
    assert fill("{dom-25}", "x", today=date(2026, 10, 25)) == "2026-10-25"
    assert fill("{dom-25}", "x", today=date(2026, 10, 26)) == "2026-11-25"
    assert fill("{dom-25}", "x", today=date(2026, 12, 30)) == "2027-01-25"
    assert fill("{dom-28}", "x", today=date(2026, 1, 31)) == "2026-02-28"
    good = [{"id": "G", "language": "en-IN", "turns": [{"user": "{dom-1} {dom-28}", "expect": {}}]}]
    bad = [{"id": "B", "language": "en-IN", "turns": [{"user": "{dom-29} {dom-0}", "expect": {}}]}]
    assert validate_conversations(good) == []
    assert validate_conversations(bad) == ["B: unknown placeholder {dom-0}", "B: unknown placeholder {dom-29}"]
    

def test_past_time_is_always_earlier_today():
    from datetime import datetime
    assert fill("{past-time}", "x", now=datetime(2026, 10, 17, 13, 30)) == "11:00"
    assert fill("{past-time}", "x", now=datetime(2026, 10, 17, 1, 10)) == "00:00"
    assert fill("{past-time}", "x", now=datetime(2026, 10, 17, 0, 5)) == "00:00"


def test_validate_accepts_the_new_placeholders_only():
    good = [{"id": "G", "language": "en-IN", "turns": [{"user": "{next-mon} {this-fri+7} {past-time}", "expect": {}}]}]
    bad = [{"id": "B", "language": "en-IN", "turns": [{"user": "{next-monday} {past-hour}", "expect": {}}]}]
    assert validate_conversations(good) == []
    assert validate_conversations(bad) == ["B: unknown placeholder {next-monday}", "B: unknown placeholder {past-hour}"]


def test_layer2_has_the_same_12_cases_in_every_language():
    convs = [c for c in load_conversations() if c["layer"] == 2]
    langs = sorted({c["language"] for c in convs})
    assert langs == ["en-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "ta-IN", "te-IN"]
    titles = {lang: [c["title"] for c in convs if c["language"] == lang] for lang in langs}
    assert all(len(t) == 12 for t in titles.values())
    assert len({tuple(t) for t in titles.values()}) == 1, "every language must test the same 12 cases"
    # Bookings never get the final "yes": nothing in layer 2 may save data.
    assert not any(c.get("data_checks") for c in convs)
    # "day after tomorrow" in each language must come back as today + 2.
    convs = {c["id"]: c for c in load_conversations()}
    for lang in ("en", "hi", "mr", "ta", "te", "kn", "ml"):
        expect = convs[f"L1-{lang}-009"]["turns"][2]["expect"]
        assert expect.get("reply_contains_all") == ["{date+2}"], lang


def _f001_rows():
    path = REPO / "data" / "animals.json"
    if not path.exists():
        pytest.skip("data/animals.json not found")
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else next((v for v in raw.values() if isinstance(v, list)), [])
    rows = [r for r in rows if isinstance(r, dict) and "f-001" in {str(v) for v in r.values()}]
    if not rows:
        pytest.skip("could not read f-001 animals from data/animals.json")
    return rows


def _f001_species_counts():
    counts = {}
    for r in _f001_rows():
        sp = str(r.get("species", "")).strip().lower()
        counts[sp] = counts.get(sp, 0) + 1
    return counts


def test_layer1_numbers_match_the_data():
    """If data/animals.json changes, the expected numbers in layer 1 must change too."""
    counts = _f001_species_counts()
    want = {"goat": 14, "sheep": 7, "buffalo": 16, "cow": 9, "chicken": 7}
    assert {k: counts.get(k, 0) for k in want} == want
    assert sum(counts.values()) == 53


def test_layer1_breeds_and_names_match_the_data():
    rows = _f001_rows()
    breeds = {}
    for r in rows:
        key = (str(r.get("species", "")).lower(), str(r.get("breed", "")).strip())
        breeds[key] = breeds.get(key, 0) + 1
    want = {("goat", "Sirohi"): 5, ("goat", "Osmanabadi"): 3, ("buffalo", "Mehsana"): 5,
            ("buffalo", "Nili-Ravi"): 5, ("cow", "Kankrej"): 3, ("sheep", "Nali"): 3, ("chicken", "Aseel"): 3}
    assert {k: breeds.get(k, 0) for k in want} == want
    names = {str(r.get("tag_or_name")): (str(r.get("species")).lower(), str(r.get("breed")).strip()) for r in rows}
    assert names["GAURI"] == ("goat", "Sirohi")
    assert names["MOTI"] == ("goat", "Sirohi")
    assert names["KAALI"] == ("goat", "Jamunapari")
    assert names["LAKSHMI"] == ("buffalo", "Murrah")
    assert names["CHINNI"] == ("buffalo", "Jaffarabadi")
    assert names["BIJLI"] == ("buffalo", "Nili-Ravi")
    assert names["RAJA"] == ("cow", "Kankrej")


# ---------------------------------------------------------------- compare.py


def _run(results):
    return {"results": results}


def _res(cid, passed, ms=1000, agent="query_agent"):
    return {"id": cid, "passed": passed, "layer": 1, "language": "en-IN", "title": cid,
            "turns": [{"ms": ms, "error": None, "expect": {"agent": agent}, "agent": agent}]}


def test_verdicts():
    assert verdict({"rate": 1.0}, {"rate": 0.0}) == "REGRESSION"
    assert verdict({"rate": 0.0}, {"rate": 1.0}) == "FIXED"
    assert verdict({"rate": 0.67}, {"rate": 0.33}) == "FLAKY"
    assert verdict({"rate": 1.0}, {"rate": 1.0}) == "SAME"
    assert verdict({"rate": 0.0}, {"rate": 0.0}) == "SAME"
    assert verdict(None, {"rate": 1.0}) == "NEW"


def test_aggregate_counts_pass_rate_across_runs():
    runs = [_run([_res("A", True), _res("B", False)]), _run([_res("A", True), _res("B", True)])]
    agg = aggregate(runs)
    assert agg["conversations"]["A"]["rate"] == 1.0
    assert agg["conversations"]["B"]["passes"] == 1 and agg["conversations"]["B"]["runs"] == 2


def test_compare_flags_regression_and_slower_agent():
    base = aggregate([_run([_res("A", True, ms=1000)])] * 3)
    now = aggregate([_run([_res("A", False, ms=5000)])])
    out = compare(base, now)
    assert out["rows"][0]["verdict"] == "REGRESSION"
    assert out["slower"] and out["slower"][0]["agent"] == "query_agent"


def test_script_check_ignores_names_and_expected_breed():
    checks = check_turn({"reply_contains_any": ["Murrah", "मुर्रा"]}, agent=None,
                        reply="LAKSHMI की नस्ल Murrah है।", ms=1, language="hi-IN",
                        user_text="LAKSHMI की नस्ल क्या है?")
    assert turn_passed(checks), checks


def test_script_check_still_catches_english_reply():
    checks = check_turn({}, agent=None, reply="You have 7 sheep on your farm.", ms=1,
                        language="hi-IN", user_text="मेरे पास कितनी भेड़ें हैं?")
    assert not turn_passed(checks)


def test_has_number():
    ok = check_turn({"has_number": True}, agent=None, reply="आज 9.3mm बारिश हो सकती है", ms=1, language="hi-IN")
    bad = check_turn({"has_number": True}, agent=None, reply="आज मौसम अच्छा है", ms=1, language="hi-IN")
    assert turn_passed(ok) and not turn_passed(bad)
