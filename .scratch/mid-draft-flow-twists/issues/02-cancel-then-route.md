# 02: After a cancel, a question in the same message still gets answered

**What to build:** "cancel my booking, how many cows do I have" cancels
the booking *and* answers the count -- today the cancel happens but the
trailing question is dropped. Also: "forget this, start again -- MOTI is
limping, vet tomorrow" cancels the old booking and starts a *new* one from
the same message, instead of requiring a second turn.

**Blocked by:** None (can start immediately) -- deliberately deferred out
of the farm_logging PR #71/#73 cleanup this ticket came from (see
Context), since it needs real design work against this repo's current
mid-draft-escape architecture, not a mechanical port.

**Status:** ready-for-agent

## Context (found during the #71/#73 cleanup, verified against real code)

Same background as ticket 01 (PR #71's side-question mechanism dropped in
favor of #72's `mid_draft_escape.py`, already merged). PR #73 (`feat/
evals-layer4`) added cancel-then-route handling on top of #71's loop,
built across three commits, each fixing a real bug found live:

- `b4afc9e`: after a booking is cancelled, a question in the same message
  ("cancel the booking and tell me how many cows I have") used to be
  dropped entirely -- the classifier often names the cancelled flow itself
  when a question rides along in the same message (seen in hi/ta/te).
  Also added `_has_booking_details(text)` (`services/chat_orchestrator/
  adk_router.py`): a message classified as "appointment" after a cancel
  only starts a *new* booking when it actually carries booking details
  (animal/problem/date/time) -- a bare "no, cancel it" was starting an
  empty new booking.
- `359461f`: a *plain* cancel with no real question ("cancel") was getting
  a made-up answer from the query-agent probe ("you have 53 animals") in
  ~1 of 3 runs -- the probe's prompt now explicitly tells the model the
  farmer just cancelled, to answer only a real question in the rest of the
  message, and reply a sentinel (dropped) otherwise.
- `7c927b7`: the post-cancel question probe was running inside the chat's
  *real* query-agent session, so the cancel text itself polluted the
  session's memory and the next real question got answered against stale
  context (a goat was called a cow after this). Fixed by running the probe
  on a disposable session, same pattern #71's own side-question probe used.

All three live in `_route_after_cancel()` (`services/chat_orchestrator/
adk_router.py`), called from directly inside the side-question loop
(`for agent, flow_intent, supervisor, has_draft in (...)`) that no longer
exists on `dev` -- `result.get("state") == "CANCELLED"` is checked right
after `supervisor.turn(..., side_question=side_question)` returns, and
`_route_after_cancel` reaches into that same loop's `agent`/`flow_intent`/
`_allowed` closures. Not portable as a standalone function; the call site
it hooks into is gone.

## What to build, this time against the current sticky-routing shape

1. The actual cancel detection (`result.get("state") == "CANCELLED"` right
   after `supervisor.confirm(..., "cancel", ...)`/`turn()` returns a
   cancelled draft) doesn't need the dropped loop -- `route_turn_adk`
   already knows when a turn resulted in a cancel, in the sticky-routing
   branch for each supervisor. The question-in-the-same-message check can
   likely hook in right there instead.
2. Port `_has_booking_details()` as-is -- it's a small, self-contained
   helper (`services/voice_agent/orchestrator.py`'s `process_text_input`
   on a throwaway session, checking for animal/problem/date/time) with no
   dependency on the dropped loop.
3. Port the query-agent-probe refinements (disposable session, "just
   cancelled, only answer a real question" prompt framing, appointment-
   data exclusion so the cancel confirmation itself isn't mistaken for an
   answer) -- these are sound fixes to a probe pattern, reusable regardless
   of what calls it.
4. New design needed: the actual *trigger and call site* for all of this,
   now living inside whichever cancel-handling code path
   `appointment_supervisor`/`animal_registration` already have, composed
   with `_try_mid_draft_escape` rather than a separate loop.

- [ ] Design: trigger point for "check for a trailing question" after a
      cancel, in the current (non-loop) `route_turn_adk` structure
- [ ] Port `_has_booking_details()` verbatim
- [ ] Port the disposable-session + cancel-aware-prompt probe refinements
- [ ] Regression tests: plain cancel answered correctly (no made-up data),
      cancel+question answered for real, cancel+new-booking-details starts
      a fresh booking from the same message, a bare "no, cancel it" does
      NOT start an empty booking
- [ ] Full suite green, both with and without AWS credentials
