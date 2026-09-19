from __future__ import annotations

import pytest

from services.appointment_supervisor import service


def test_turn_confirm_and_submit_state_machine(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {
                "animal_identifier": "Lakshmi",
                "issue": "foot swelling",
                "date": "2026-08-25",
                "time": "11:30",
            }
        },
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "Lakshmi"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)

    first = supervisor.turn("demo-farmer", "session-1", "Lakshmi has foot swelling on August 25 at 11:30", "en-IN")
    assert first["state"] == "CONFIRMING"
    assert first["missing_fields"] == []

    with pytest.raises(ValueError, match="final confirmation"):
        supervisor.submit("demo-farmer", "session-1")

    ready = supervisor.confirm("demo-farmer", "session-1", "yes")
    assert ready["state"] == "READY_TO_SUBMIT"


def test_correction_keeps_draft_open(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_identifier": "Lakshmi", "issue": "fever"}},
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "Lakshmi"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-2", "Lakshmi has fever", "hi-IN")
    corrected = supervisor.confirm("demo-farmer", "session-2", "no")

    assert corrected["state"] == "CORRECTING"
    assert corrected["response_text"]
    assert corrected["language"] == "hi-IN"


def test_hindi_turn_uses_llm_extracted_entities(tmp_path, monkeypatch):
    """No regex fallback exists — process_text_input (backed by call_bedrock)
    is the only source of entities for any language, including Hindi."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {
                "animal_name": "सीमा",
                "issue": "lethargy",
                "symptoms": ["lethargy", "not eating"],
            }
        },
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "सीमा"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)

    result = supervisor.turn(
        "demo-farmer",
        "session-hi",
        "इसका नाम सीमा है इसके खाना पीना बंद कर दिया सोई सोई रही है",
        "hi-IN",
    )

    assert result["draft"]["animal_name"] == "सीमा"
    assert result["draft"]["issue"] == "lethargy"
    assert "not eating" in result["draft"]["symptoms"]


def test_bare_reply_to_targeted_field_question_is_wired_as_context(tmp_path, monkeypatch):
    """Real bug: a bare reply ("1122") to the bot's own "please provide the
    animal tag/ID" question kept landing in issue/symptoms instead, because
    appointment_supervisor never told the extraction call which field it
    had just asked about. Fix: pending_questions_override carries that
    context into process_text_input every turn a specific field is
    expected. This test asserts the wiring, not the real model's behavior
    (that's covered by wiring the pending_questions param through, and by
    the real extraction system prompt's own examples)."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    seen_pending = []

    def fake_process_text_input(text, session_id, pending_questions_override=None):
        seen_pending.append(pending_questions_override)
        if pending_questions_override and "animal ID" in pending_questions_override[0]:
            return {"entities": {"animal_tag": text.strip()}}
        return {"entities": {}}

    monkeypatch.setattr(service, "process_text_input", fake_process_text_input)
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "1122"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)

    first = supervisor.turn("demo-farmer", "session-bare", "I want to report symptoms", "en-IN")
    assert first["missing_fields"] == ["animal_identifier", "issue", "date", "time"]

    second = supervisor.turn("demo-farmer", "session-bare", "1122", "en-IN")
    # animal_tag must bridge into animal_identifier (the field REQUIRED_FIELDS
    # actually checks) -- a correctly-extracted tag that never bridges is
    # the same user-visible failure as extraction guessing the wrong field.
    assert second["draft"]["animal_identifier"] == "1122"
    assert "animal_identifier" not in second["missing_fields"]


def test_animal_tag_bridges_to_animal_identifier(tmp_path, monkeypatch):
    """_copy_entities must accept either animal_tag (bare ear-tag/ID number,
    the extraction schema's field for exactly this) or animal_name -- only
    bridging animal_name was a real bug: a correctly-extracted tag number
    silently never counted as having answered the question."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_tag": "1122"}},
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "1122"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)
    result = supervisor.turn("demo-farmer", "session-tag", "1122", "en-IN")
    assert result["draft"]["animal_identifier"] == "1122"


def test_unchanged_extraction_reasks_targeted_field_not_full_welcome(tmp_path, monkeypatch):
    """Real bug: once anything had been collected, a turn where extraction
    found nothing new re-sent the full 4-field "Hello, please tell me..."
    welcome, discarding what was already known -- looked like the bot
    forgot the whole conversation. Fix: re-ask only the specific field
    still missing once something has been collected; full welcome is only
    for a truly empty draft."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_identifier": "Lakshmi"}},
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "Lakshmi"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-reask", "Lakshmi", "en-IN")

    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}},
    )
    second = supervisor.turn("demo-farmer", "session-reask", "bro you dont understand my intent at all", "en-IN")
    assert "Hello. Please tell me the animal name" not in second["response_text"]
    assert second["draft"]["animal_identifier"] == "Lakshmi"


def test_confirmation_classified_by_signal_not_keyword_substring(tmp_path, monkeypatch):
    """Real bug: the old _response_kind() did naive substring matching --
    "no" in "enough" is True -- so an ordinary sentence containing "enough"
    got misclassified as a rejection and derailed the flow into
    CORRECTING. Fix: classification now comes from confirmation_signal on
    the same extraction call (which sees full sentence meaning), not
    Python keyword matching. This test asserts turn() reads
    confirmation_signal from the mocked extraction result rather than
    re-deriving it from the text itself."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {
                "animal_identifier": "Lakshmi", "issue": "foot swelling",
                "date": "2026-08-25", "time": "11:30",
            }
        },
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "Lakshmi"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)
    first = supervisor.turn("demo-farmer", "session-confirm-signal", "Lakshmi foot swelling Aug 25 11:30", "en-IN")
    assert first["state"] == "CONFIRMING"

    # Now mid-CONFIRMING: a sentence containing "enough" that actually
    # means "no" -- confirmation_signal says so explicitly, unlike a
    # keyword scan of the raw text which would misfire on "enough".
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "no"},
    )
    corrected = supervisor.turn("demo-farmer", "session-confirm-signal", "that's wrong, arnt you smart enough", "en-IN")
    assert corrected["state"] == "CORRECTING"


def test_yes_at_ready_to_submit_actually_submits(tmp_path, monkeypatch):
    """Real infinite-loop bug, found via live user testing: at
    READY_TO_SUBMIT, saying "yes" is the natural way to consent, and the
    model correctly reports confirmation_signal="yes" (the farmer's literal
    word), not the separate enum value "submit". Routing only matched
    "submit" -- "yes" fell through unmatched, regressed state back to
    CONFIRMING, and the next turn's follow-up bounced it back to
    READY_TO_SUBMIT via confirm()'s own "yes" handling, forever, never once
    calling submit()."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {
                "animal_identifier": "1122", "issue": "not eating",
                "date": "2026-09-20", "time": "17:00",
            }
        },
    )
    fake_animal = type("Animal", (), {"id": "1122", "tag_or_name": "1122"})()
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [fake_animal])
    monkeypatch.setattr(service, "append_health_log", lambda *a, **k: type("H", (), {"id": "h-1", "model_dump": lambda self: {"id": "h-1"}})())
    monkeypatch.setattr(service, "append_appointment", lambda *a, **k: type("A", (), {"id": "a-1", "model_dump": lambda self: {"id": "a-1"}})())
    monkeypatch.setattr(service, "append_ai_health_log", lambda **k: None)
    monkeypatch.setattr(
        service, "generate_health_recommendation",
        lambda **k: {"diagnosis_suggestion": "", "potential_ailments": [], "first_aid_advice": ""},
    )
    monkeypatch.setattr(service.flokiq_sync, "create_health_log", lambda **k: None)
    monkeypatch.setattr(service.flokiq_sync, "create_appointment", lambda **k: None)

    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-loop", "1122, not eating, tomorrow 5pm", "en-IN")

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "yes"},
    )
    ready = supervisor.turn("demo-farmer", "session-loop", "cool", "en-IN")
    assert ready["state"] == "READY_TO_SUBMIT"

    result = supervisor.turn("demo-farmer", "session-loop", "yes", "en-IN")
    assert result.get("status") == "submitted", f"expected submit() to fire, got: {result}"


def test_animal_not_found_loops_back_instead_of_raising(tmp_path, monkeypatch):
    """Real bug: the animal was only ever checked at the very end, inside
    submit() -- a raw ValueError there became a dead-end HTTP 400 with no
    way to recover. Now the animal is verified the moment it's given,
    immediately in turn(), not deferred to submit() at all -- catching a
    wrong identifier right away instead of after the farmer has also
    given issue/date/time and confirmed everything."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {
                "animal_identifier": "9999", "issue": "fever",
                "date": "2026-09-20", "time": "17:00",
            }
        },
    )
    real_animal = type("Animal", (), {"id": "a-1", "tag_or_name": "GAURI"})()
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [real_animal])
    # "9999" genuinely doesn't fuzzy-match "GAURI" -- assert that
    # deterministically rather than relying on a real (network, credential-
    # dependent) Bedrock call inside a unit test.
    monkeypatch.setattr(service, "_resolve_animal_id", lambda wanted, animals: (None, []))

    supervisor = service.AppointmentSupervisor(tmp_path)
    result = supervisor.turn("demo-farmer", "session-notfound", "9999, fever, tomorrow 5pm", "en-IN")

    assert result.get("status") != "submitted", "must not submit when the animal doesn't match"
    assert result["state"] == "COLLECTING"
    assert result["draft"].get("animal_identifier") is None
    assert "GAURI" in result["response_text"]
    assert "9999" in result["response_text"]
    assert result["options"]["choices"] == ["GAURI"]
    assert result["options"]["other_allowed"] is True


def test_fuzzy_animal_match_resolves_typo_and_submits(tmp_path, monkeypatch):
    """Real bug: exact-match-only lookup (wanted in {id, tag_or_name}) gave
    up instantly on anything not byte-identical to a stored string -- a
    farmer's reasonable guess ("tag 001" after being told real tags look
    like "TAG-001-1") or a plain typo had no path to success. Now falls
    back to _resolve_animal_id (an LLM match against the real animal list)
    when the exact match fails. This test asserts the wiring -- that a
    successful fuzzy match actually lets submit() proceed -- using a mock
    resolver rather than a real Bedrock call."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {
                "animal_identifier": "GARI", "issue": "fever",
                "date": "2026-09-20", "time": "17:00",
            }
        },
    )
    real_animal = type("Animal", (), {"id": "a-1", "tag_or_name": "GAURI"})()
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [real_animal])
    monkeypatch.setattr(service, "_resolve_animal_id", lambda wanted, animals: ("a-1", []) if wanted == "GARI" else (None, []))
    monkeypatch.setattr(service, "append_health_log", lambda *a, **k: type("H", (), {"id": "h-1", "model_dump": lambda self: {"id": "h-1"}})())
    monkeypatch.setattr(service, "append_appointment", lambda *a, **k: type("A", (), {"id": "a-1", "model_dump": lambda self: {"id": "a-1"}})())
    monkeypatch.setattr(service, "append_ai_health_log", lambda **k: None)
    monkeypatch.setattr(
        service, "generate_health_recommendation",
        lambda **k: {"diagnosis_suggestion": "", "potential_ailments": [], "first_aid_advice": ""},
    )
    monkeypatch.setattr(service.flokiq_sync, "create_health_log", lambda **k: None)
    monkeypatch.setattr(service.flokiq_sync, "create_appointment", lambda **k: None)

    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-fuzzy", "GARI, fever, tomorrow 5pm", "en-IN")

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "yes"},
    )
    supervisor.turn("demo-farmer", "session-fuzzy", "cool", "en-IN")
    result = supervisor.turn("demo-farmer", "session-fuzzy", "yes", "en-IN")
    assert result.get("status") == "submitted", f"expected fuzzy-matched submit to succeed, got: {result}"


def test_ambiguous_match_shows_shortlist_not_entire_herd(tmp_path, monkeypatch):
    """When _resolve_animal_id can't pick one specific animal but flags a
    handful of plausible candidates (e.g. several tags sharing a prefix
    fragment), the not-found message should list only those candidates --
    asking the farmer to pick between 3 real possibilities is useful,
    asking them to scan an entire 50-animal herd is not."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service,
        "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {
                "animal_identifier": "001", "issue": "fever",
                "date": "2026-09-20", "time": "17:00",
            }
        },
    )
    animals = [
        type("Animal", (), {"id": "a-1", "tag_or_name": "TAG-001-1"})(),
        type("Animal", (), {"id": "a-2", "tag_or_name": "TAG-001-2"})(),
        type("Animal", (), {"id": "a-3", "tag_or_name": "OTHER-999"})(),
    ]
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: animals)
    monkeypatch.setattr(service, "_resolve_animal_id", lambda wanted, animals: (None, ["a-1", "a-2"]))

    supervisor = service.AppointmentSupervisor(tmp_path)
    result = supervisor.turn("demo-farmer", "session-ambiguous", "001, fever, tomorrow 5pm", "en-IN")

    assert "TAG-001-1" in result["response_text"]
    assert "TAG-001-2" in result["response_text"]
    assert "OTHER-999" not in result["response_text"], "shortlist must narrow, not show the whole herd"
    assert result["options"]["choices"] == ["TAG-001-1", "TAG-001-2"]


def test_cancel_honored_during_collecting(tmp_path, monkeypatch):
    """Real bug: confirmation_signal=="cancel" was only ever checked in
    awaiting_confirmation/READY_TO_SUBMIT -- a farmer saying "cancel"/
    "never mind" mid-collection (the normal state for most of a booking)
    had no way to abandon it, silently discarded."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_identifier": "Lakshmi"}},
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "Lakshmi"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-cancel", "Lakshmi", "en-IN")

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "cancel"},
    )
    result = supervisor.turn("demo-farmer", "session-cancel", "never mind, cancel this", "en-IN")
    assert result["state"] == "CANCELLED"


def test_cancelled_draft_resets_on_next_message_not_resurrected(tmp_path, monkeypatch):
    """Real bug: CANCELLED was never actually terminal -- no code cleared
    the draft body or set submitted=True, so any further message on that
    session fell through the generic path and could walk the old,
    supposedly-cancelled booking data straight back to CONFIRMING/
    READY_TO_SUBMIT as if it had never been cancelled."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {"animal_identifier": "Lakshmi", "issue": "fever", "date": "2026-09-20", "time": "17:00"},
        },
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "Lakshmi"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-cancelled-reset", "Lakshmi fever tomorrow 5pm", "en-IN")

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "cancel"},
    )
    cancelled = supervisor.turn("demo-farmer", "session-cancelled-reset", "cancel", "en-IN")
    assert cancelled["state"] == "CANCELLED"

    # confirm() must refuse a stray "yes" on the still-cancelled draft
    # (before any subsequent turn() call has a chance to reset it) --
    # this is the direct-call path turn()'s own reset-on-entry can't cover.
    with pytest.raises(ValueError, match="cancelled"):
        supervisor.confirm("demo-farmer", "session-cancelled-reset", "yes")

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}},
    )
    result = supervisor.turn("demo-farmer", "session-cancelled-reset", "hello again", "en-IN")
    assert result["state"] != "READY_TO_SUBMIT"
    assert result["draft"].get("animal_identifier") is None, "old cancelled booking data must not resurface"


def test_no_at_ready_to_submit_goes_to_correcting_not_animal_wipe(tmp_path, monkeypatch):
    """Real bug: a bare "no" answering "would you like to submit?" had no
    dedicated branch, so it fell through to the generic animal-verified-
    reset check, which ALWAYS evaluates true at READY_TO_SUBMIT (every
    required field present by construction) -- wiping the correct,
    already-verified animal even if the objection was about something
    else entirely."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {"animal_identifier": "Lakshmi", "issue": "fever", "date": "2026-09-20", "time": "17:00"},
        },
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "Lakshmi"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-ready-no", "Lakshmi fever tomorrow 5pm", "en-IN")

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "yes"},
    )
    ready = supervisor.turn("demo-farmer", "session-ready-no", "cool", "en-IN")
    assert ready["state"] == "READY_TO_SUBMIT"

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "no"},
    )
    result = supervisor.turn("demo-farmer", "session-ready-no", "no", "en-IN")
    assert result["state"] == "CORRECTING"
    assert result["draft"].get("animal_identifier") == "Lakshmi", "animal must survive a 'no' at READY_TO_SUBMIT"


def test_cancel_clears_router_session_cache_immediately(tmp_path, monkeypatch):
    """Real bug, found live: clearing the session cache only reactively (on
    the NEXT turn's entry, when it sees a pre-existing CANCELLED state) is
    one turn too late. chat_orchestrator.route_turn() runs its OWN
    classification call (session key f"{farmer_id}:{session_id}:route")
    BEFORE it ever calls back into appointment_supervisor.turn() on that
    next turn -- so an unrelated question right after cancelling (e.g. a
    weather question) got classified using the stale cached
    CREATE_APPOINTMENT intent from before the cancel, and the booking flow
    swallowed it. Must clear at the moment of cancelling. This test asserts
    clear_session is actually called with the router's :route-suffixed key,
    not just appointment_supervisor's own -- live end-to-end coverage of
    the full leak is in the manual verification steps for this fix."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_identifier": "Lakshmi"}},
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "Lakshmi"})()])
    cleared_keys = []
    monkeypatch.setattr(service, "clear_session", lambda key: cleared_keys.append(key))

    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-cancel-clear", "Lakshmi", "en-IN")

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "cancel"},
    )
    supervisor.turn("demo-farmer", "session-cancel-clear", "cancel", "en-IN")

    assert "demo-farmer:session-cancel-clear" in cleared_keys
    assert "demo-farmer:session-cancel-clear:route" in cleared_keys, "router's own classification cache must be cleared too, at cancel time"


def test_session_path_is_scoped_by_farmer_not_just_session_id(tmp_path, monkeypatch):
    """Real bug, found in a robustness audit: the old path scheme
    (''.join(ch for ch in session_id if ch.isalnum() or ch in '-_')) was
    farmer-unscoped and collision-prone -- two different farmers reusing
    (or guessing) the same session_id shared one draft file, and a bare
    '' (from an empty/emoji-only session_id) collapsed to one single
    global file across every farmer. Assert the same session_id string
    used by two different farmers resolves to two different files with
    no cross-contamination."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-1", "tag_or_name": "GAURI"})()])

    supervisor = service.AppointmentSupervisor(tmp_path)
    shared_sid = "shared-session-xyz"

    path_a = supervisor._path("farmer-a", shared_sid)
    path_b = supervisor._path("farmer-b", shared_sid)
    assert path_a != path_b, "same session_id from two farmers must not resolve to the same file"

    # Farmer A actually collects a real animal; farmer B's turn extracts
    # nothing at all -- isolates the file-separation question from the
    # mocked extraction call, which would otherwise return the same
    # canned entities for both farmers regardless of any file leak.
    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_identifier": "GAURI"}},
    )
    supervisor.turn("farmer-a", shared_sid, "GAURI", "en-IN")

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}},
    )
    result_b = supervisor.turn("farmer-b", shared_sid, "hello", "en-IN")
    assert result_b["draft"].get("animal_identifier") is None, "farmer B must not see farmer A's draft data"


def test_zero_animals_gets_honest_message_not_nonsense_fallback(tmp_path, monkeypatch):
    """Real bug, found in a robustness audit: with animals_for_farmer()
    == [], ", ".join(...) on an empty list is "" (falsy), so the message
    fell back to the literal field-label string, producing a nonsensical
    "...your registered animals are: the animal name, tag, or ID..." for a
    farmer who genuinely has none yet. Should say so honestly instead."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_identifier": "GAURI"}},
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [])
    supervisor = service.AppointmentSupervisor(tmp_path)
    result = supervisor.turn("farmer-no-animals", "session-zero", "GAURI", "en-IN")
    assert "the animal name, tag, or ID" not in result["response_text"], "must not fall back to the field-label string"
    assert "no" in result["response_text"].lower() or "not" in result["response_text"].lower() or "any" in result["response_text"].lower()


def test_wrong_tag_after_auto_verify_resets_animal(tmp_path, monkeypatch):
    """Real bug, found live: once the animal auto-verifies (matched
    immediately when given, not deferred to submit()), the flow moves
    straight to asking for the next field and never again asks "is this
    the right animal?" -- so a farmer who says "wrong tag" right after
    (while still COLLECTING the issue/date/time, nowhere near
    awaiting_confirmation or READY_TO_SUBMIT) had no way to be heard.
    Exact conversation that surfaced this: "TAG-001-11" auto-verified,
    then farmer said "wrong tag" and the flow just kept asking for the
    date as if nothing had been said."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_identifier": "TAG-001-11"}},
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [type("Animal", (), {"id": "a-11", "tag_or_name": "TAG-001-11"})()])
    supervisor = service.AppointmentSupervisor(tmp_path)
    first = supervisor.turn("demo-farmer", "session-wrong-tag", "TAG-001-11", "en-IN")
    assert first["draft"].get("animal_identifier") == "TAG-001-11"
    # state=="CONFIRMING" here is the overloaded targeted-follow-up sense
    # (expected_field set to the next missing field, e.g. "issue"), not a
    # literal yes/no confirmation -- that distinction is what the real bug
    # exploited: this state never re-asked about the animal itself.
    loaded = supervisor._load("session-wrong-tag", "demo-farmer", "en-IN")
    assert loaded.get("animal_verified") is True
    assert loaded.get("expected_field") == "issue"

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "no"},
    )
    corrected = supervisor.turn("demo-farmer", "session-wrong-tag", "wrong tag", "en-IN")
    assert corrected["draft"].get("animal_identifier") is None, "the wrong tag must be cleared, not silently kept"
    assert corrected["state"] == "COLLECTING"


def test_answers_expected_field_recognizes_raw_animal_keys(tmp_path, monkeypatch):
    """Real bug, found in a robustness audit: expected_field is set to the
    merged key "animal_identifier", but the raw extraction schema never
    emits that key directly -- it emits animal_id/animal_tag/animal_name.
    So whenever expected_field=="animal_identifier", answers_expected_field
    always evaluated False even when the farmer's turn genuinely named an
    animal. Reproduced here via the one path where that combination is
    reachable: animal_verified already True (from a prior animal) while
    expected_field is manually pinned back to "animal_identifier" -- a
    farmer naming a second, different, real animal in the same breath as
    "no" must re-verify to the new one in this turn, not get wiped back to
    a blank "which animal?" question by the wrong-tag-reset branch."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    animals = [
        type("Animal", (), {"id": "a-gauri", "tag_or_name": "Gauri"})(),
        type("Animal", (), {"id": "a-lakshmi", "tag_or_name": "Lakshmi"})(),
    ]
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: animals)
    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {"animal_identifier": "Gauri"}},
    )
    supervisor = service.AppointmentSupervisor(tmp_path)
    supervisor.turn("demo-farmer", "session-answers-field", "Gauri", "en-IN")
    draft = supervisor._load("session-answers-field", "demo-farmer", "en-IN")
    assert draft.get("animal_verified") is True
    draft["expected_field"] = "animal_identifier"
    supervisor._save(draft)

    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {
            "entities": {"animal_tag": "Lakshmi"}, "confirmation_signal": "no",
        },
    )
    result = supervisor.turn("demo-farmer", "session-answers-field", "no, it's Lakshmi", "en-IN")
    # With the fix: recognized as answering the animal question, so it
    # re-verifies to Lakshmi in this same turn instead of the wrong-tag-
    # reset branch wiping it back to None and asking again from scratch.
    assert result["draft"].get("animal_identifier") == "Lakshmi"


def test_concurrent_turns_do_not_lose_transcript_entries(tmp_path, monkeypatch):
    """Real bug, found in a robustness audit: turn() read the draft
    unlocked, ran the extraction call, then wrote back under a lock held
    only around the write -- two concurrent turns on the same session_id
    could both read the same starting draft and each write back their own
    version, one clobbering the other's transcript entry. Fixed by holding
    a per-session RLock across the whole call."""
    import threading
    import time

    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    call_count = [0]
    count_lock = threading.Lock()

    def fake_process_text_input(text, session_id, pending_questions_override=None):
        with count_lock:
            call_count[0] += 1
            n = call_count[0]
        time.sleep(0.02)
        return {"entities": {"issue": f"issue-{n}"}}

    monkeypatch.setattr(service, "process_text_input", fake_process_text_input)
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [])
    supervisor = service.AppointmentSupervisor(tmp_path)

    threads = [
        threading.Thread(target=supervisor.turn, args=("demo-farmer", "session-concurrent", "cow is sick"), kwargs={"include_audio": False})
        for _ in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive(), "a turn() call hung -- possible deadlock"

    draft = supervisor._load("session-concurrent", "demo-farmer", "en-IN")
    assert len(draft.get("transcript_history", [])) == 5, "every concurrent turn's transcript entry must survive"


def test_turn_reentrant_into_confirm_does_not_deadlock(tmp_path, monkeypatch):
    """The per-session RLock added to fix the concurrent lost-update race
    must be reentrant: turn() calls self.confirm() on the same thread in
    several branches (e.g. the universal "cancel" check). A plain Lock
    here would deadlock the very first cancel."""
    monkeypatch.setattr(service, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(
        service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": "cancel"},
    )
    monkeypatch.setattr(service, "animals_for_farmer", lambda farmer_id: [])
    supervisor = service.AppointmentSupervisor(tmp_path)
    result = supervisor.turn("demo-farmer", "session-reentrant", "never mind", include_audio=False)
    assert result["state"] == "CANCELLED"
