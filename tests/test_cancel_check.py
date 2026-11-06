"""A plain "no" never traps a farmer in a booking, an animal registration or
an order (services/common/cancel_check.py). Each flow runs for real; only
the LLM extraction, TTS and main_backend are mocked at their boundaries,
the same way the flows' own test files do it."""
from __future__ import annotations

import datetime as _dt

import pytest

from services.animal_registration import service as animal_service
from services.animal_registration.service import AnimalRegistrationSupervisor
from services.appointment_supervisor import service as appt_service
from services.common import cancel_check
from services.order_supervisor import service as order_service
from services.order_supervisor.service import OrderSupervisor

FARMER = "24cdd479-7ce8-4951-91cb-e295f8a2b0ff"  # the app sends real UUIDs
SESSION = "24666232-6a23-4471-9fef-0c89e366ddbe"
LANGS = ("en-IN", "hi-IN", "mr-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN")


# ------------------------------------------------------------------ words

def test_every_language_has_its_question_and_chips():
    for kind in ("booking", "animal", "order"):
        for lang in LANGS:
            assert cancel_check.ask_text(kind, lang).strip()
    for lang in LANGS:
        yes, no = cancel_check.chips(lang)["choices"]
        assert cancel_check.answer(yes) == "cancel"
        assert cancel_check.answer(no) == "continue"


def test_the_word_lists_never_overlap():
    assert not (cancel_check._STOP & cancel_check._BARE_NO)
    assert not (cancel_check._ANSWER_CANCEL & cancel_check._ANSWER_CONTINUE)


@pytest.mark.parametrize("text", ["no", "No.", "NAHI", "नहीं", "नाही", "இல்லை", "లేదు", "ಇಲ್ಲ", "ഇല്ല", " nahi! "])
def test_bare_no_in_every_language(text):
    assert cancel_check.is_bare_no(text) and not cancel_check.is_stop(text)


@pytest.mark.parametrize("text", ["nahi chahiye", "I don't want", "rehne do", "नहीं चाहिए", "मला नको",
                                  "வேண்டாம்", "వద్దు", "ಬೇಡ", "വേണ്ട"])
def test_clear_dont_want_in_every_language(text):
    assert cancel_check.is_stop(text)


@pytest.mark.parametrize("text", ["no fever", "nahi, kal subah", "not on monday", "नहीं, बुखार है", "ताप आहे, औषध नको"])
def test_a_no_inside_a_longer_answer_is_left_to_the_flow(text):
    assert not cancel_check.is_bare_no(text) and not cancel_check.is_stop(text)
    assert cancel_check.answer(text) is None


# ------------------------------------------------------------------ booking

@pytest.fixture
def booking(tmp_path, monkeypatch):
    monkeypatch.setattr(appt_service, "_try_mid_draft_escape", lambda text, farmer_id, session_id, language: None)
    monkeypatch.setattr(appt_service, "_today_ist", lambda: _dt.date(2026, 8, 20))
    monkeypatch.setattr(appt_service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(appt_service, "animals_for_farmer",
                        lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "Lakshmi"})()])
    calls = []
    replies = []

    def extract(text, session_id, pending_questions_override=None):
        calls.append(text)
        return replies.pop(0) if replies else {"entities": {}}

    monkeypatch.setattr(appt_service, "process_text_input", extract)
    sup = appt_service.AppointmentSupervisor(tmp_path)
    sup.calls, sup.replies = calls, replies
    return sup


def _start_booking(sup, language="en-IN"):
    """Animal and problem given; the flow now asks for the date."""
    sup.replies.append({"entities": {"animal_identifier": "Lakshmi", "issue": "fever"}})
    first = sup.turn(FARMER, SESSION, "Lakshmi has fever", language)
    assert first["state"] in {"COLLECTING", "CONFIRMING"} and first["missing_fields"]
    return first


@pytest.mark.parametrize("language", LANGS)
def test_booking_bare_no_asks_once_then_yes_cancels_without_a_model_call(booking, language):
    _start_booking(booking, language)
    # Already-verified animal + a bare "no": the flow's own "wrong animal?"
    # step runs first (it changes the draft), exactly as before.
    booking.replies.append({"entities": {}, "confirmation_signal": "no"})
    wrong_animal = booking.turn(FARMER, SESSION, "no", language)
    assert wrong_animal["response_text"] != cancel_check.ask_text("booking", language)

    booking.replies.append({"entities": {}, "confirmation_signal": "no"})
    ask = booking.turn(FARMER, SESSION, "no", language)
    assert ask["response_text"] == cancel_check.ask_text("booking", language)
    assert ask["prompt_text"] == ask["response_text"]
    assert ask["options"] == cancel_check.chips(language)
    assert ask["state"] == wrong_animal["state"], "asking does not move the booking"

    calls = len(booking.calls)
    done = booking.turn(FARMER, SESSION, cancel_check.chips(language)["choices"][0], language)
    assert done["state"] == "CANCELLED"
    assert len(booking.calls) == calls, "the chip answer needs no model call"


def test_booking_carry_on_shows_the_same_question_and_a_second_no_cancels(booking):
    _start_booking(booking)
    booking.replies.append({"entities": {}, "confirmation_signal": "no"})
    asks_animal = booking.turn(FARMER, SESSION, "no", "en-IN")  # wrong animal -> asks the animal
    booking.replies.append({"entities": {}})
    pending = booking.turn(FARMER, SESSION, "nahi", "en-IN")
    assert pending["response_text"] == cancel_check.ask_text("booking", "en-IN")

    calls = len(booking.calls)
    again = booking.turn(FARMER, SESSION, "No, continue", "en-IN")
    assert again["state"] == asks_animal["state"]
    assert again["response_text"] == asks_animal["response_text"], "the same question, shown again"
    assert len(booking.calls) == calls, "carrying on needs no model call"

    booking.replies.append({"entities": {}})
    done = booking.turn(FARMER, SESSION, "no", "en-IN")
    assert done["state"] == "CANCELLED", "never the same question twice in a row"


def test_booking_carry_on_counts_only_for_the_next_reply(booking):
    _start_booking(booking)
    booking.replies.append({"entities": {}, "confirmation_signal": "no"})
    booking.turn(FARMER, SESSION, "no", "en-IN")
    booking.replies.append({"entities": {}})
    booking.turn(FARMER, SESSION, "no", "en-IN")  # asks
    booking.turn(FARMER, SESSION, "continue", "en-IN")
    booking.replies.append({"entities": {}})
    booking.turn(FARMER, SESSION, "umm let me see", "en-IN")  # something else, nothing changed
    booking.replies.append({"entities": {}})
    asked = booking.turn(FARMER, SESSION, "no", "en-IN")
    assert asked["response_text"] == cancel_check.ask_text("booking", "en-IN")


@pytest.mark.parametrize("text,language", [("nahi chahiye", "hi-IN"), ("I don't want", "en-IN"),
                                           ("मला नको", "mr-IN"), ("வேண்டாம்", "ta-IN"), ("వద్దు", "te-IN"),
                                           ("ಬೇಡ", "kn-IN"), ("വേണ്ട", "ml-IN")])
def test_booking_clear_dont_want_cancels_at_once(booking, text, language):
    _start_booking(booking, language)
    booking.replies.append({"entities": {}})
    done = booking.turn(FARMER, SESSION, text, language)
    assert done["state"] == "CANCELLED"


def test_booking_other_reply_to_the_question_goes_through_the_flow(booking):
    _start_booking(booking)
    booking.replies.append({"entities": {}, "confirmation_signal": "no"})
    booking.turn(FARMER, SESSION, "no", "en-IN")
    booking.replies.append({"entities": {}})
    booking.turn(FARMER, SESSION, "no", "en-IN")  # asks
    calls = len(booking.calls)
    booking.replies.append({"entities": {"animal_identifier": "Lakshmi"}})
    r = booking.turn(FARMER, SESSION, "Lakshmi", "en-IN")
    assert len(booking.calls) == calls + 1, "a normal answer is read by the flow as usual"
    assert r["state"] != "CANCELLED" and r["draft"].get("animal_identifier") == "Lakshmi"
    assert "cancel_check" not in booking._load(SESSION, FARMER, "en-IN")


def test_booking_no_at_the_readback_still_asks_what_to_correct(booking):
    booking.replies.append({"entities": {"animal_identifier": "Lakshmi", "issue": "fever",
                                         "date": "2026-08-25", "time": "11:30"}})
    first = booking.turn(FARMER, SESSION, "Lakshmi fever 25 august 11:30", "en-IN")
    assert first["state"] == "CONFIRMING"
    booking.replies.append({"entities": {}, "confirmation_signal": "no"})
    r = booking.turn(FARMER, SESSION, "no", "en-IN")
    assert r["state"] == "CORRECTING"
    assert r["response_text"] == appt_service._TEXT["en"]["no"]


# ------------------------------------------------------------------ animal registration

@pytest.fixture
def animal(tmp_path, monkeypatch):
    monkeypatch.setattr(animal_service, "_try_mid_draft_escape", lambda text, farmer_id, session_id, language: None)
    monkeypatch.setattr(animal_service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(animal_service, "animals_for_farmer", lambda farmer_id: [])
    sup = AnimalRegistrationSupervisor(tmp_path)
    sup.replies = []
    sup.calls = []

    def extract(draft, text):
        sup.calls.append(text)
        return sup.replies.pop(0) if sup.replies else {}

    sup._extract = extract
    return sup


@pytest.mark.parametrize("language", ["en-IN", "hi-IN", "ta-IN"])
def test_animal_bare_no_at_a_required_field_asks_and_chips_come_along(animal, language):
    animal.replies.append({"species": "goat"})
    first = animal.turn(FARMER, SESSION, "register a goat", language, include_audio=False)
    assert first["state"] == "COLLECTING"
    ask = animal.turn(FARMER, SESSION, "no", language, include_audio=False)
    assert ask["response_text"] == cancel_check.ask_text("animal", language)
    assert ask["options"] == cancel_check.chips(language)
    done = animal.turn(FARMER, SESSION, cancel_check.chips(language)["choices"][0], language, include_audio=False)
    assert done["state"] == "CANCELLED"


def test_animal_no_at_the_optional_details_still_skips(animal):
    animal.replies.extend([{"species": "goat"}, {"unique_animal_id": "REG-77"}, {"breed": "Jamunapari", "sex": "male"},
                           {"confirmation_signal": "no"}])
    animal.turn(FARMER, SESSION, "register a goat", include_audio=False)
    animal.turn(FARMER, SESSION, "REG-77", include_audio=False)
    optional = animal.turn(FARMER, SESSION, "Jamunapari male", include_audio=False)
    assert optional["state"] == "COLLECTING_OPTIONAL"
    r = animal.turn(FARMER, SESSION, "no", include_audio=False)
    assert r["state"] == "CONFIRMING", "the optional step's 'no' means skip, as before"


# ------------------------------------------------------------------ order

CALCIUM = {"productId": "230bd59c-91d6-48f6-8d5a-bcdaa1c6b5c4", "name": "Calcium Gel", "packType": "1 L",
           "image": None, "prescriptionRequired": False, "unitPrice": 120, "mrp": 140, "available": 15}
CALCIUM_PLUS = {**CALCIUM, "productId": "11111111-2222-3333-4444-555555555555", "name": "Calcium Plus",
                "packType": "500 ml", "unitPrice": 95, "available": 4}


@pytest.fixture
def order(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAT_ORDERS_ENABLED", "true")
    monkeypatch.setattr(order_service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(order_service.flokiq_sync, "orders_available", lambda farmer_id: True)
    monkeypatch.setattr(order_service.flokiq_sync, "search_products",
                        lambda *a, **k: {"storeAssigned": True, "products": [CALCIUM, CALCIUM_PLUS]})
    monkeypatch.setattr(order_service.flokiq_sync, "quote_order",
                        lambda *a, **k: {"status": 200, "body": {"totalAmount": 240, "currency": "INR",
                                                                  "deliveryAddress": "Pune", "items": []}})
    monkeypatch.setattr(order_service.flokiq_sync, "create_order", lambda *a, **k: pytest.fail("must not order"))
    sup = OrderSupervisor(tmp_path)
    sup.replies = []
    sup._extract = lambda draft, text: dict(sup.replies.pop(0)) if sup.replies else {}
    return sup


def test_order_bare_no_while_choosing_asks_and_the_chips_are_not_drawn_as_products(order):
    order.replies.append({"product_query": "calcium"})
    first = order.turn(FARMER, SESSION, "calcium", include_audio=False)
    assert first["state"] == "CHOOSING" and len(first["draft"]["options"]) == 2
    order.replies.append({"confirmation_signal": "no"})
    ask = order.turn(FARMER, SESSION, "no", include_audio=False)
    assert ask["response_text"] == cancel_check.ask_text("order", "en-IN")
    assert ask["options"] == cancel_check.chips("en-IN")
    assert ask["draft"]["options"] == [], "two chips beside two products would pair up as product cards"
    assert len(order._load(SESSION, FARMER, "en-IN")["draft"]["options"]) == 2, "the saved draft keeps the products"

    back = order.turn(FARMER, SESSION, "No, continue", include_audio=False)
    assert back["state"] == "CHOOSING"
    assert back["options"]["choices"] == first["options"]["choices"]
    assert len(back["draft"]["options"]) == 2, "carrying on shows the product cards again"


def test_order_clear_dont_want_cancels(order):
    order.replies.append({"product_query": "calcium"})
    order.turn(FARMER, SESSION, "calcium", include_audio=False)
    order.replies.append({})
    done = order.turn(FARMER, SESSION, "nahi chahiye", include_audio=False)
    assert done["state"] == "CANCELLED"
