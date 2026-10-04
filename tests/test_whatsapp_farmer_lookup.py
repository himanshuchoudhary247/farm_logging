"""Tests for storage.get_farmer_by_whatsapp_phone / _canonicalize_phone.

The load-bearing behavior tested here is the user's stated requirement:
"if a farmer is registered with a phone number we shall not ask for any
farmer id or something -- we should know we have this farmer in system".
So the phone-only match (no whatsapp_phone set) MUST resolve to the
farmer -- this is the common case for a farmer who's registered in the
system and just messages WhatsApp for the first time.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def storage_mod(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FARMER_CHAT_DATA_DIR", str(tmp_path))
    import storage
    importlib.reload(storage)
    return storage


def _write_farmers(storage_mod, tmp_path: Path, rows: list[dict]) -> None:
    from models import Farmer
    dumps = []
    for row in rows:
        f = Farmer(**{**{"password_hash": "x", "login_username": row["id"]}, **row})
        dumps.append(f.model_dump())
    storage_mod.atomic_write_json(tmp_path / "farmers.json", dumps)


def test_canonicalize_phone_variants_collapse_to_same_key(storage_mod):
    canon = storage_mod._canonicalize_phone
    assert canon("+91 98765 43210") == "+919876543210"
    assert canon("+91-98765-43210") == "+919876543210"
    assert canon("+91(98765)43210") == "+919876543210"
    assert canon("whatsapp:+91-98765 43210") == "+919876543210"
    assert canon("tel:+919876543210") == "+919876543210"
    assert canon("919876543210") == "919876543210"  # no leading + preserved
    assert canon("") == ""
    assert canon(None) == ""


def test_resolves_farmer_by_phone_alone_no_whatsapp_phone_set(storage_mod, tmp_path):
    """The load-bearing case: farmer is registered with their phone in
    Farmer.phone, has never touched WhatsApp before. First WhatsApp
    message from that number MUST resolve to them -- no enrollment
    prompt, no lookup ceremony. Explicit test for user's stated
    requirement."""
    _write_farmers(storage_mod, tmp_path, [
        {"id": "f-1", "name": "Asha", "phone": "+919876543210"},
        {"id": "f-2", "name": "Ravi", "phone": "+911111111111"},
    ])
    found = storage_mod.get_farmer_by_whatsapp_phone("whatsapp:+91-98765 43210")
    assert found is not None
    assert found.id == "f-1"


def test_whatsapp_phone_override_wins_over_phone(storage_mod, tmp_path):
    """If a farmer explicitly sets whatsapp_phone (e.g. because they
    message from a spouse's number that's different from their
    registered phone), that override takes precedence."""
    _write_farmers(storage_mod, tmp_path, [
        {"id": "f-1", "name": "Asha", "phone": "+919876543210"},
        {"id": "f-2", "name": "Ravi", "phone": "+919999999999", "whatsapp_phone": "+919876543210"},
    ])
    found = storage_mod.get_farmer_by_whatsapp_phone("+919876543210")
    assert found is not None
    assert found.id == "f-2", "whatsapp_phone override wins even when another farmer's phone matches"


def test_unknown_phone_returns_none(storage_mod, tmp_path):
    _write_farmers(storage_mod, tmp_path, [{"id": "f-1", "name": "A", "phone": "+911111111111"}])
    assert storage_mod.get_farmer_by_whatsapp_phone("+919999999999") is None


def test_empty_or_none_phone_returns_none(storage_mod, tmp_path):
    _write_farmers(storage_mod, tmp_path, [{"id": "f-1", "name": "A", "phone": "+911111111111"}])
    assert storage_mod.get_farmer_by_whatsapp_phone("") is None
    assert storage_mod.get_farmer_by_whatsapp_phone(None) is None  # type: ignore[arg-type]


def test_update_farmer_whatsapp_phone_persists(storage_mod, tmp_path):
    _write_farmers(storage_mod, tmp_path, [{"id": "f-1", "name": "Asha", "phone": "+911111111111"}])
    updated = storage_mod.update_farmer_whatsapp_phone("f-1", "+919876543210")
    assert updated.whatsapp_phone == "+919876543210"
    # Re-read from disk to confirm the write actually landed.
    reloaded = storage_mod.get_farmer_by_id("f-1")
    assert reloaded is not None
    assert reloaded.whatsapp_phone == "+919876543210"


def test_update_farmer_whatsapp_phone_missing_farmer_raises(storage_mod, tmp_path):
    _write_farmers(storage_mod, tmp_path, [{"id": "f-1", "name": "Asha", "phone": ""}])
    with pytest.raises(ValueError, match="Farmer not found"):
        storage_mod.update_farmer_whatsapp_phone("f-nonexistent", "+911111111111")
