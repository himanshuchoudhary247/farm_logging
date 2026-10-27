"""Outbound HTTP client that writes farm_logging's appointment bookings to
the main FlokIQ backend (main_backend), so a booking made through the
Chocolate chatbot also shows in the app's appointment list.

Called from appointment_supervisor.submit() AFTER the local write already
succeeded -- this is best-effort sync, never the primary write path. A
failure here is logged and swallowed; the farmer's booking is never lost
because the local JSON store already has it.

Appointments go to main_backend's server-to-server route
POST {FLOKIQ_API_BASE_URL}/internal/appointments, authenticated with a
shared key in the X-Internal-Api-Key header (main_backend's logins all need
an OTP, so this service cannot log in as a user). main_backend then runs its
normal booking logic: it assigns the farmer's store doctor and sends the
booking SMS, same as an in-app booking.

It also reads the PIN code of the farmer's farm from
GET {FLOKIQ_API_BASE_URL}/internal/farmers/<id>/farm-location (same key), so
weather advice can use it instead of asking the farmer (get_farm_pincode).

It also persists geocoded PIN/place -> lat,lon lookups to
GET/POST {FLOKIQ_API_BASE_URL}/internal/geocode (same key), so a location
weather_alert resolves once via Nominatim survives this process's restarts
and its own short in-memory cache expiring (get_cached_geocode, save_geocode).

It also writes health logs created in the chatbot to
POST {FLOKIQ_API_BASE_URL}/internal/health-logs (same key), so a health
check done through the chatbot shows up in the app's farmer-facing health
history (create_health_log).

Config (env, same precedence pattern as the rest of this app):
  FLOKIQ_SYNC_ENABLED       "true"/"1" to actually call out. Default off --
                            ships inert until explicitly turned on.
  FLOKIQ_API_BASE_URL       main_backend base URL including /v1, e.g.
                            https://api.example.com/v1
  FLOKIQ_INTERNAL_API_KEY   the same value as INTERNAL_API_KEY on main_backend.
  FLOKIQ_SYNC_HEALTH_LOGS   "true" to also call POST /internal/health-logs,
                            on top of FLOKIQ_SYNC_ENABLED.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Optional

import requests

_log = logging.getLogger("flokiq_sync")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_TRUTHY = {"1", "true", "yes", "on"}
# main_backend's validation limit for appointment notes.
_MAX_NOTES = 1000
# main_backend farmer ids are UUIDs. Local demo farmers ("f-001") don't
# exist there, so calling for them would only ever fail.
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def is_enabled() -> bool:
    return os.getenv("FLOKIQ_SYNC_ENABLED", "").lower() in _TRUTHY


def _health_logs_enabled() -> bool:
    return os.getenv("FLOKIQ_SYNC_HEALTH_LOGS", "").lower() in _TRUTHY


def _base_url() -> Optional[str]:
    return os.getenv("FLOKIQ_API_BASE_URL")


def build_appointment_notes(values: dict[str, Any]) -> str:
    """Short note for the vet in the app: which animal, what is wrong, and
    that it was booked through the chatbot. The local booking keeps the
    full details, but main_backend only stores a free-text note.
    e.g. "GAURI (goat): not eating. Booked via Chocolate." """
    animal = str(values.get("animal_name") or "").strip()
    species = str(values.get("species") or "").strip()
    issue = str(values.get("issue") or "").strip()
    if not issue:
        symptoms = [str(s).strip() for s in (values.get("symptoms") or []) if str(s).strip()]
        issue = ", ".join(symptoms)
    extra = str(values.get("miscellaneous_notes") or values.get("notes") or "").strip()

    head = f"{animal} ({species})" if animal and species else (animal or species)
    parts: list[str] = []
    if head and issue:
        parts.append(f"{head}: {issue}.")
    elif head or issue:
        parts.append(f"{head or issue}.")
    if extra:
        parts.append(extra if extra.endswith(".") else f"{extra}.")
    parts.append("Booked via Chocolate.")
    return " ".join(parts)[:_MAX_NOTES]


def _can_sync_for_farmer(farmer_id: str) -> bool:
    """Shared precondition check for every main_backend write call in
    this module: sync enabled, base URL + key configured, and farmer_id
    is a real main_backend farmer id (not a local demo one). Single
    source of truth -- create_appointment and will_attempt_appointment_
    sync used to each re-implement this check, with nothing enforcing
    they stayed in agreement (reviewer-found risk, PR #64)."""
    if not is_enabled():
        return False
    base = (_base_url() or "").rstrip("/")
    key = os.getenv("FLOKIQ_INTERNAL_API_KEY", "")
    if not base or not key:
        _log.warning("flokiq_sync enabled but FLOKIQ_API_BASE_URL or FLOKIQ_INTERNAL_API_KEY unset -- skipping")
        return False
    return bool(_UUID_RE.match(str(farmer_id or "")))


def will_attempt_appointment_sync(farmer_id: str) -> bool:
    """True if create_appointment would actually attempt a network call
    for this farmer_id right now -- lets a caller distinguish "sync
    doesn't apply here" (disabled, unconfigured, a local demo farmer_id)
    from "sync was attempted and failed," both of which create_appointment
    reports identically as None."""
    return _can_sync_for_farmer(farmer_id)


def create_appointment(
    farmer_id: str,
    date: str,
    time: str,
    notes: str = "",
    health_log_id: Optional[str] = None,
    timeout_s: float = 5.0,
) -> Optional[dict[str, Any]]:
    """POST /internal/appointments on main_backend. Returns the created (or
    already existing) appointment, or None if sync is disabled,
    unconfigured or failed -- caller should treat None as "not synced this
    time", not an error, and keep the local record as the source of truth
    for the booking. main_backend returns the existing appointment instead
    of a duplicate if the same farmer/date/time is sent twice."""
    if not will_attempt_appointment_sync(farmer_id):
        return None
    base = (_base_url() or "").rstrip("/")
    key = os.getenv("FLOKIQ_INTERNAL_API_KEY", "")

    payload: dict[str, Any] = {
        "farmerId": farmer_id,
        "date": date,
        "time": time,
        "notes": (notes or "")[:_MAX_NOTES],
    }
    if health_log_id:
        payload["healthLogId"] = health_log_id

    try:
        resp = requests.post(
            f"{base}/internal/appointments",
            json=payload,
            headers={"X-Internal-Api-Key": key},
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        _log.warning("flokiq_sync create_appointment failed farmer=%s err=%s", farmer_id, exc)
        return None

    if resp.status_code not in (200, 201):
        _log.warning(
            "flokiq_sync create_appointment failed farmer=%s status=%s body=%s",
            farmer_id, resp.status_code, resp.text[:200],
        )
        return None
    try:
        result = resp.json()
    except ValueError:
        result = {}
    _log.info("flokiq_sync appointment synced id=%s farmer=%s", result.get("id"), farmer_id)
    return result


def create_health_log(
    farmer_id: str,
    pincode: str,
    symptoms: list[str],
    animal_id: Optional[str] = None,
    risk_level: Optional[str] = None,
    ai_diagnosis_suggestion: Optional[str] = None,
    potential_ailments: Optional[list[str]] = None,
    first_aid_advice: Optional[str] = None,
    timeout_s: float = 5.0,
) -> Optional[dict[str, Any]]:
    """POST /internal/health-logs on main_backend, authenticated with the
    same X-Internal-Api-Key as create_appointment (main_backend resolves
    farmer.userId itself -- this never needs main_backend's internal User
    id). Off unless FLOKIQ_SYNC_HEALTH_LOGS is set, on top of
    FLOKIQ_SYNC_ENABLED. Same best-effort contract as create_appointment:
    None means "not synced," never raises."""
    if not is_enabled() or not _health_logs_enabled():
        return None
    base = (_base_url() or "").rstrip("/")
    key = os.getenv("FLOKIQ_INTERNAL_API_KEY", "")
    if not base or not key:
        _log.warning("flokiq_sync enabled but FLOKIQ_API_BASE_URL or FLOKIQ_INTERNAL_API_KEY unset -- skipping")
        return None
    if not _UUID_RE.match(str(farmer_id or "")):
        _log.info("flokiq_sync skipped farmer=%s -- not a main_backend farmer id", farmer_id)
        return None
    # Reviewer-found bug: values["weather_location"] (this function's
    # pincode argument, from the call site) can be a place name like
    # "Pune" rather than a PIN -- sending that as pincode would 400
    # against main_backend's validation. pincode is NOT NULL there, so
    # an invalid value has to be treated the same as a missing one
    # (skip this sync), not sent and left to fail.
    if not pincode or not _PIN_RE.match(str(pincode)):
        _log.warning("flokiq_sync create_health_log skipped -- pincode is not a 6-digit PIN: %r", pincode)
        return None

    payload: dict[str, Any] = {
        "farmerId": farmer_id,
        "pincode": pincode,
        "symptomsReported": symptoms or [],
    }
    # Reviewer-found bug: main_backend requires animalId to be a UUID,
    # but animals registered through Chocolate have local, non-UUID ids
    # (e.g. "MLTEST03"). Sending one of those would 400 the ENTIRE health
    # log, dropping real symptoms/AI-diagnosis data over a field that's
    # optional on main_backend's side. Only send it when it's actually a
    # main_backend-shaped id; otherwise the log still goes through, just
    # without an animal link.
    if animal_id and _UUID_RE.match(str(animal_id)):
        payload["animalId"] = animal_id
    # riskLevel comes from an LLM and main_backend only accepts the exact
    # casing Low/Medium/High -- normalize here so a model that returns
    # "low"/"LOW" doesn't 400 the log. An unrecognized value is omitted
    # (optional on main_backend's side) rather than sent and rejected.
    normalized_risk_level = {"low": "Low", "medium": "Medium", "high": "High"}.get(
        str(risk_level or "").strip().lower()
    )
    if normalized_risk_level:
        payload["riskLevel"] = normalized_risk_level
    if ai_diagnosis_suggestion:
        payload["aiDiagnosisSuggestion"] = ai_diagnosis_suggestion
    if potential_ailments:
        payload["potentialAilments"] = potential_ailments
    if first_aid_advice:
        payload["firstAidAdvice"] = first_aid_advice

    try:
        resp = requests.post(
            f"{base}/internal/health-logs",
            json=payload,
            headers={"X-Internal-Api-Key": key},
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        _log.warning("flokiq_sync create_health_log failed farmer=%s err=%s", farmer_id, exc)
        return None

    if resp.status_code not in (200, 201):
        _log.warning(
            "flokiq_sync create_health_log failed farmer=%s status=%s body=%s",
            farmer_id, resp.status_code, resp.text[:200],
        )
        return None
    try:
        result = resp.json()
    except ValueError:
        result = {}
    _log.info("flokiq_sync health_log created id=%s farmer=%s", result.get("log_id"), farmer_id)
    return result


# Farm PIN lookups are cached per farmer, so weather does not call main_backend
# on every turn. A found or missing PIN is kept for an hour (it changes only
# when the farm is edited); a failed call is retried after a minute, so an
# outage does not add the timeout to every weather turn.
_FARM_PIN_TTL_S = 60 * 60
_FARM_PIN_RETRY_S = 60
_FARM_PIN_CACHE_MAX = 1000
_PIN_RE = re.compile(r"^[1-9][0-9]{5}$")
_farm_pin_cache: dict[str, tuple[float, Optional[str]]] = {}
_farm_pin_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def get_farm_pincode(farmer_id: str, timeout_s: float = 3.0) -> Optional[str]:
    """PIN code of the farmer's farm in main_backend
    (GET /internal/farmers/{farmer_id}/farm-location), or None if sync is off
    or unconfigured, the farmer is not a main_backend farmer, the farm has no
    valid PIN, or the call failed. Used by weather when the farmer has no
    saved weather location, so they are not asked for a PIN the app already
    has. Never raises."""
    if not is_enabled():
        return None
    base = (_base_url() or "").rstrip("/")
    key = os.getenv("FLOKIQ_INTERNAL_API_KEY", "")
    if not base or not key or not _UUID_RE.match(str(farmer_id or "")):
        return None

    now = _now()
    with _farm_pin_lock:
        hit = _farm_pin_cache.get(farmer_id)
        if hit is not None and hit[0] > now:
            return hit[1]

    pincode, ttl = _fetch_farm_pincode(base, key, farmer_id, timeout_s)
    with _farm_pin_lock:
        if len(_farm_pin_cache) >= _FARM_PIN_CACHE_MAX:
            _farm_pin_cache.clear()
        _farm_pin_cache[farmer_id] = (now + ttl, pincode)
    return pincode


def _fetch_farm_pincode(base: str, key: str, farmer_id: str, timeout_s: float) -> tuple[Optional[str], float]:
    """One call to main_backend: (pincode or None, how long to cache it)."""
    try:
        resp = requests.get(
            f"{base}/internal/farmers/{farmer_id}/farm-location",
            headers={"X-Internal-Api-Key": key},
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        _log.warning("flokiq_sync farm pincode failed farmer=%s err=%s", farmer_id, exc)
        return None, _FARM_PIN_RETRY_S

    if resp.status_code == 404:
        _log.info("flokiq_sync farm pincode none farmer=%s", farmer_id)
        return None, _FARM_PIN_TTL_S
    if resp.status_code != 200:
        _log.warning(
            "flokiq_sync farm pincode failed farmer=%s status=%s body=%s",
            farmer_id, resp.status_code, resp.text[:200],
        )
        return None, _FARM_PIN_RETRY_S

    try:
        pincode = str((resp.json() or {}).get("pincode") or "").strip()
    except (ValueError, AttributeError):
        pincode = ""
    if not _PIN_RE.match(pincode):
        _log.warning("flokiq_sync farm pincode not a 6-digit PIN farmer=%s", farmer_id)
        return None, _FARM_PIN_TTL_S
    _log.info("flokiq_sync farm pincode found farmer=%s", farmer_id)
    return pincode, _FARM_PIN_TTL_S


def get_cached_geocode(query: str, country_code: str = "in", timeout_s: float = 3.0) -> Optional[dict[str, Any]]:
    """GET /internal/geocode on main_backend: a previously-resolved
    PIN/place -> lat,lon,display_name, or None if sync is off/unconfigured,
    nothing is cached for this query, or the call failed. A lat/lon never
    changes for a given place, so the caller can treat a hit as good
    indefinitely -- never raises."""
    if not is_enabled():
        return None
    base = (_base_url() or "").rstrip("/")
    key = os.getenv("FLOKIQ_INTERNAL_API_KEY", "")
    if not base or not key:
        return None

    try:
        resp = requests.get(
            f"{base}/internal/geocode",
            params={"query": query, "countryCode": country_code},
            headers={"X-Internal-Api-Key": key},
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        _log.warning("flokiq_sync get_cached_geocode failed query=%s err=%s", query, exc)
        return None

    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        _log.warning(
            "flokiq_sync get_cached_geocode failed query=%s status=%s body=%s",
            query, resp.status_code, resp.text[:200],
        )
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def save_geocode(
    query: str,
    display_name: str,
    lat: float,
    lon: float,
    country_code: str = "in",
    district: Optional[str] = None,
    state: Optional[str] = None,
    source: str = "nominatim",
    timeout_s: float = 3.0,
) -> None:
    """POST /internal/geocode on main_backend: persist a location
    weather_alert just resolved, so the next process (or this one after
    its in-memory cache expires) does not need another Nominatim call for
    the same PIN/place. Best-effort, like every other call in this module
    -- a failure here only means the next lookup also goes to Nominatim,
    never an error for the farmer. Never raises."""
    if not is_enabled():
        return
    base = (_base_url() or "").rstrip("/")
    key = os.getenv("FLOKIQ_INTERNAL_API_KEY", "")
    if not base or not key:
        return

    payload = {
        "query": query,
        "countryCode": country_code,
        "displayName": display_name,
        "lat": lat,
        "lon": lon,
        "district": district or "",
        "state": state or "",
        "source": source,
    }
    try:
        resp = requests.post(
            f"{base}/internal/geocode",
            json=payload,
            headers={"X-Internal-Api-Key": key},
            timeout=timeout_s,
        )
        if resp.status_code != 200:
            _log.warning(
                "flokiq_sync save_geocode failed query=%s status=%s body=%s",
                query, resp.status_code, resp.text[:200],
            )
    except requests.RequestException as exc:
        _log.warning("flokiq_sync save_geocode failed query=%s err=%s", query, exc)


# A farmer's main_backend-side animals are cached briefly per farmer_id --
# unlike a farm's PIN (rarely edited), animals can be added through the app
# at any time, so this uses a much shorter TTL than _FARM_PIN_TTL_S. A
# failed call is retried sooner still, same reasoning as the PIN cache: an
# outage should not add the network timeout to every single chat turn.
_FARM_ANIMALS_TTL_S = 120
_FARM_ANIMALS_RETRY_S = 20
_FARM_ANIMALS_CACHE_MAX = 1000
_farm_animals_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_farm_animals_lock = threading.Lock()


def get_farm_animals(farmer_id: str, timeout_s: float = 3.0) -> list[dict[str, Any]]:
    """This farmer's animals in main_backend (GET /internal/farmers/
    {farmer_id}/animals), so a farmer who added an animal in the app can
    still be matched against it through the chatbot. Always returns a
    list -- empty if sync is off/unconfigured, the farmer_id isn't a
    main_backend farmer, the farm has no animals, or the call failed.
    Never raises."""
    if not is_enabled():
        return []
    base = (_base_url() or "").rstrip("/")
    key = os.getenv("FLOKIQ_INTERNAL_API_KEY", "")
    if not base or not key or not _UUID_RE.match(str(farmer_id or "")):
        return []

    now = _now()
    with _farm_animals_lock:
        hit = _farm_animals_cache.get(farmer_id)
        if hit is not None and hit[0] > now:
            return hit[1]

    animals, ttl = _fetch_farm_animals(base, key, farmer_id, timeout_s)
    with _farm_animals_lock:
        if len(_farm_animals_cache) >= _FARM_ANIMALS_CACHE_MAX:
            _farm_animals_cache.clear()
        _farm_animals_cache[farmer_id] = (now + ttl, animals)
    return animals


def _fetch_farm_animals(base: str, key: str, farmer_id: str, timeout_s: float) -> tuple[list[dict[str, Any]], float]:
    """One call to main_backend: (animals, how long to cache the result)."""
    try:
        resp = requests.get(
            f"{base}/internal/farmers/{farmer_id}/animals",
            headers={"X-Internal-Api-Key": key},
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        _log.warning("flokiq_sync farm animals failed farmer=%s err=%s", farmer_id, exc)
        return [], _FARM_ANIMALS_RETRY_S

    if resp.status_code != 200:
        _log.warning(
            "flokiq_sync farm animals failed farmer=%s status=%s body=%s",
            farmer_id, resp.status_code, resp.text[:200],
        )
        return [], _FARM_ANIMALS_RETRY_S

    try:
        animals = (resp.json() or {}).get("animals") or []
    except ValueError:
        animals = []
    _log.info("flokiq_sync farm animals found=%d farmer=%s", len(animals), farmer_id)
    return animals, _FARM_ANIMALS_TTL_S


# ---------------------------------------------------------------------------
# Shop orders placed through the chat (main_backend /internal/orders).
#
# The order agent (services/order_supervisor) asks main_backend three things:
# which products this farmer can order (search_products), the exact total for
# a cart (quote_order) and to create the order with its Razorpay order
# (create_order). main_backend prices everything from the farmer's own store
# and never trusts a price from here.
#
# Unlike the best-effort sync calls above, an order cannot be "saved locally
# and synced later": main_backend is the only place it can exist. So these
# calls return enough for the agent to tell the farmer what happened --
# quote_order/create_order return {"status": <HTTP status or None>, "body":
# <parsed JSON or {}>}, where status None means the call never got an answer
# (sync off or unconfigured, not a main_backend farmer, network error). They
# never raise.
# ---------------------------------------------------------------------------

def orders_available(farmer_id: str) -> bool:
    """True if the order calls below would actually reach main_backend for
    this farmer: sync enabled, base URL and key set, and a main_backend
    (UUID) farmer id. Same precondition as every write call in this module."""
    return _can_sync_for_farmer(farmer_id)


def _order_request(method: str, path: str, farmer_id: str, timeout_s: float,
                   params: Optional[dict[str, Any]] = None,
                   payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if not orders_available(farmer_id):
        return {"status": None, "body": {}}
    base = (_base_url() or "").rstrip("/")
    key = os.getenv("FLOKIQ_INTERNAL_API_KEY", "")
    try:
        resp = requests.request(
            method,
            f"{base}{path}",
            params=params,
            json=payload,
            headers={"X-Internal-Api-Key": key},
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        _log.warning("flokiq_sync %s %s failed farmer=%s err=%s", method, path, farmer_id, exc)
        return {"status": None, "body": {}}
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if resp.status_code >= 400:
        # The body carries main_backend's reason (e.g. items_unavailable);
        # no farmer data is logged beyond the id.
        _log.warning(
            "flokiq_sync %s %s farmer=%s status=%s reason=%s",
            method, path, farmer_id, resp.status_code, body.get("reason") or body.get("message"),
        )
    return {"status": resp.status_code, "body": body}


def search_products(farmer_id: str, search: str = "", limit: int = 5,
                    timeout_s: float = 5.0) -> Optional[dict[str, Any]]:
    """GET /internal/orders/products: products the farmer can order now in
    their own store, each with productId, name, unitPrice, mrp, available and
    prescriptionRequired. Returns {"storeAssigned": bool, "products": [...]},
    or None if the call could not be made or failed (the caller should say
    the shop could not be reached, not "nothing found")."""
    result = _order_request(
        "GET", "/internal/orders/products", farmer_id, timeout_s,
        params={"farmerId": farmer_id, "search": (search or "")[:100], "limit": max(1, min(int(limit), 20))},
    )
    body = result["body"]
    if result["status"] != 200 or "storeAssigned" not in body:
        # An answer without the expected shape (e.g. a proxy error page
        # with status 200) is "could not reach the shop", never "no store".
        return None
    products = body.get("products")
    return {
        "storeAssigned": bool(body.get("storeAssigned")),
        "products": products if isinstance(products, list) else [],
    }


def quote_order(farmer_id: str, items: list[dict[str, Any]], delivery_address: str = "",
                timeout_s: float = 8.0) -> dict[str, Any]:
    """POST /internal/orders/quote: the exact total for `items`
    ([{"productId", "quantity"}]) and the delivery address that would be
    used (the farmer's profile address when none is given). Nothing is saved.
    200 -> body {totalAmount, currency, deliveryAddress, items};
    409 -> body.reason 'items_unavailable' (body.problems) or 'no_store'."""
    payload: dict[str, Any] = {"farmerId": farmer_id, "items": items}
    if delivery_address:
        payload["deliveryAddress"] = delivery_address[:500]
    return _order_request("POST", "/internal/orders/quote", farmer_id, timeout_s, payload=payload)


def create_order(farmer_id: str, items: list[dict[str, Any]], delivery_address: str = "",
                 timeout_s: float = 30.0) -> dict[str, Any]:
    """POST /internal/orders: creates the unpaid order and its Razorpay order.
    201 (new) or 200 (main_backend reused the same unpaid order, e.g. after
    a retry) -> body {orderId, orderCode, totalAmount, currency,
    deliveryAddress, items, payment: {razorpayOrderId, amount, currency}}.
    409 -> 'items_unavailable' / 'stock_changed' / 'no_store';
    422 -> 'address_required'; 502 -> 'payment_unavailable' (order saved,
    a retry reuses it). The timeout is longer than the other calls because
    main_backend also prepares the order's documents while creating it; a
    retry after a timeout is safe for the same reason as above."""
    payload: dict[str, Any] = {"farmerId": farmer_id, "items": items}
    if delivery_address:
        payload["deliveryAddress"] = delivery_address[:500]
    return _order_request("POST", "/internal/orders", farmer_id, timeout_s, payload=payload)
