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
    """Seen live: a plain "no" at the date question dropped the animal
    ("wrong animal?") and asked for it again. Now it asks to cancel, keeps
    the animal, and needs no model call for the "no" or the answer."""
    _start_booking(booking, language)
    calls = len(booking.calls)
    ask = booking.turn(FARMER, SESSION, "no", language)
    assert ask["response_text"] == cancel_check.ask_text("booking", language)
    assert ask["prompt_text"] == ask["response_text"]
    assert ask["options"] == cancel_check.chips(language)
    assert ask["draft"]["animal_identifier"] == "Lakshmi", "the animal is kept"
    done = booking.turn(FARMER, SESSION, cancel_check.chips(language)["choices"][0], language)
    assert done["state"] == "CANCELLED"
    assert len(booking.calls) == calls, "no model call for the 'no' or the chip"


def test_booking_carry_on_shows_the_same_question_and_a_second_no_cancels(booking):
    first = _start_booking(booking)
    pending = booking.turn(FARMER, SESSION, "nahi", "en-IN")
    assert pending["response_text"] == cancel_check.ask_text("booking", "en-IN")

    calls = len(booking.calls)
    again = booking.turn(FARMER, SESSION, "No, continue", "en-IN")
    assert again["state"] == first["state"]
    assert again["response_text"] == first["response_text"], "the same question, shown again"
    assert len(booking.calls) == calls, "carrying on needs no model call"

    done = booking.turn(FARMER, SESSION, "no", "en-IN")
    assert done["state"] == "CANCELLED", "never the same question twice in a row"


def test_booking_carry_on_counts_only_for_the_next_reply(booking):
    _start_booking(booking)
    booking.turn(FARMER, SESSION, "no", "en-IN")  # asks
    booking.turn(FARMER, SESSION, "continue", "en-IN")
    booking.replies.append({"entities": {}})
    booking.turn(FARMER, SESSION, "umm let me see", "en-IN")  # something else, nothing changed
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
    booking.turn(FARMER, SESSION, "no", "en-IN")  # asks
    calls = len(booking.calls)
    booking.replies.append({"entities": {"date": "2026-08-25"}})
    r = booking.turn(FARMER, SESSION, "25 august", "en-IN")
    assert len(booking.calls) == calls + 1, "a normal answer is read by the flow as usual"
    assert r["state"] != "CANCELLED" and r["draft"].get("date") == "2026-08-25"
    assert "cancel_check" not in booking._load(SESSION, FARMER, "en-IN")


def test_booking_wrong_animal_words_still_reach_the_flow(booking):
    _start_booking(booking)
    booking.replies.append({"entities": {}, "confirmation_signal": "no"})
    r = booking.turn(FARMER, SESSION, "wrong tag", "en-IN")
    assert r["response_text"] != cancel_check.ask_text("booking", "en-IN")
    assert r["draft"].get("animal_identifier") is None, "'wrong tag' still asks for the animal again"


@pytest.mark.parametrize("language", LANGS)
def test_booking_no_at_the_readback_asks_cancel_or_continue(booking, language):
    """Tapping the app's "No" at "Is this correct?": cancel, or carry on and
    say what to correct -- the farmer chooses. No model call either way."""
    booking.replies.append({"entities": {"animal_identifier": "Lakshmi", "issue": "fever",
                                         "date": "2026-08-25", "time": "11:30"}})
    first = booking.turn(FARMER, SESSION, "Lakshmi fever 25 august 11:30", language)
    assert first["state"] == "CONFIRMING"
    calls = len(booking.calls)
    ask = booking.turn(FARMER, SESSION, "no", language)
    assert ask["response_text"] == cancel_check.ask_text("booking", language)
    assert ask["options"] == cancel_check.chips(language)
    assert ask["state"] == "CORRECTING", "the app's own Yes/No buttons are not drawn over the question"
    back = booking.turn(FARMER, SESSION, cancel_check.chips(language)["choices"][1], language)
    assert back["state"] == "CORRECTING"
    assert back["response_text"] == appt_service._TEXT[language.split("-")[0]]["no"]
    assert len(booking.calls) == calls, "no model call for the 'no' or the choice"


def test_booking_yes_after_no_at_the_readback_cancels(booking):
    booking.replies.append({"entities": {"animal_identifier": "Lakshmi", "issue": "fever",
                                         "date": "2026-08-25", "time": "11:30"}})
    booking.turn(FARMER, SESSION, "Lakshmi fever 25 august 11:30", "en-IN")
    booking.turn(FARMER, SESSION, "No", "en-IN")
    assert booking.turn(FARMER, SESSION, "Yes, cancel", "en-IN")["state"] == "CANCELLED"


def test_booking_no_with_a_change_at_the_readback_still_corrects_in_place(booking):
    booking.replies.append({"entities": {"animal_identifier": "Lakshmi", "issue": "fever",
                                         "date": "2026-08-25", "time": "11:30"}})
    booking.turn(FARMER, SESSION, "Lakshmi fever 25 august 11:30", "en-IN")
    booking.replies.append({"entities": {"date": "2026-08-26"}, "confirmation_signal": "no"})
    r = booking.turn(FARMER, SESSION, "no, make it 26 august", "en-IN")
    assert r["draft"]["date"] == "2026-08-26"
    assert r["response_text"] != cancel_check.ask_text("booking", "en-IN")


def _to_correcting(booking, language="en-IN"):
    booking.replies.append({"entities": {"animal_identifier": "Lakshmi", "issue": "fever",
                                         "date": "2026-08-25", "time": "11:30"}})
    assert booking.turn(FARMER, SESSION, "Lakshmi fever 25 august 11:30", language)["state"] == "CONFIRMING"
    # "What would you like to correct?" reached straight from the readback
    # (the /appointments/confirm route; in chat the "cancel?" question comes first).
    assert booking.confirm(FARMER, SESSION, "no", include_audio=False)["state"] == "CORRECTING"


def test_booking_no_continue_then_no_at_what_to_correct_cancels(booking):
    """The chat path: No -> "cancel?" -> No, continue -> "What would you like
    to correct?" -> no again: the farmer said no twice, so it is cancelled."""
    booking.replies.append({"entities": {"animal_identifier": "Lakshmi", "issue": "fever",
                                         "date": "2026-08-25", "time": "11:30"}})
    booking.turn(FARMER, SESSION, "Lakshmi fever 25 august 11:30", "en-IN")
    booking.turn(FARMER, SESSION, "No", "en-IN")
    assert booking.turn(FARMER, SESSION, "No, continue", "en-IN")["state"] == "CORRECTING"
    assert booking.turn(FARMER, SESSION, "no", "en-IN")["state"] == "CANCELLED"


@pytest.mark.parametrize("signal", [None, "no"])
def test_booking_no_at_what_to_correct_asks_instead_of_looping(booking, signal):
    """Seen live: "No" at the readback -> "What would you like to correct?"
    -> "no" -> the same readback again (or, when the model read "no", the
    animal dropped) -> "No" -> ... for ever. Now the second "no" asks."""
    _to_correcting(booking)
    calls = len(booking.calls)
    booking.replies.append({"entities": {}, "confirmation_signal": signal})
    ask = booking.turn(FARMER, SESSION, "no", "en-IN")
    assert ask["response_text"] == cancel_check.ask_text("booking", "en-IN")
    assert ask["options"] == cancel_check.chips("en-IN")
    assert ask["state"] == "CORRECTING", "no Yes/No confirm buttons of the app over the question"
    assert ask[cancel_check.CANCEL_QUESTION_KEY] is True
    assert len(booking.calls) == calls, "decided without a model call"
    saved = booking._load(SESSION, FARMER, "en-IN")
    assert saved["draft"]["animal_identifier"] == "Lakshmi", "the animal is kept"

    back = booking.turn(FARMER, SESSION, "No, continue", "en-IN")
    assert back["state"] == "CORRECTING"
    assert back["response_text"] == appt_service._TEXT["en"]["no"]

    done = booking.turn(FARMER, SESSION, "no", "en-IN")
    assert done["state"] == "CANCELLED"


def test_booking_dont_want_at_what_to_correct_cancels(booking):
    _to_correcting(booking, "hi-IN")
    assert booking.turn(FARMER, SESSION, "नहीं चाहिए", "hi-IN")["state"] == "CANCELLED"


def test_booking_a_real_correction_at_what_to_correct_still_works(booking):
    _to_correcting(booking)
    booking.replies.append({"entities": {"date": "2026-08-26"}})
    r = booking.turn(FARMER, SESSION, "make it 26 august", "en-IN")
    assert r["draft"]["date"] == "2026-08-26" and r["state"] == "CONFIRMING"


def test_the_cancel_question_gets_no_form_and_what_to_correct_gets_a_filled_form(booking, monkeypatch):
    from services.a2ui import booking_widget, widgets
    monkeypatch.setattr(booking_widget, "widgets_enabled", lambda: True)
    monkeypatch.setattr(booking_widget, "_symptom_options", lambda language: {"choices": ["Fever"]}, raising=False)
    _to_correcting(booking)
    correcting = booking._response(booking._load(SESSION, FARMER, "en-IN"), "What would you like to correct?",
                                   include_audio=False)
    form = widgets.widget_for("appointment_supervisor", FARMER, SESSION, correcting, "en-IN")
    assert form, "the filled form comes with 'What would you like to correct?'"
    assert "2026-08-25" in str(form) and "11:30" in str(form)

    booking.replies.append({"entities": {}})
    ask = booking.turn(FARMER, SESSION, "no", "en-IN")
    assert widgets.widget_for("appointment_supervisor", FARMER, SESSION, ask, "en-IN") is None


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


def test_animal_no_at_what_to_correct_asks(animal):
    animal.replies.extend([{"species": "goat"}, {"unique_animal_id": "REG-78"}, {"breed": "Jamunapari", "sex": "male"},
                           {"confirmation_signal": "no"}])
    animal.turn(FARMER, SESSION, "register a goat", include_audio=False)
    animal.turn(FARMER, SESSION, "REG-78", include_audio=False)
    animal.turn(FARMER, SESSION, "Jamunapari male", include_audio=False)
    assert animal.turn(FARMER, SESSION, "no", include_audio=False)["state"] == "CONFIRMING"  # skip optional
    assert animal.confirm(FARMER, SESSION, "no", include_audio=False)["state"] == "CORRECTING"
    calls = len(animal.calls)
    ask = animal.turn(FARMER, SESSION, "இல்லை", "ta-IN", include_audio=False)
    assert ask["response_text"] == cancel_check.ask_text("animal", "ta-IN") and len(animal.calls) == calls
    assert animal.turn(FARMER, SESSION, "ஆம்", "ta-IN", include_audio=False)["state"] == "CANCELLED"


def test_animal_no_at_the_summary_asks_cancel_or_continue(animal):
    animal.replies.extend([{"species": "goat"}, {"unique_animal_id": "REG-79"}, {"breed": "Jamunapari", "sex": "male"},
                           {"confirmation_signal": "no"}])
    animal.turn(FARMER, SESSION, "register a goat", "te-IN", include_audio=False)
    animal.turn(FARMER, SESSION, "REG-79", "te-IN", include_audio=False)
    animal.turn(FARMER, SESSION, "Jamunapari male", "te-IN", include_audio=False)
    assert animal.turn(FARMER, SESSION, "no", "te-IN", include_audio=False)["state"] == "CONFIRMING"  # skip optional
    calls = len(animal.calls)
    ask = animal.turn(FARMER, SESSION, "లేదు", "te-IN", include_audio=False)
    assert ask["response_text"] == cancel_check.ask_text("animal", "te-IN") and ask["options"]
    back = animal.turn(FARMER, SESSION, cancel_check.chips("te-IN")["choices"][1], "te-IN", include_audio=False)
    assert back["state"] == "CORRECTING" and len(animal.calls) == calls


@pytest.mark.parametrize("word,language", [("no", "en-IN"), ("नहीं", "hi-IN"), ("ഇല്ല", "ml-IN"), ("வேண்டாம்", "ta-IN")])
def test_animal_no_at_the_optional_details_skips_even_when_the_model_reads_nothing(animal, word, language):
    """Seen live: "say 'no' to submit now" -> "no" -> the model gave no skip
    signal -> "Do you want to stop adding this animal?". Now a plain "no"
    (or "don't want") there is the skip, without a model call."""
    animal.replies.extend([{"species": "goat"}, {"unique_animal_id": "REG-80"}, {"breed": "Jamunapari", "sex": "male"}])
    animal.turn(FARMER, SESSION, "register a goat", language, include_audio=False)
    animal.turn(FARMER, SESSION, "REG-80", language, include_audio=False)
    assert animal.turn(FARMER, SESSION, "Jamunapari male", language, include_audio=False)["state"] == "COLLECTING_OPTIONAL"
    calls = len(animal.calls)
    r = animal.turn(FARMER, SESSION, word, language, include_audio=False)
    assert r["state"] == "CONFIRMING" and len(animal.calls) == calls
    assert r["response_text"] != cancel_check.ask_text("animal", language)


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


def _to_what_to_change(order, language="en-IN"):
    order.replies.append({"product_query": "calcium"})
    order.turn(FARMER, SESSION, "calcium", language=language, include_audio=False)
    order.turn(FARMER, SESSION, "Calcium Gel", language=language,
               include_audio=False)
    order.replies.append({"quantity": 2})
    quote = order.turn(FARMER, SESSION, "2", language=language, include_audio=False)
    assert quote["state"] == "CONFIRMING", quote["response_text"]
    order.turn(FARMER, SESSION, "no", language=language, include_audio=False)  # cancel?
    back = order.turn(FARMER, SESSION, cancel_check.chips(language)["choices"][1], language=language, include_audio=False)
    assert back["state"] == "CORRECTING"


@pytest.mark.parametrize("word,language", [("quantity", "en-IN"), ("मात्रा", "hi-IN"), ("எண்ணிக்கை", "ta-IN")])
def test_order_naming_the_quantity_asks_how_many(order, word, language):
    """Seen live: "What would you like to change?" -> "quantity" -> the same
    question again. Now it asks how many."""
    _to_what_to_change(order, language)
    r = order.turn(FARMER, SESSION, word, language=language, include_audio=False)
    assert r["state"] == "QUANTITY" and r["options"], "how many, with the quantity pills"


def test_order_naming_the_address_asks_for_it(order):
    _to_what_to_change(order, "hi-IN")
    r = order.turn(FARMER, SESSION, "पता", language="hi-IN", include_audio=False)
    assert r["state"] == "ADDRESS"
    assert r["response_text"] == order._message("hi-IN", "ask_address")


def test_order_naming_the_product_shows_the_store(order):
    _to_what_to_change(order)
    r = order.turn(FARMER, SESSION, "product", include_audio=False)
    assert r["state"] == "CHOOSING" and len(r["draft"]["options"]) == 2


def test_order_a_real_change_at_what_to_change_still_works(order):
    _to_what_to_change(order)
    order.replies.append({"quantity": 4})
    r = order.turn(FARMER, SESSION, "make it 4", include_audio=False)
    assert r["state"] == "CONFIRMING" and r["draft"]["quantity"] == 4


# ------------------------------------------------------------------ review fixes

def test_order_naming_the_product_respects_the_store_list_kill_switch(order, monkeypatch):
    """CHAT_ORDER_BROWSE_ENABLED=false: like every other place, no store
    list -- the farmer is asked which product instead."""
    _to_what_to_change(order)
    monkeypatch.setenv("CHAT_ORDER_BROWSE_ENABLED", "false")
    searched = []
    monkeypatch.setattr(order_service.flokiq_sync, "search_products",
                        lambda *a, **k: searched.append(a) or {"storeAssigned": True, "products": [CALCIUM]})
    r = order.turn(FARMER, SESSION, "product", include_audio=False)
    assert r["state"] == "SEARCHING"
    assert r["response_text"] == order._message("en-IN", "welcome")
    assert searched == [], "no store list while it is switched off"
    saved = order._load(SESSION, FARMER, "en-IN")["draft"]
    assert not saved.get("product") and not saved.get("quantity") and not saved.get("quote")


@pytest.mark.parametrize("language", LANGS)
def test_order_an_unknown_reply_at_what_to_change_says_it_was_not_understood(order, language, caplog):
    _to_what_to_change(order, language)
    with caplog.at_level("INFO"):
        r = order.turn(FARMER, SESSION, "quantty", language=language, include_audio=False)
    assert r["state"] == "CORRECTING"
    assert r["response_text"] == order._message(language, "change_not_understood")
    assert r["response_text"] != order._message(language, "what_to_change")
    assert "order correction not understood" in caplog.text


def _ask_cancel_in_booking(booking):
    _start_booking(booking)
    asked = booking.turn(FARMER, SESSION, "no", include_audio=False)
    assert asked["response_text"] == cancel_check.ask_text("booking", "en-IN")
    return asked


def test_a_failed_cancel_keeps_the_question_open(booking, monkeypatch):
    """The farmer taps "Yes, cancel" and the cancel itself fails: the error
    goes up as before, and the open question is kept, so the next "yes"
    is read as the answer again (not as a booking answer)."""
    _ask_cancel_in_booking(booking)
    real = type(booking)._cancel_now

    def broken(self, *a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(type(booking), "_cancel_now", broken)
    with pytest.raises(RuntimeError):
        booking.turn(FARMER, SESSION, "yes", include_audio=False)
    assert booking._load(SESSION, FARMER, "en-IN")["cancel_check"].get("asked")

    monkeypatch.setattr(type(booking), "_cancel_now", real)
    done = booking.turn(FARMER, SESSION, "yes", include_audio=False)
    assert done["state"] == "CANCELLED"


def test_the_question_is_not_saved_when_its_reply_fails(booking, monkeypatch):
    """Nothing is saved as "asked" for a question the farmer never saw."""
    _start_booking(booking)

    def broken(self, *a, **k):
        raise RuntimeError("tts down")
    monkeypatch.setattr(type(booking), "_cancel_reply", broken)
    with pytest.raises(RuntimeError):
        booking.turn(FARMER, SESSION, "no", include_audio=False)
    assert not (booking._load(SESSION, FARMER, "en-IN").get("cancel_check") or {}).get("asked")


def test_any_other_reply_to_the_question_is_logged(booking, caplog):
    _ask_cancel_in_booking(booking)
    with caplog.at_level("INFO"):
        booking.turn(FARMER, SESSION, "tomorrow", include_audio=False)
    assert "cancel_check answer=other" in caplog.text

