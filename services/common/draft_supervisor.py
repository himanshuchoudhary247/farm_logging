"""Shared base class for file-backed, multi-turn draft supervisors.

Two now-live supervisors -- AppointmentSupervisor and
AnimalRegistrationSupervisor -- had hand-duplicated the same machinery:
the sha1-hashed per-(farmer, session) draft path, the FileLock-guarded
atomic write, the load-or-fresh helper, the per-session RLock dict,
the 5-language SUPPORTED_LANGUAGES map, the _lang() language-tag helper,
the _UNSET sentinel, and the small dispatch that wraps turn/confirm/submit
under _session_lock(). docs/conversation_patterns.md anticipates a third
supervisor (health-log) using the same pattern; extracting this base now
prevents the third copy-paste and gives the two existing subclasses a
single, tested implementation of the shared machinery.

Deliberately NOT hoisted into the base: _fresh() (each supervisor has a
different draft schema), _summary() (different label dicts and field-order
rules), _response() (appointment's has extra options/prompt parameters
animal_registration doesn't need), turn()/confirm()/submit() (domain logic).
_message() IS hoisted -- both subclasses had byte-identical bodies, so the
base reads from a MESSAGES class attribute each subclass provides.

The _path()/_load()/_save() bodies here are copied byte-for-byte from
AppointmentSupervisor's own audit-hardened versions (see the historical
comments in _path and _session_lock -- both refer to real bugs found in
this session's robustness audit that the fix was applied to; keeping the
context so a future reader knows why the hashing/locking looks the way
it does).
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

from filelock import FileLock

from storage import atomic_write_json, get_data_dir


SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "kn-IN": "Kannada",
}

# Sentinel distinguishing "caller didn't pass this optional arg, use the
# default" from an explicit None (which some subclasses treat as a real
# semantic value -- e.g. prompt=None on _response means "no separate prompt
# text this turn," which is a real state, not the same as "not provided").
_UNSET: Any = object()


def _lang(language: str) -> str:
    """Normalize an IETF-like language tag to its lowercase primary subtag."""
    return (language or "en-IN").split("-")[0].lower()


class DraftSupervisor:
    """Base machinery for a file-backed, per-(farmer, session) multi-turn
    draft supervisor. Subclasses must supply:
      * `INTAKE_SUBDIR`: directory name under data/ for this supervisor's drafts.
      * `MESSAGES`: nested dict {lang_prefix: {key: str}} for `_message()`.
      * `_fresh(session_id, farmer_id, language) -> dict`: the initial draft
        shape for that domain.
    """

    INTAKE_SUBDIR: ClassVar[str] = ""
    MESSAGES: ClassVar[Dict[str, Dict[str, str]]] = {}

    def __init__(self, data_dir: Path | None = None) -> None:
        if not self.INTAKE_SUBDIR:
            raise NotImplementedError(
                f"{type(self).__name__} must set INTAKE_SUBDIR"
            )
        self.data_dir = data_dir or get_data_dir()
        self.intake_dir = self.data_dir / self.INTAKE_SUBDIR
        # Real bug, found in a robustness audit: turn()/confirm()/submit()
        # each read the draft (unlocked), did real work -- including, in
        # turn(), the extraction LLM call -- then wrote it back under a lock
        # held only around the write itself. Two concurrent requests for the
        # same session_id could both read the same starting draft and each
        # write back their own version, one silently clobbering the other's
        # fields (no corruption, just dropped entities/transcript). Fixed by
        # holding a per-session RLock across the entire call, not just the
        # write. RLock (not Lock) because turn() may call self.confirm()/
        # self.submit() internally on the same thread -- a plain Lock would
        # deadlock on that re-entry.
        self._session_locks: dict[str, threading.RLock] = {}
        self._session_locks_guard = threading.Lock()

    def _session_lock(self, farmer_id: str, session_id: str) -> threading.RLock:
        digest = hashlib.sha1(f"{farmer_id}:{session_id}".encode("utf-8")).hexdigest()
        with self._session_locks_guard:
            return self._session_locks.setdefault(digest, threading.RLock())

    def _path(self, farmer_id: str, session_id: str) -> Path:
        # Real bug, found in a robustness audit: the old scheme
        # (''.join(ch for ch in session_id if ch.isalnum() or ch in '-_'))
        # was farmer-unscoped and collision-prone -- "", "!!!", and any
        # emoji-only session_id all strip to "" (every such session shares
        # ONE global draft file, across ALL farmers), and distinct ids like
        # "ab-c"/"a@b/c" both collide to "abc". Worse, nothing checked
        # draft["farmer_id"] against the caller's farmer_id, so farmer A
        # could read farmer B's in-progress booking by guessing/reusing a
        # session id. Hash farmer_id+session_id together instead, same
        # pattern services/voice_agent/session_store.py already uses
        # correctly for the parallel per-turn entity cache.
        digest = hashlib.sha1(f"{farmer_id}:{session_id}".encode("utf-8")).hexdigest()
        return self.intake_dir / f"{digest}.json"

    def _fresh(self, session_id: str, farmer_id: str, language: str) -> dict[str, Any]:
        raise NotImplementedError

    def _load(self, session_id: str, farmer_id: str, language: str) -> dict[str, Any]:
        path = self._path(farmer_id, session_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return self._fresh(session_id, farmer_id, language)

    def _before_save(self, draft: dict[str, Any]) -> None:
        """Hook: subclasses override to stamp per-save fields (e.g. updated_at).
        Default is a no-op."""
        return None

    def _save(self, draft: dict[str, Any]) -> None:
        path = self._path(draft["farmer_id"], draft["session_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock"):
            self._before_save(draft)
            atomic_write_json(path, draft)

    def _message(self, language: str, key: str, **values: str) -> str:
        catalog = self.MESSAGES.get(_lang(language), self.MESSAGES["en"])
        return catalog[key].format(**values)
