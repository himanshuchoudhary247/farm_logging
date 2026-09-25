"""Direct tests for the shared DraftSupervisor base class.

The two live subclasses (AppointmentSupervisor, AnimalRegistrationSupervisor)
exercise the base indirectly through their own extensive suites, but the base
also deserves a couple of standalone tests -- one for each future subclass
that will be built against this contract (docs/conversation_patterns.md
already anticipates a health-log flow), so the base's own guarantees don't
silently drift when the existing subclasses evolve."""
from __future__ import annotations

import json
import threading

import pytest

from services.common.draft_supervisor import (
    DraftSupervisor,
    SUPPORTED_LANGUAGES,
    _UNSET,
    _lang,
)


class _MinimalSupervisor(DraftSupervisor):
    INTAKE_SUBDIR = "test_intakes"
    MESSAGES = {
        "en": {"hello": "hi {name}"},
        "hi": {"hello": "नमस्ते {name}"},
    }

    def _fresh(self, session_id, farmer_id, language):
        return {
            "session_id": session_id,
            "farmer_id": farmer_id,
            "language": language if language in SUPPORTED_LANGUAGES else "en-IN",
            "draft": {},
        }


def test_supported_languages_and_lang_helper():
    assert set(SUPPORTED_LANGUAGES) == {"en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN"}
    assert _lang("hi-IN") == "hi"
    assert _lang("") == "en", "empty/missing tag falls back to en-IN -> 'en'"
    assert _lang(None) == "en"  # type: ignore[arg-type]


def test_unset_sentinel_is_distinct_from_none():
    assert _UNSET is not None
    assert (_UNSET is None) is False


def test_missing_intake_subdir_raises():
    class NoSubdir(DraftSupervisor):
        MESSAGES = {"en": {}}

        def _fresh(self, session_id, farmer_id, language):
            return {}

    with pytest.raises(NotImplementedError, match="INTAKE_SUBDIR"):
        NoSubdir()


def test_path_is_farmer_scoped_and_collision_safe(tmp_path):
    """The historical bug in _path (see the comment there): distinct
    session_ids like 'ab-c' and 'a@b/c' both stripped to 'abc' -- and every
    empty/emoji-only id collided to ''. sha1 over 'farmer_id:session_id' fixes
    both: different farmers with the same session_id land on different files,
    and no two distinct (farmer, session) pairs share a path."""
    sup = _MinimalSupervisor(data_dir=tmp_path)
    a = sup._path("f-1", "s-1")
    b = sup._path("f-2", "s-1")  # different farmer, same session -- must differ
    c = sup._path("f-1", "!!!")  # weird session, previously collided to ''
    d = sup._path("f-1", "")     # empty session, previously collided to ''
    assert a != b
    assert c != d
    assert a.parent == tmp_path / "test_intakes"


def test_load_returns_fresh_when_no_file(tmp_path):
    sup = _MinimalSupervisor(data_dir=tmp_path)
    draft = sup._load("s-new", "f-1", "en-IN")
    assert draft == {
        "session_id": "s-new",
        "farmer_id": "f-1",
        "language": "en-IN",
        "draft": {},
    }


def test_save_and_reload_roundtrip(tmp_path):
    sup = _MinimalSupervisor(data_dir=tmp_path)
    draft = sup._fresh("s-1", "f-1", "en-IN")
    draft["draft"] = {"key": "value"}
    sup._save(draft)
    reloaded = sup._load("s-1", "f-1", "en-IN")
    assert reloaded["draft"] == {"key": "value"}


def test_before_save_hook_runs_under_the_file_lock(tmp_path):
    """AppointmentSupervisor uses _before_save to stamp updated_at. The hook
    must fire inside _save() -- verify a subclass override actually gets called."""
    seen = {}

    class Stamped(_MinimalSupervisor):
        def _before_save(self, draft):
            seen["called"] = True
            draft["stamped"] = "yes"

    sup = Stamped(data_dir=tmp_path)
    draft = sup._fresh("s-1", "f-1", "en-IN")
    sup._save(draft)
    assert seen == {"called": True}
    assert json.loads(sup._path("f-1", "s-1").read_text())["stamped"] == "yes"


def test_message_looks_up_localized_string_and_formats(tmp_path):
    sup = _MinimalSupervisor(data_dir=tmp_path)
    assert sup._message("en-IN", "hello", name="Asha") == "hi Asha"
    assert sup._message("hi-IN", "hello", name="Asha") == "नमस्ते Asha"


def test_message_falls_back_to_english_for_unknown_language(tmp_path):
    sup = _MinimalSupervisor(data_dir=tmp_path)
    assert sup._message("fr-FR", "hello", name="Asha") == "hi Asha", (
        "no French catalog entry -- must fall back to English, not KeyError"
    )


def test_message_missing_english_and_missing_language_raises_named_key(tmp_path):
    """Real risk (code review): the previous fallback `MESSAGES["en"]`
    would KeyError inside the request-handler path with a confusing
    'en'-not-found message if a subclass shipped only non-English
    catalogs. Now the missing-catalog case degrades to an empty catalog,
    so the final failure points at the specific missing key -- clearer
    diagnostic without hiding the real problem."""
    class HindiOnly(_MinimalSupervisor):
        MESSAGES = {"hi": {"hello": "नमस्ते {name}"}}

    sup = HindiOnly(data_dir=tmp_path)
    assert sup._message("hi-IN", "hello", name="Asha") == "नमस्ते Asha"
    with pytest.raises(KeyError, match="hello"):
        sup._message("fr-FR", "hello", name="Asha")


def test_session_lock_is_reentrant(tmp_path):
    """turn() may call self.confirm()/self.submit() on the same thread while
    already holding the session lock; a plain Lock would deadlock on that
    re-entry. The base uses RLock -- verify."""
    sup = _MinimalSupervisor(data_dir=tmp_path)
    lock = sup._session_lock("f-1", "s-1")
    with lock:
        with lock:  # would hang forever on a plain Lock
            assert True


def test_session_lock_scopes_are_distinct_per_farmer_and_session(tmp_path):
    sup = _MinimalSupervisor(data_dir=tmp_path)
    a = sup._session_lock("f-1", "s-1")
    b = sup._session_lock("f-1", "s-1")
    c = sup._session_lock("f-2", "s-1")
    assert a is b, "same (farmer, session) -> same lock instance"
    assert a is not c, "different farmer -> different lock"


def test_concurrent_saves_do_not_lose_transcript(tmp_path):
    """Same lost-update race the base class's _session_lock is meant to
    prevent, exercised directly against the base rather than through a subclass."""
    sup = _MinimalSupervisor(data_dir=tmp_path)
    sup._save(sup._fresh("s-1", "f-1", "en-IN"))
    counters = {"appended": 0}

    def append_one():
        with sup._session_lock("f-1", "s-1"):
            draft = sup._load("s-1", "f-1", "en-IN")
            draft["draft"].setdefault("items", []).append("x")
            sup._save(draft)
            counters["appended"] += 1

    threads = [threading.Thread(target=append_one) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()

    final = sup._load("s-1", "f-1", "en-IN")
    assert len(final["draft"]["items"]) == 10, "every concurrent append must survive"
