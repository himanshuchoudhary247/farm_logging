"""Changing the animal in the middle of a conversation.

The session cache keeps the animal resolved in an earlier turn, including
its animal_id. A later turn that names a different animal ("not that one,
the other one") must replace it; repeating the same animal, a small
spelling slip of it, or a turn that names no animal must not.

Only the model call, the animal store and the session store are faked; the
orchestrator and appointment_supervisor code is the real one. Entities use
the shapes the real extraction returns.
"""
import datetime
from types import SimpleNamespace

from services.appointment_supervisor import service
from services.voice_agent import orchestrator


def _animal(id_, name, age):
    return SimpleNamespace(id=id_, tag_or_name=name, species="goat", breed="Sirohi",
                           age_years=age, feeding_details="green fodder", farmer_id="f-001")


GAURI = _animal("a-f-001-99", "GAURI", 2.5)
MOTI = _animal("a-f-001-98", "MOTI", 1.2)


def _fake_world(monkeypatch, replies):
    """replies: what the extraction model returns, one per call."""
    sessions = {}
    monkeypatch.setattr(orchestrator, "get_session", lambda key: dict(sessions.get(key) or {}))
    monkeypatch.setattr(orchestrator, "update_session", lambda key, value: sessions.setdefault(key, {}).update(value))
    monkeypatch.setattr(service, "clear_session", lambda key: sessions.pop(key, None))
    monkeypatch.setattr(orchestrator, "load_animals", lambda: [GAURI, MOTI])
    queue = list(replies)
    monkeypatch.setattr(orchestrator, "call_bedrock", lambda text, context=None: queue.pop(0))


_BOOKING = {"intent": "CREATE_APPOINTMENT", "entities": {
    "animal_name": "GAURI", "issue": "fever", "symptoms": ["fever"], "date": "2026-08-22", "time": "10:00"}}


def _two_turns(monkeypatch, second_entities, first=_BOOKING):
    _fake_world(monkeypatch, [first, {"confirmation_signal": "no", "entities": second_entities}])
    one = orchestrator.process_text_input("first turn", session_id="s")
    two = orchestrator.process_text_input("second turn", session_id="s", pending_questions_override=["confirm"])
    return one["entities"], two["entities"]


# ---- orchestrator ---------------------------------------------------------

def test_another_stored_animal_replaces_the_cached_one(monkeypatch):
    first, second = _two_turns(monkeypatch, {"animal_name": "MOTI"})
    assert first["animal_id"] == "a-f-001-99"
    assert second["animal_name"] == "MOTI"
    assert second["animal_id"] == "a-f-001-98"
    assert second["age_years"] == 1.2, "the new animal's own record, not the old one's"
    assert second["date"] == "2026-08-22" and second["time"] == "10:00", "booking details stay"


def test_same_animal_in_other_case_keeps_the_record(monkeypatch):
    _, second = _two_turns(monkeypatch, {"animal_name": "gauri"})
    assert second["animal_id"] == "a-f-001-99"
    assert second["animal_name"] == "GAURI"


def test_small_spelling_slip_of_the_same_animal_keeps_the_record(monkeypatch):
    _, second = _two_turns(monkeypatch, {"animal_name": "Gaurii"})
    assert second["animal_id"] == "a-f-001-99"


def test_unknown_name_drops_the_old_record_so_the_caller_can_verify(monkeypatch):
    """A name that matches no stored animal must not be silently turned
    back into the old animal."""
    _, second = _two_turns(monkeypatch, {"animal_name": "BADAL"})
    assert second["animal_name"] == "BADAL"
    assert "animal_id" not in second
    assert second["date"] == "2026-08-22"


def test_turn_naming_no_animal_keeps_the_record(monkeypatch):
    _, second = _two_turns(monkeypatch, {"date": "2026-08-23"})
    assert second["animal_id"] == "a-f-001-99"
    assert second["date"] == "2026-08-23"


def test_renaming_a_new_animal_keeps_what_the_farmer_said(monkeypatch):
    """Registering a NEW animal: species/breed/age in the cache are the
    farmer's own words (no stored record), so a new name must keep them."""
    new_goat = {"intent": "CREATE_ANIMAL", "entities": {
        "animal_name": "RAJU", "species": "goat", "breed": "Osmanabadi", "age_years": 2, "animal_record_mode": "new"}}
    _, second = _two_turns(monkeypatch, {"animal_name": "RAJA"}, first=new_goat)
    assert second["animal_name"] == "RAJA"
    assert second["breed"] == "Osmanabadi"
    assert second["age_years"] == 2


# ---- whole booking: orchestrator + appointment_supervisor -----------------

def test_booking_readback_correction_switches_the_animal(tmp_path, monkeypatch):
    _fake_world(monkeypatch, [_BOOKING, {"confirmation_signal": "no", "entities": {"animal_name": "MOTI"}}])
    monkeypatch.setattr(service, "_today_ist", lambda: datetime.date(2026, 8, 20))
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [GAURI, MOTI])
    probe_calls = []

    def probe(query, farmer_id):
        # The off-topic probe would find the named animal in the database
        # and answer with its details instead of continuing the booking.
        probe_calls.append(query)
        return {"answer": "MOTI is a Sirohi goat", "sql": "SELECT 1", "data": [{"name": "MOTI"}]}

    monkeypatch.setattr(service, "process_query", probe)
    supervisor = service.AppointmentSupervisor(tmp_path)

    first = supervisor.turn("f-001", "booking-1", "GAURI has fever, day after tomorrow 10 am", "en-IN")
    assert first["state"] == "CONFIRMING" and first["missing_fields"] == []
    second = supervisor.turn("f-001", "booking-1", "no wait, not GAURI, it's MOTI", "en-IN")

    assert probe_calls == []
    assert second["state"] == "CONFIRMING"
    assert second["draft"]["animal_identifier"] == "MOTI"
    assert second["draft"]["animal_id"] == "a-f-001-98"
    assert "2026-08-22" in second["response_text"] and "10:00" in second["response_text"]

