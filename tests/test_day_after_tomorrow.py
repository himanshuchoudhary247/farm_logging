"""Backstop for "day after tomorrow" read as tomorrow (evals layer 3: Telugu
'MOTI తినడం లేదు, ఎల్లుండి ...' gave tomorrow 5 of 5 times)."""
from datetime import date

from services.llm_service.bedrock_adapter import _check_day_after_tomorrow

MONDAY = date(2026, 10, 19)


def _date(text, value, monkeypatch=None):
    return _check_day_after_tomorrow(text, {"date": value}, today=MONDAY)["date"]


def test_day_after_tomorrow_read_as_tomorrow_is_fixed_in_every_language():
    for text in ("MOTI తినడం లేదు, ఎల్లుండి ఉదయం 11 గంటలకు డాక్టర్ బుక్ చేయండి",
                 "day after tomorrow at 11 am", "परसों सुबह 11 बजे", "परवा सकाळी 11 वाजता",
                 "நாளை மறுநாள் காலை 11 மணிக்கு", "ನಾಡಿದ್ದು ರಂದು ಬೆಳಿಗ್ಗೆ", "മറ്റന്നാൾ രാവിലെ"):
        assert _date(text, "2026-10-20") == "2026-10-21", text
    assert _date("परसों सुबह 11 बजे", "tomorrow") == "2026-10-21"


def test_other_dates_and_words_are_left_alone():
    assert _date("ఎల్లుండి ఉదయం", "2026-10-21") == "2026-10-21"   # already right
    assert _date("परसों", "2026-10-25") == "2026-10-25"            # not tomorrow
    assert _date("कल सुबह 10 बजे", "2026-10-20") == "2026-10-20"   # कल is not listed
    assert _check_day_after_tomorrow("परसों", {}, today=MONDAY) == {}


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("EXTRACTION_DAY_AFTER_TOMORROW_CHECK", "0")
    assert _date("परसों सुबह", "2026-10-20") == "2026-10-20"
    