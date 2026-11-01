"""Backstop for a "tomorrow" the extraction left out (evals layer 4: Telugu
'CHINNI కి జ్వరం, రేపు డాక్టర్ కావాలి' sometimes came back with no date)."""
from datetime import date

from services.llm_service.bedrock_adapter import _fill_missing_tomorrow

MONDAY = date(2026, 10, 19)


def _date(text, entities):
    return _fill_missing_tomorrow(text, entities, today=MONDAY).get("date")


def test_missing_date_is_filled_when_the_farmer_said_tomorrow_in_any_language():
    for text in ("CHINNI కి జ్వరం, రేపు డాక్టర్ కావాలి", "vet tomorrow please", "उद्या सकाळी डॉक्टर हवा",
                 "நாளை டாக்டர் வேண்டும்", "ನಾಳೆ ವೈದ್ಯರು ಬೇಕು", "നാളെ ഡോക്ടർ വേണം", "రేపటి కోసం బుక్ చేయండి"):
        assert _date(text, {"issue": "fever"}) == "2026-10-20", text
    assert _date("vet tomorrow", {"date": None}) == "2026-10-20"
    assert _date("vet tomorrow", {"date": ""}) == "2026-10-20"


def test_left_alone_otherwise():
    assert _date("vet tomorrow", {"date": "2026-10-25"}) == "2026-10-25"      # a date was given
    assert _date("कल सुबह डॉक्टर", {}) is None                                # कल is not listed
    assert _date("day after tomorrow at 10", {}) is None                       # the other check decides
    assert _date("நாளை மறுநாள் காலை", {}) is None
    assert _date("tomorrow, I mean Thursday", {}) is None                      # weekday named
    assert _date("GAURI has fever", {}) is None


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("EXTRACTION_TOMORROW_CHECK", "0")
    assert _date("vet tomorrow", {}) is None


def test_a_word_sharing_a_prefix_but_differing_by_more_than_one_character_is_not_matched():
    """Boundary test for the fix ported from PR #73 (same fix already made
    once for the near-identical day-after-tomorrow check): the original
    tolerance (up to 3 extra characters past the phrase) would have
    accepted an unrelated word differing by 2-3 characters that happens to
    share the same prefix. Narrowed to 1 here too, same as
    _says_day_after_tomorrow -- "tomorrowxy" (2 extra characters) must not
    match, though it would have under the old tolerance."""
    assert _date("tomorrowxy at 10", {}) is None
