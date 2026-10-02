"""Tests for services/whatsapp_channel/config.py.

Exercise the env/YAML/defaults precedence chain; make sure the module
ships inert (enabled=False) with no env/yaml at all; check that unknown
intent names are dropped with a warning rather than crashing the loader.
"""
from __future__ import annotations

import pytest

from services.whatsapp_channel import config as cfg_mod


@pytest.fixture(autouse=True)
def _reset_cache_between_tests():
    """The config loader caches its result module-level; reset before AND
    after every test so env changes flow through as expected."""
    cfg_mod.reset_cache_for_tests()
    yield
    cfg_mod.reset_cache_for_tests()


def test_defaults_ship_inert(monkeypatch, tmp_path):
    """No env vars, no config file -- module is off, safe."""
    for var in ("WHATSAPP_ENABLED", "WHATSAPP_ALLOWED_INTENTS", "WHATSAPP_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CHANNELS_CONFIG_PATH", str(tmp_path / "does-not-exist.yaml"))
    c = cfg_mod.load_config()
    assert c.enabled is False, "must default to disabled so nothing changes for existing deployments"
    assert c.provider == "mock"
    assert c.enrollment_enabled is True


def test_env_wins_over_yaml(monkeypatch, tmp_path):
    yaml_file = tmp_path / "channels.yaml"
    yaml_file.write_text(
        "channels:\n"
        "  whatsapp:\n"
        "    enabled: true\n"
        "    allowed_intents: [query, weather]\n"
        "    provider: mock\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CHANNELS_CONFIG_PATH", str(yaml_file))
    monkeypatch.setenv("WHATSAPP_ALLOWED_INTENTS", "query,appointment")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "meta")
    c = cfg_mod.load_config()
    assert c.enabled is True
    assert c.allowed_intents == frozenset({"query", "appointment"})
    assert c.provider == "meta", "env WHATSAPP_PROVIDER wins over yaml"


def test_unknown_intents_dropped_not_crashed(monkeypatch, tmp_path):
    monkeypatch.setenv("CHANNELS_CONFIG_PATH", str(tmp_path / "none.yaml"))
    monkeypatch.setenv("WHATSAPP_ALLOWED_INTENTS", "query,nonsense,appointment,other")
    c = cfg_mod.load_config()
    # `nonsense` and `other` are silently dropped -- the module boots
    # rather than crashing on a config typo.
    assert c.allowed_intents == frozenset({"query", "appointment"})


def test_env_bool_and_int_parsers(monkeypatch, tmp_path):
    monkeypatch.setenv("CHANNELS_CONFIG_PATH", str(tmp_path / "none.yaml"))
    monkeypatch.setenv("WHATSAPP_ENABLED", "yes")
    monkeypatch.setenv("WHATSAPP_INCLUDE_AUDIO", "off")
    monkeypatch.setenv("WHATSAPP_RATE_LIMIT_PER_MIN", "12")
    monkeypatch.setenv("WHATSAPP_MAX_REPLY_CHARS", "1234")
    c = cfg_mod.load_config()
    assert c.enabled is True
    assert c.include_audio is False, "off/0/no/false all evaluate as false"
    assert c.per_phone_per_min == 12
    assert c.max_reply_chars == 1234


def test_reset_cache_for_tests_actually_resets(monkeypatch, tmp_path):
    """The fixture above depends on this behavior -- verify it explicitly."""
    monkeypatch.setenv("CHANNELS_CONFIG_PATH", str(tmp_path / "none.yaml"))
    monkeypatch.setenv("WHATSAPP_PROVIDER", "mock")
    a = cfg_mod.load_config()
    monkeypatch.setenv("WHATSAPP_PROVIDER", "meta")
    b_cached = cfg_mod.load_config()
    assert b_cached is a, "no reset -> cached value (env change ignored)"
    cfg_mod.reset_cache_for_tests()
    c = cfg_mod.load_config()
    assert c.provider == "meta", "after reset, new env is picked up"
