"""Booking dates: the extraction prompt carries a calendar of the coming
days, and a booking date before today or too far ahead is re-asked.

Found by the evals suite (evals/, layer 1, {date+2} check): "day after
tomorrow" came back wrong in Kannada (ನಾಡಿದ್ದು -> today or no date) and
Telugu (ఎల్లుండి -> tomorrow); the old check only looked at the time.
"""
from datetime import date, datetime, timedelta, timezone

import services.appointment_supervisor.service as service
from services.llm_service import bedrock_adapter


def _today_ist():
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date()


# ---- calendar in the extraction prompt -----------------------------------

def test_calendar_lists_the_coming_days_with_weekdays():
    cal = bedrock_adapter._date_calendar(date(2026, 10, 17))
    assert "2026-10-17 Saturday (today)" in cal
    assert "2026-10-18 Sunday (tomorrow)" in cal
    assert "2026-10-19 Monday (day after tomorrow)" in cal
    assert "2026-10-26 Monday" in cal  # next week's Monday too
    assert len(cal.split("; ")) == bedrock_adapter._CALENDAR_DAYS


def test_calendar_crosses_month_and_year_end():
    cal = bedrock_adapter._date_calendar(date(2026, 12, 30))
    assert "2026-12-31 Thursday (tomorrow)" in cal
    assert "2027-01-01 Friday (day after tomorrow)" in cal


def test_calendar_kill_switch(monkeypatch):
    monkeypatch.setenv("EXTRACTION_DATE_CALENDAR", "0")
    assert bedrock_adapter._date_calendar(date(2026, 10, 17)) == ""
    assert "Calendar" not in bedrock_adapter.build_prompt("ನಾಡಿದ್ದು ಮಧ್ಯಾಹ್ನ 2 ಗಂಟೆಗೆ")


def test_prompt_carries_todays_calendar():
    # The real prompt builder, with the real clock (IST).
    prompt = bedrock_adapter.build_prompt("ನಾಡಿದ್ದು ಮಧ್ಯಾಹ್ನ 2 ಗಂಟೆಗೆ")
    today = _today_ist()
    assert f"Today: {today.isoformat()} Tomorrow: {(today + timedelta(days=1)).isoformat()}" in prompt
    assert f"{(today + timedelta(days=2)).isoformat()}" in prompt
    assert "(day after tomorrow)" in prompt


# ---- booking date backstop -----------------------------------------------

def test_booking_date_must_be_today_or_later_and_not_too_far(monkeypatch):
    monkeypatch.setattr(service, "_today_ist", lambda: date(2026, 10, 17))
    ok = ("today", "tomorrow", "2026-10-17", "2026-10-19", "2027-10-17")
    bad = ("yesterday", "2026-10-16", "2025-10-19", "2027-10-18", "11", "2026-02-30", None)
    for value in ok:
        assert service._valid_appointment_date(value) is True, value
    for value in bad:
        assert service._valid_appointment_date(value) is False, value


def _booking_turn(tmp_path, monkeypatch, date_value):
    monkeypatch.setattr(service, "_today_ist", lambda: date(2026, 10, 17))
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [])
    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"date": date_value}},
    )
    supervisor = service.AppointmentSupervisor(tmp_path)
    return supervisor.turn("demo-farmer", f"session-date-{date_value}", "date", "en-IN")


def test_past_booking_date_is_reasked_not_stored(tmp_path, monkeypatch):
    result = _booking_turn(tmp_path, monkeypatch, "2026-10-10")
    assert result["draft"].get("date") is None
    assert "date" in result["missing_fields"]


def test_future_booking_date_is_stored(tmp_path, monkeypatch):
    result = _booking_turn(tmp_path, monkeypatch, "2026-10-19")
    assert result["draft"].get("date") == "2026-10-19"
    