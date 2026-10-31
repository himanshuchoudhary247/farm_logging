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
    