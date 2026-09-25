# Conversation patterns: sticky routing

This note documents how the chat backend keeps a multi-turn conversation with
the right agent. Both patterns below are deliberate design choices, not bugs
or inconsistencies. Read this before adding a new agent or a new multi-turn
flow, so it reuses one of these patterns instead of inventing a third.

All routing lives in `route_turn_adk()` in
`services/chat_orchestrator/adk_router.py`.

## Why "sticky" routing exists

Every farmer message normally goes to an LLM classifier
(`_classify_intent_async`), which picks one of `appointment`, `add_animal`,
`weather`, or `query`. That works for a fresh request, but not for a short
follow-up reply. A bare "yes", "tomorrow morning", a breed name, or a PIN code
has no topic words in it, so the classifier would send it to the wrong place
(usually `query`, the fallback).

"Sticky" means: when a conversation is in the middle of something, the next
message skips the classifier and goes straight back to the agent that asked
the question.

## Routing order in `route_turn_adk()`

Checks run top to bottom; the first match wins.

1. Active appointment draft -> `appointment_supervisor` (Pattern 2)
2. Active animal registration draft -> `animal_registration` (Pattern 2)
3. Pending weather location follow-up -> weather (Pattern 1)
4. Otherwise -> LLM classifier decides

Consequences of this order:

- While any draft is active, the classifier never runs for that session.
- An active draft always outranks a pending weather follow-up.
- If a session somehow had both an appointment draft and a registration
  draft active, the appointment draft would win.

## Pattern 1: bounded sticky (one follow-up turn)

Used by: weather.

When to use: a single question with a single short answer, e.g. "Which PIN
code?" followed by "583101".

How it works:

- Stored as a flag in the voice session store
  (`services/voice_agent/session_store`, `get_session` / `update_session`),
  under the key built by `_weather_session_key()`:
  `"{farmer_id}:{session_id}:weather_pending"`.
- `_run_weather()` sets `awaiting_location = True` only when the weather
  result has `error == "no_location"`, and sets it back to `False` otherwise.
- On the next turn, `route_turn_adk()` clears the flag immediately and then
  calls `_run_weather(..., allow_rearm=False)`.

Why it is capped at exactly one turn: if the follow-up also fails (for
example two bad PIN codes in a row), `allow_rearm=False` stops the flag from
being set again, so the next message goes back to normal classification. The
farmer is never trapped in weather after they have moved on to something
else.

## Pattern 2: draft sticky (until the form is finished)

Used by: `appointment_supervisor`, `animal_registration`.

When to use: a form that needs several questions answered over many turns.

How it works:

- The "memory" is the agent's own draft file on disk (one file per
  farmer + session, path from the supervisor's `_path()`).
- `_has_active_booking_draft()` and `_has_active_registration_draft()` are
  cheap file checks with no LLM call. A draft counts as active when the file
  exists, its `state` is not `"CANCELLED"`, and `submitted` is not true.
- The flow stays sticky until the form is submitted or cancelled. After that
  the check returns false and the classifier takes over again.

Why cancel must end it too: without the `CANCELLED` check, a farmer who
cancelled would have every later message on that session routed back into
the finished form.

## Adding a new multi-turn flow

1. Decide which pattern fits:
   - One question, one short answer -> Pattern 1.
   - A form with several fields -> Pattern 2.
2. Add the sticky check in `route_turn_adk()` before the classifier call, and
   think about where it sits in the order above.
3. Make sure the flow stops being sticky on every way it can end (submitted,
   cancelled, and for Pattern 1, a second miss).
4. Add a test showing that a bare follow-up reply (no topic words) still
   reaches the right agent, and that the flow releases after it ends.

A future health-log flow collecting several fields would be Pattern 2.
