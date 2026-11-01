"""Tests for the chat order agent. The LLM (OrderSupervisor._extract) and
main_backend (services.flokiq_sync.client order calls) are mocked at their
boundaries, same convention as test_animal_registration.py, so the suite is
deterministic and makes no network or Bedrock calls.

Mocked main_backend answers use the exact shapes main_backend's
/internal/orders routes return (see main_backend
src/controllers/internal/order.controller.js)."""
from __future__ import annotations

import pytest

from services.order_supervisor import service
from services.order_supervisor.service import OrderSupervisor

FARMER = "24cdd479-7ce8-4951-91cb-e295f8a2b0ff"
CALCIUM = {
    "productId": "230bd59c-91d6-48f6-8d5a-bcdaa1c6b5c4",
    "name": "Calcium Gel",
    "company": "Demo Co",
    "packType": "1 L",
    "unit": "unit",
    "image": None,
    "prescriptionRequired": False,
    "unitPrice": 120,
    "mrp": 140,
    "available": 15,
}
CALCIUM_PLUS = {**CALCIUM, "productId": "11111111-2222-3333-4444-555555555555", "name": "Calcium Plus",
                "packType": "500 ml", "unitPrice": 95, "available": 4}
ADDRESS = "Pune, Maharashtra, 411001"


def _quote(total=240, address=ADDRESS):
    return {"status": 200, "body": {"totalAmount": total, "currency": "INR", "deliveryAddress": address, "items": []}}


def _created(total=240, reused=False):
    return {"status": 201 if not reused else 200, "body": {
        "orderId": "55b00a1a-9622-4109-b1eb-21bb9858bfa9",
        "orderCode": "OD108504213339770880",
        "reused": reused,
        "totalAmount": total,
        "currency": "INR",
        "deliveryAddress": ADDRESS,
        "items": [],
        "payment": {"razorpayOrderId": "order_ABC123", "amount": total * 100, "currency": "INR"},
    }}


class Backend:
    """Records every call the agent makes to main_backend and answers from
    queues (one answer per call, last one repeats)."""

    def __init__(self, monkeypatch, search=None, quote=None, create=None, available=True):
        self.calls = {"search": [], "quote": [], "create": []}
        self._answers = {
            "search": list(search or [{"storeAssigned": True, "products": [CALCIUM]}]),
            "quote": list(quote or [_quote()]),
            "create": list(create or [_created()]),
        }
        monkeypatch.setattr(service.flokiq_sync, "orders_available", lambda farmer_id: available)
        monkeypatch.setattr(service.flokiq_sync, "search_products", self._call("search"))
        monkeypatch.setattr(service.flokiq_sync, "quote_order", self._call("quote"))
        monkeypatch.setattr(service.flokiq_sync, "create_order", self._call("create"))

    def _call(self, name):
        def call(*args, **kwargs):
            self.calls[name].append({"args": args, "kwargs": kwargs})
            answers = self._answers[name]
            return answers.pop(0) if len(answers) > 1 else answers[0]
        return call


@pytest.fixture
def sup(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAT_ORDERS_ENABLED", "true")
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    return OrderSupervisor(tmp_path)


def _say(sup, entities_by_turn):
    """The LLM's reading of each turn, in order (an empty dict = it found nothing)."""
    turns = iter(entities_by_turn)
    sup._extract = lambda draft, text: dict(next(turns, {}))


def test_full_order_one_product_then_pay_details(sup, monkeypatch):
    backend = Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel"}, {"quantity": 2}, {"confirmation_signal": "yes"}])

    r1 = sup.turn(FARMER, "s1", "I need calcium gel", include_audio=False)
    assert r1["state"] == "QUANTITY"
    assert "Calcium Gel" in r1["response_text"]
    assert "₹120" in r1["response_text"], "the price of one is shown before asking how many"
    assert r1["options"]["choices"] == ["1", "2", "3", "5", "10"]
    assert backend.calls["search"][0]["args"][:2] == (FARMER, "calcium gel")

    r2 = sup.turn(FARMER, "s1", "2", include_audio=False)
    assert r2["state"] == "CONFIRMING"
    assert "₹240" in r2["response_text"] and ADDRESS in r2["response_text"]
    assert r2["options"]["choices"] == ["Yes", "No"]
    assert backend.calls["quote"][0]["args"] == (FARMER, [{"productId": CALCIUM["productId"], "quantity": 2}], "")

    r3 = sup.turn(FARMER, "s1", "yes", include_audio=False)
    assert r3["state"] == "ORDERED"
    assert backend.calls["create"][0]["args"] == (FARMER, [{"productId": CALCIUM["productId"], "quantity": 2}], ADDRESS)
    assert r3["order"]["payment"] == {"razorpayOrderId": "order_ABC123", "amount": 24000, "currency": "INR"}
    assert r3["order"]["orderId"] == "55b00a1a-9622-4109-b1eb-21bb9858bfa9"
    assert "OD108504213339770880" in r3["response_text"]
    assert sup._load("s1", FARMER, "en-IN")["submitted"] is True


def test_product_and_quantity_in_one_message_go_straight_to_the_quote(sup, monkeypatch):
    backend = Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}])
    r = sup.turn(FARMER, "s1", "2 calcium gel chahiye", include_audio=False)
    assert r["state"] == "CONFIRMING"
    assert len(backend.calls["quote"]) == 1


def test_several_matches_are_offered_as_pills_and_a_tapped_pill_picks_one(sup, monkeypatch):
    backend = Backend(monkeypatch, search=[{"storeAssigned": True, "products": [CALCIUM, CALCIUM_PLUS]}])
    _say(sup, [{"product_query": "calcium"}, {}])  # the LLM reads nothing from the tapped pill
    r1 = sup.turn(FARMER, "s1", "calcium", include_audio=False)
    assert r1["state"] == "CHOOSING"
    assert r1["options"]["choices"] == ["Calcium Gel (1 L)", "Calcium Plus (500 ml)"]
    assert "₹120" in r1["response_text"] and "₹95" in r1["response_text"]

    r2 = sup.turn(FARMER, "s1", "Calcium Plus (500 ml)", include_audio=False)
    assert r2["state"] == "QUANTITY"
    # Calcium Plus has only 4 orderable, so the pills stop at what can be ordered.
    assert r2["options"]["choices"] == ["1", "2", "3"]
    assert len(backend.calls["search"]) == 1


def test_option_picked_by_number_through_the_llm(sup, monkeypatch):
    Backend(monkeypatch, search=[{"storeAssigned": True, "products": [CALCIUM, CALCIUM_PLUS]}])
    _say(sup, [{"product_query": "calcium"}, {"chosen_option": 2}])
    sup.turn(FARMER, "s1", "calcium", include_audio=False)
    r = sup.turn(FARMER, "s1", "the second one", include_audio=False)
    assert r["draft"]["product"]["productId"] == CALCIUM_PLUS["productId"]


def test_an_option_number_out_of_range_is_not_picked(sup, monkeypatch):
    Backend(monkeypatch, search=[{"storeAssigned": True, "products": [CALCIUM, CALCIUM_PLUS]}])
    _say(sup, [{"product_query": "calcium"}, {"chosen_option": 7}])
    sup.turn(FARMER, "s1", "calcium", include_audio=False)
    r = sup.turn(FARMER, "s1", "seven", include_audio=False)
    assert r["state"] == "CHOOSING"
    assert r["draft"]["product"] is None


def test_nothing_found_asks_for_another_name(sup, monkeypatch):
    Backend(monkeypatch, search=[{"storeAssigned": True, "products": []}])
    _say(sup, [{"product_query": "unicorn tonic"}])
    r = sup.turn(FARMER, "s1", "unicorn tonic", include_audio=False)
    assert r["state"] == "SEARCHING"
    assert "unicorn tonic" in r["response_text"]


def test_shop_unreachable_is_said_and_the_conversation_stays_open(sup, monkeypatch):
    Backend(monkeypatch, search=[None])
    _say(sup, [{"product_query": "calcium"}])
    r = sup.turn(FARMER, "s1", "calcium", include_audio=False)
    assert r["response_text"] == service._TEXT["en"]["shop_unreachable"]
    assert r["state"] == "SEARCHING"


def test_farmer_without_a_store_is_told_and_the_conversation_ends(sup, monkeypatch):
    Backend(monkeypatch, search=[{"storeAssigned": False, "products": []}])
    _say(sup, [{"product_query": "calcium"}])
    r = sup.turn(FARMER, "s1", "calcium", include_audio=False)
    assert r["state"] == "CANCELLED"
    assert r["response_text"] == service._TEXT["en"]["no_store"]


def test_more_than_can_be_ordered_asks_again_within_the_limit(sup, monkeypatch):
    backend = Backend(monkeypatch, search=[{"storeAssigned": True, "products": [CALCIUM_PLUS]}])
    _say(sup, [{"product_query": "calcium plus", "quantity": 6}])
    r = sup.turn(FARMER, "s1", "6 calcium plus", include_audio=False)
    assert r["state"] == "QUANTITY"
    assert "4" in r["response_text"]
    assert r["draft"]["quantity"] is None
    assert backend.calls["quote"] == []


def test_a_bare_number_answers_the_quantity_when_the_llm_reads_nothing(sup, monkeypatch):
    Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel"}, {}])
    sup.turn(FARMER, "s1", "calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", " 3 ", include_audio=False)
    assert r["draft"]["quantity"] == 3
    assert r["state"] == "CONFIRMING"


@pytest.mark.parametrize("bad", [0, -2, 1.5, "two", True])
def test_quantity_must_be_a_positive_whole_number(bad):
    assert OrderSupervisor._as_quantity(bad) is None


def test_yes_with_a_change_gets_a_new_quote_instead_of_ordering(sup, monkeypatch):
    backend = Backend(monkeypatch, quote=[_quote(240), _quote(360)])
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {"confirmation_signal": "yes", "quantity": 3}])
    sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "yes but make it 3", include_audio=False)
    assert r["state"] == "CONFIRMING"
    assert "₹360" in r["response_text"]
    assert backend.calls["create"] == []


def test_the_llm_repeating_the_product_at_confirm_does_not_undo_yes(sup, monkeypatch):
    backend = Backend(monkeypatch)
    _say(sup, [
        {"product_query": "calcium gel", "quantity": 2},
        # A reworded echo: not a substring of the name, so it searches again
        # and finds the same product.
        {"confirmation_signal": "yes", "product_query": "calcium gel 1 litre"},
    ])
    sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "yes", include_audio=False)
    assert r["state"] == "ORDERED"
    assert len(backend.calls["create"]) == 1


def test_no_at_confirm_asks_what_to_change_then_a_new_quantity_requotes(sup, monkeypatch):
    backend = Backend(monkeypatch, quote=[_quote(240), _quote(480)])
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {"confirmation_signal": "no"}, {"quantity": 4}])
    sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    r2 = sup.turn(FARMER, "s1", "no", include_audio=False)
    assert r2["state"] == "CORRECTING"
    r3 = sup.turn(FARMER, "s1", "4", include_audio=False)
    assert r3["state"] == "CONFIRMING" and "₹480" in r3["response_text"]
    assert backend.calls["create"] == []


def test_cancel_at_any_step_ends_and_the_next_message_starts_fresh(sup, monkeypatch):
    backend = Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {"confirmation_signal": "cancel"}, {}])
    sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    r2 = sup.turn(FARMER, "s1", "rehne do", include_audio=False)
    assert r2["state"] == "CANCELLED"
    assert backend.calls["create"] == []
    r3 = sup.turn(FARMER, "s1", "hello", include_audio=False)
    assert r3["state"] == "SEARCHING"
    assert r3["draft"]["product"] is None


def test_kill_switch_off_says_unavailable_and_calls_nothing(sup, monkeypatch):
    monkeypatch.setenv("CHAT_ORDERS_ENABLED", "false")
    backend = Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel"}])
    r = sup.turn(FARMER, "s1", "calcium gel", include_audio=False)
    assert r["state"] == "CANCELLED"
    assert r["response_text"] == service._TEXT["en"]["unavailable"]
    assert backend.calls == {"search": [], "quote": [], "create": []}


def test_main_backend_not_configured_says_unavailable(sup, monkeypatch):
    backend = Backend(monkeypatch, available=False)
    _say(sup, [{"product_query": "calcium gel"}])
    r = sup.turn(FARMER, "s1", "calcium gel", include_audio=False)
    assert r["response_text"] == service._TEXT["en"]["unavailable"]
    assert backend.calls["search"] == []


def test_quote_short_stock_asks_again_with_what_is_left(sup, monkeypatch):
    Backend(monkeypatch, quote=[{"status": 409, "body": {"code": 409, "reason": "items_unavailable", "problems": [
        {"productId": CALCIUM["productId"], "reason": "insufficient_stock", "available": 3}]}}])
    _say(sup, [{"product_query": "calcium gel", "quantity": 5}])
    r = sup.turn(FARMER, "s1", "5 calcium gel", include_audio=False)
    assert r["state"] == "QUANTITY"
    assert "3" in r["response_text"]
    assert r["options"]["choices"] == ["1", "2", "3"]


def test_quote_out_of_stock_goes_back_to_choosing_a_product(sup, monkeypatch):
    Backend(monkeypatch, quote=[{"status": 409, "body": {"reason": "items_unavailable", "problems": [
        {"productId": CALCIUM["productId"], "reason": "insufficient_stock", "available": 0}]}}])
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}])
    r = sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    assert r["state"] == "SEARCHING"
    assert r["draft"]["product"] is None


def test_payment_not_started_stays_at_confirm_and_yes_retries(sup, monkeypatch):
    backend = Backend(monkeypatch, create=[
        {"status": 502, "body": {"reason": "payment_unavailable", "orderId": "55b00a1a-9622-4109-b1eb-21bb9858bfa9"}},
        _created(reused=True),
    ])
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {"confirmation_signal": "yes"}, {"confirmation_signal": "yes"}])
    sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    r2 = sup.turn(FARMER, "s1", "yes", include_audio=False)
    assert r2["state"] == "CONFIRMING"
    assert r2["response_text"] == service._TEXT["en"]["payment_retry"]
    r3 = sup.turn(FARMER, "s1", "yes", include_audio=False)
    assert r3["state"] == "ORDERED"
    assert len(backend.calls["create"]) == 2


def test_no_answer_from_main_backend_on_create_stays_at_confirm(sup, monkeypatch):
    Backend(monkeypatch, create=[{"status": None, "body": {}}])
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {"confirmation_signal": "yes"}])
    sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "yes", include_audio=False)
    assert r["state"] == "CONFIRMING"
    assert r["response_text"] == service._TEXT["en"]["order_failed"]
    assert "order" not in r


def test_stock_changed_on_create_asks_the_quantity_again(sup, monkeypatch):
    Backend(monkeypatch, create=[{"status": 409, "body": {"reason": "stock_changed"}}])
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {"confirmation_signal": "yes"}])
    sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "yes", include_audio=False)
    assert r["state"] == "QUANTITY"
    assert "Calcium Gel" in r["response_text"]


def test_no_address_on_file_asks_for_one_and_uses_the_reply(sup, monkeypatch):
    backend = Backend(monkeypatch, quote=[_quote(address=""), _quote(address="Near temple, Wakad")])
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {}])  # LLM misses the address
    r1 = sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    assert r1["state"] == "ADDRESS"
    r2 = sup.turn(FARMER, "s1", "Near temple, Wakad", include_audio=False)
    assert r2["state"] == "CONFIRMING"
    assert backend.calls["quote"][1]["args"][2] == "Near temple, Wakad"


def test_address_required_on_create_asks_for_an_address(sup, monkeypatch):
    Backend(monkeypatch, create=[{"status": 422, "body": {"reason": "address_required"}}])
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {"confirmation_signal": "yes"}])
    sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "yes", include_audio=False)
    assert r["state"] == "ADDRESS"


def test_prescription_products_say_so_at_confirm(sup, monkeypatch):
    Backend(monkeypatch, search=[{"storeAssigned": True, "products": [{**CALCIUM, "prescriptionRequired": True}]}])
    _say(sup, [{"product_query": "calcium gel", "quantity": 1}])
    r = sup.turn(FARMER, "s1", "1 calcium gel", include_audio=False)
    assert service._TEXT["en"]["prescription"] in r["response_text"]


def test_tapped_yes_pill_orders_even_when_the_llm_reads_nothing(sup, monkeypatch):
    backend = Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {}])
    sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "Yes", include_audio=False)
    assert r["state"] == "ORDERED"
    assert len(backend.calls["create"]) == 1


def test_hindi_conversation_gets_hindi_text_and_pills(sup, monkeypatch):
    backend = Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {}])
    r1 = sup.turn(FARMER, "s1", "2 कैल्शियम जेल", language="hi-IN", include_audio=False)
    assert r1["response_text"].endswith("क्या मैं ऑर्डर कर दूँ?")
    assert r1["options"]["choices"] == ["हाँ", "नहीं"]
    r2 = sup.turn(FARMER, "s1", "हाँ", language="hi-IN", include_audio=False)
    assert r2["state"] == "ORDERED"
    assert len(backend.calls["create"]) == 1


def test_a_second_yes_after_ordering_does_not_order_again(sup, monkeypatch):
    backend = Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {"confirmation_signal": "yes"}, {"confirmation_signal": "yes"}])
    sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    sup.turn(FARMER, "s1", "yes", include_audio=False)
    r = sup.turn(FARMER, "s1", "yes", include_audio=False)
    assert r["state"] == "SEARCHING"
    assert len(backend.calls["create"]) == 1


def test_llm_failure_never_breaks_the_turn(sup, monkeypatch):
    Backend(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("bedrock down")

    monkeypatch.setattr(service, "BedrockTextAdapter", boom)
    r = sup.turn(FARMER, "s1", "something", include_audio=False)
    assert r["state"] == "SEARCHING"
    assert r["response_text"] == service._TEXT["en"]["welcome"]


def test_off_topic_message_is_released_and_the_order_closed(sup, monkeypatch):
    backend = Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel"}, {"off_topic": True}, {}])
    sup.turn(FARMER, "s1", "calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "will it rain tomorrow?", include_audio=False)
    assert r["released"] is True
    assert r["state"] == "CANCELLED"
    assert backend.calls["quote"] == []
    assert sup._load("s1", FARMER, "en-IN")["state"] == "CANCELLED"
    # The next order starts fresh.
    r3 = sup.turn(FARMER, "s1", "hello", include_audio=False)
    assert r3["state"] == "SEARCHING" and r3["draft"]["product"] is None


def test_off_topic_flag_is_ignored_when_the_message_also_answers_the_order(sup, monkeypatch):
    Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel"}, {"off_topic": True, "quantity": 2}])
    sup.turn(FARMER, "s1", "calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "2, and is it going to rain?", include_audio=False)
    assert "released" not in r
    assert r["state"] == "CONFIRMING"


def test_a_bare_number_is_never_released_even_if_the_llm_says_off_topic(sup, monkeypatch):
    Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel"}, {"off_topic": True}])
    sup.turn(FARMER, "s1", "calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "3", include_audio=False)
    assert "released" not in r
    assert r["draft"]["quantity"] == 3


def test_off_topic_at_the_address_step_is_not_taken_as_an_address(sup, monkeypatch):
    backend = Backend(monkeypatch, quote=[_quote(address="")])
    _say(sup, [{"product_query": "calcium gel", "quantity": 2}, {"off_topic": True}])
    r1 = sup.turn(FARMER, "s1", "2 calcium gel", include_audio=False)
    assert r1["state"] == "ADDRESS"
    r2 = sup.turn(FARMER, "s1", "my goat is not eating since morning", include_audio=False)
    assert r2["released"] is True
    assert len(backend.calls["quote"]) == 1, "the off-topic text must not be sent as an address"


def test_number_typed_next_to_the_product_is_used_when_the_llm_drops_it(sup, monkeypatch):
    backend = Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel"}])  # the LLM named the product but gave no quantity
    r = sup.turn(FARMER, "s1", "calcium gel chahiye 2", include_audio=False)
    assert r["state"] == "CONFIRMING"
    assert backend.calls["quote"][0]["args"][1] == [{"productId": CALCIUM["productId"], "quantity": 2}]


@pytest.mark.parametrize("text", ["calcium gel 500 ml", "calcium gel 1 L", "calcium gel 1.5 litre",
                                  "2 or 3 calcium gel", "calcium gel for 411057"])
def test_pack_sizes_several_numbers_or_a_pin_are_not_taken_as_the_quantity(sup, monkeypatch, text):
    backend = Backend(monkeypatch)
    _say(sup, [{"product_query": "calcium gel"}])
    r = sup.turn(FARMER, "s1", text, include_audio=False)
    assert r["state"] == "QUANTITY" and r["draft"]["quantity"] is None
    assert backend.calls["quote"] == []


@pytest.mark.parametrize("text, number", [
    ("2 calcium gel", 2), ("calcium gel chahiye 3", 3), ("कैल्शियम जेल २ चाहिए", 2), ("10 dewormer", 10),
    ("calcium gel", None), ("15 calcium gel", None), ("0 calcium gel", None), ("calcium gel 500ml", None),
    ("calcium gel 1 kg", None), ("Pune 411057", None), ("2 and 3", None), ("", None),
])
def test_number_in_text(text, number):
    assert service._number_in_text(text) == number


def test_a_number_while_choosing_picks_an_option_and_is_not_a_quantity(sup, monkeypatch):
    Backend(monkeypatch, search=[{"storeAssigned": True, "products": [CALCIUM, CALCIUM_PLUS]}])
    _say(sup, [{"product_query": "calcium"}, {}])
    sup.turn(FARMER, "s1", "calcium", include_audio=False)
    r = sup.turn(FARMER, "s1", "2", include_audio=False)
    assert r["state"] == "QUANTITY"
    assert r["draft"]["product"]["productId"] == CALCIUM_PLUS["productId"]
    assert r["draft"]["quantity"] is None


def test_message_for_another_agent_is_released_when_the_llm_reads_nothing(sup, monkeypatch):
    backend = Backend(monkeypatch)
    asked = []
    sup.topic_check = lambda text: asked.append(text) or "weather"
    _say(sup, [{"product_query": "calcium gel"}, {}])  # the LLM did not flag it as off topic
    sup.turn(FARMER, "s1", "calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "kal barish hogi kya?", include_audio=False)
    assert r["released"] is True and r["topic"] == "weather"
    assert r["state"] == "CANCELLED"
    assert asked == ["kal barish hogi kya?"]
    assert backend.calls["quote"] == []


@pytest.mark.parametrize("topic", ["query", "order", None, "something unknown"])
def test_query_or_order_topics_keep_the_order(sup, monkeypatch, topic):
    """"query" is the classifier's catch-all ("ok", a price question), so
    only the other agents' areas let the order go."""
    Backend(monkeypatch)
    sup.topic_check = lambda text: topic
    _say(sup, [{"product_query": "calcium gel"}, {}])
    sup.turn(FARMER, "s1", "calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "ok", include_audio=False)
    assert "released" not in r
    assert r["state"] == "QUANTITY"


def test_topic_check_failure_keeps_the_order(sup, monkeypatch):
    Backend(monkeypatch)

    def broken(text):
        raise RuntimeError("classifier down")

    sup.topic_check = broken
    _say(sup, [{"product_query": "calcium gel"}, {}])
    sup.turn(FARMER, "s1", "calcium gel", include_audio=False)
    r = sup.turn(FARMER, "s1", "kal barish hogi kya?", include_audio=False)
    assert "released" not in r and r["state"] == "QUANTITY"


def test_topic_is_not_checked_for_a_message_that_answers_the_order(sup, monkeypatch):
    Backend(monkeypatch)
    asked = []
    sup.topic_check = lambda text: asked.append(text) or "weather"
    _say(sup, [{"product_query": "calcium gel"}, {"quantity": 2}, {"confirmation_signal": "no"}])
    sup.turn(FARMER, "s1", "calcium gel", include_audio=False)
    sup.turn(FARMER, "s1", "2", include_audio=False)
    r = sup.turn(FARMER, "s1", "no", include_audio=False)
    assert r["state"] == "CORRECTING"
    assert asked == []


def test_every_language_has_every_message_with_the_same_placeholders():
    import re

    keys = set(service._TEXT["en"])
    for lang, catalog in service._TEXT.items():
        assert set(catalog) == keys, lang
        for key in keys:
            assert set(re.findall(r"\{(\w+)\}", catalog[key])) == set(re.findall(r"\{(\w+)\}", service._TEXT["en"][key])), (lang, key)
    assert set(service._YES_NO) == set(service._TEXT) == set(service._OTHER_LABEL)


@pytest.mark.parametrize("value, shown", [(240, "240"), (240.0, "240"), (730.5, "730.50"), ("99", "99")])
def test_money_display(value, shown):
    assert service._money(value) == shown
