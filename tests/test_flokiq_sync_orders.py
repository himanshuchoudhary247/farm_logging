"""flokiq_sync order calls (search_products / quote_order / create_order):
they stay off unless configured, skip local demo farmers, send the internal
key, return main_backend's status and reason to the caller, and never raise."""
import pytest

from services.flokiq_sync import client

FARMER = "9e95446d-c317-4074-b698-c8cc35325de6"
ITEMS = [{"productId": "230bd59c-91d6-48f6-8d5a-bcdaa1c6b5c4", "quantity": 2}]


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("FLOKIQ_SYNC_ENABLED", "true")
    monkeypatch.setenv("FLOKIQ_API_BASE_URL", "https://backend.test/api/v1/")
    monkeypatch.setenv("FLOKIQ_INTERNAL_API_KEY", "secret-key")


def _capture(monkeypatch, resp):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(client.requests, "request", fake_request)
    return calls


def test_off_by_default_makes_no_call(monkeypatch):
    monkeypatch.delenv("FLOKIQ_SYNC_ENABLED", raising=False)
    calls = _capture(monkeypatch, _Resp())
    assert client.orders_available(FARMER) is False
    assert client.search_products(FARMER, "calcium") is None
    assert client.quote_order(FARMER, ITEMS) == {"status": None, "body": {}}
    assert client.create_order(FARMER, ITEMS) == {"status": None, "body": {}}
    assert calls == []


def test_demo_farmer_id_is_skipped(on, monkeypatch):
    calls = _capture(monkeypatch, _Resp())
    assert client.orders_available("f-001") is False
    assert client.search_products("f-001", "calcium") is None
    assert calls == []


def test_search_sends_the_farmer_query_and_key(on, monkeypatch):
    products = [{"productId": "p-1", "name": "Calcium Gel", "unitPrice": 120, "available": 15}]
    calls = _capture(monkeypatch, _Resp(200, {"storeAssigned": True, "products": products}))
    assert client.search_products(FARMER, "calcium gel", limit=5) == {"storeAssigned": True, "products": products}
    call = calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://backend.test/api/v1/internal/orders/products"
    assert call["params"] == {"farmerId": FARMER, "search": "calcium gel", "limit": 5}
    assert call["headers"] == {"X-Internal-Api-Key": "secret-key"}


def test_search_limit_is_kept_inside_what_main_backend_accepts(on, monkeypatch):
    calls = _capture(monkeypatch, _Resp(200, {"storeAssigned": True, "products": []}))
    client.search_products(FARMER, "x", limit=500)
    client.search_products(FARMER, "x", limit=0)
    assert [c["params"]["limit"] for c in calls] == [20, 1]


@pytest.mark.parametrize("resp", [_Resp(500, {"message": "boom"}), _Resp(200, None), client.requests.ConnectionError("down")])
def test_search_failure_returns_none(on, monkeypatch, resp):
    _capture(monkeypatch, resp)
    assert client.search_products(FARMER, "calcium") is None


def test_search_with_a_bad_products_field_returns_an_empty_list(on, monkeypatch):
    _capture(monkeypatch, _Resp(200, {"storeAssigned": True, "products": "nope"}))
    assert client.search_products(FARMER, "calcium") == {"storeAssigned": True, "products": []}


def test_quote_posts_items_and_returns_status_and_body(on, monkeypatch):
    body = {"totalAmount": 240, "currency": "INR", "deliveryAddress": "Pune", "items": []}
    calls = _capture(monkeypatch, _Resp(200, body))
    assert client.quote_order(FARMER, ITEMS) == {"status": 200, "body": body}
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "https://backend.test/api/v1/internal/orders/quote"
    # No address given: the key is left out so main_backend uses the profile address.
    assert calls[0]["json"] == {"farmerId": FARMER, "items": ITEMS}


def test_quote_problem_is_passed_through(on, monkeypatch):
    body = {"code": 409, "reason": "items_unavailable", "problems": [{"productId": "p", "reason": "insufficient_stock", "available": 3}]}
    _capture(monkeypatch, _Resp(409, body))
    assert client.quote_order(FARMER, ITEMS) == {"status": 409, "body": body}


def test_create_sends_the_address_and_returns_the_payment(on, monkeypatch):
    body = {"orderId": "o-1", "payment": {"razorpayOrderId": "order_1", "amount": 24000, "currency": "INR"}}
    calls = _capture(monkeypatch, _Resp(201, body))
    assert client.create_order(FARMER, ITEMS, "Near temple, Wakad") == {"status": 201, "body": body}
    assert calls[0]["url"] == "https://backend.test/api/v1/internal/orders"
    assert calls[0]["json"] == {"farmerId": FARMER, "items": ITEMS, "deliveryAddress": "Near temple, Wakad"}


def test_create_network_error_never_raises(on, monkeypatch):
    _capture(monkeypatch, client.requests.Timeout("slow"))
    assert client.create_order(FARMER, ITEMS) == {"status": None, "body": {}}


def test_non_object_json_body_becomes_empty(on, monkeypatch):
    _capture(monkeypatch, _Resp(502, ["unexpected"]))
    assert client.create_order(FARMER, ITEMS) == {"status": 502, "body": {}}
