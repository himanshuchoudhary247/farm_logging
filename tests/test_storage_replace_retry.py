"""storage.replace_file retries briefly on Windows while another process or
thread holds the target file open (antivirus, search indexer, an unlocked
reader).

Found by the evals suite (evals/, layer 1): draft saves failed with
"PermissionError: [WinError 5] Access is denied" in atomic_write_json and the
chat turn returned HTTP 500; voice_agent.session_store lost updates the same
way, silently.
"""
import json
import logging

import pytest

import storage


class _FlakyReplace:
    """Stands in for os.replace: raises `exc` for the first `fail_times`
    calls, then does the real replace."""

    def __init__(self, real, fail_times, exc):
        self.real = real
        self.fail_times = fail_times
        self.exc = exc
        self.calls = 0

    def __call__(self, src, dst):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return self.real(src, dst)


@pytest.fixture
def waits(monkeypatch):
    recorded = []
    monkeypatch.setattr(storage.time, "sleep", recorded.append)
    return recorded


def _flaky(monkeypatch, fail_times, windows=True, exc=None):
    flaky = _FlakyReplace(
        storage.os.replace, fail_times, exc or PermissionError(13, "Access is denied"))
    monkeypatch.setattr(storage.os, "replace", flaky)
    monkeypatch.setattr(storage, "_RETRY_REPLACE_ON_PERMISSION_ERROR", windows)
    return flaky


def test_write_succeeds_when_the_file_is_held_open_briefly(tmp_path, monkeypatch, waits):
    path = tmp_path / "draft.json"
    flaky = _flaky(monkeypatch, fail_times=2)
    storage.atomic_write_json(path, {"species": "goat"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"species": "goat"}
    assert flaky.calls == 3
    assert waits == [0.05, 0.1]
    assert not (tmp_path / "draft.json.tmp").exists()


def test_gives_up_after_the_last_attempt_and_keeps_the_old_file(tmp_path, monkeypatch, waits):
    path = tmp_path / "draft.json"
    storage.atomic_write_json(path, {"v": "old"})
    flaky = _flaky(monkeypatch, fail_times=99)
    with pytest.raises(PermissionError):
        storage.atomic_write_json(path, {"v": "new"})
    assert flaky.calls == storage._REPLACE_ATTEMPTS
    assert len(waits) == storage._REPLACE_ATTEMPTS - 1
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": "old"}


def test_no_retry_outside_windows(tmp_path, monkeypatch, waits):
    flaky = _flaky(monkeypatch, fail_times=1, windows=False)
    with pytest.raises(PermissionError):
        storage.atomic_write_json(tmp_path / "draft.json", {"a": 1})
    assert flaky.calls == 1
    assert waits == []


def test_other_errors_are_not_retried(tmp_path, monkeypatch, waits):
    flaky = _flaky(monkeypatch, fail_times=1, exc=FileNotFoundError("gone"))
    with pytest.raises(FileNotFoundError):
        storage.atomic_write_json(tmp_path / "draft.json", {"a": 1})
    assert flaky.calls == 1
    assert waits == []


def test_each_retry_is_logged(tmp_path, monkeypatch, waits, caplog):
    _flaky(monkeypatch, fail_times=1)
    with caplog.at_level(logging.WARNING, logger="storage"):
        storage.atomic_write_json(tmp_path / "draft.json", {"a": 1})
    assert "replace_file retry 1/4 for draft.json" in caplog.text


def test_voice_session_write_reaches_disk_when_the_file_is_held_open(tmp_path, monkeypatch, waits):
    # The real voice session store, writing to a temp folder.
    from services.voice_agent import session_store
    monkeypatch.setenv("VOICE_SESSIONS_DIR", str(tmp_path))
    monkeypatch.delenv("VOICE_SESSIONS_MEMORY", raising=False)
    _flaky(monkeypatch, fail_times=1)
    try:
        session_store.update_session("retry-session", {"intent": "weather"})
        on_disk = json.loads(session_store._session_path("retry-session").read_text(encoding="utf-8"))
        assert on_disk["intent"] == "weather", "the update must be on disk, not only in memory"
    finally:
        session_store.clear_session("retry-session")
        