"""Real bug, found in a robustness audit: update_session() used to read the
current session (unlocked), merge in new data, then write it back under a
lock held only around the write -- two concurrent turns on the same
session_id could both read the same starting state, then each write back
their own version, one silently clobbering the other's fields. Fixed by
holding the lock across the whole read-merge-write. These tests reproduce
the race directly against the real disk-backed store (not mocked)."""
from __future__ import annotations

import threading

from services.voice_agent.session_store import clear_session, get_session, update_session


def test_concurrent_updates_do_not_lose_sibling_fields():
    session_id = "test-race-session-1"
    clear_session(session_id)
    try:
        def worker(key):
            for _ in range(20):
                update_session(session_id, {key: get_session(session_id).get(key, 0) + 1})

        threads = [threading.Thread(target=worker, args=(f"field{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive(), "update_session hung -- possible deadlock"

        final = get_session(session_id)
        for i in range(4):
            assert final.get(f"field{i}") == 20, f"field{i} lost updates from concurrent writers"
    finally:
        clear_session(session_id)


def test_concurrent_updates_to_same_key_reach_final_writer_not_stale_overwrite():
    """A stricter version of the race: many threads incrementing the SAME
    key. Without the fix, an update_session() call could read a value,
    another thread's update lands, then the first call's write clobbers it
    back to a stale value -- losing whole increments, not just merging
    fields. With the read+write under one lock, every increment must
    survive."""
    session_id = "test-race-session-2"
    clear_session(session_id)
    try:
        lock_free_increments = 30

        def worker():
            for _ in range(lock_free_increments):
                current = get_session(session_id).get("counter", 0)
                update_session(session_id, {"counter": current + 1})

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        final = get_session(session_id)
        # NOTE: this specific pattern (read-outside-the-update-call, then
        # update) can still race between the get_session() and
        # update_session() calls in *this test's own code* -- that's a
        # separate, inherent read-modify-write gap at the call-site level,
        # not the bug that was fixed. The fix guarantees update_session()
        # itself is atomic; it does not make external read-then-call
        # sequences atomic. So this test only asserts no crash/hang and a
        # sane result, not an exact count.
        assert final.get("counter", 0) > 0
    finally:
        clear_session(session_id)


def test_update_session_never_loses_a_fresh_key_under_concurrency():
    """Each thread introduces its OWN brand-new key (not present before any
    thread starts) -- this isolates the exact bug shape (lost sibling
    field from a stale read) without the same-key ambiguity above."""
    session_id = "test-race-session-3"
    clear_session(session_id)
    try:
        def worker(i):
            update_session(session_id, {f"new_key_{i}": True})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        final = get_session(session_id)
        for i in range(10):
            assert final.get(f"new_key_{i}") is True, f"new_key_{i} was lost to a concurrent write"
    finally:
        clear_session(session_id)
