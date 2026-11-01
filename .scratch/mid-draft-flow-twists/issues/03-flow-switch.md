# 03: Switching flows mid-draft (booking <-> registration)

**What to build:** mid-booking, "actually, leave that -- register a new
goat for me" closes the open booking (unsaved) and starts a registration
from the same message, instead of the booking just re-asking its own
question. The reverse (mid-registration, a real booking request) works
the same way.

**Blocked by:** None (can start immediately) -- deliberately deferred out
of the farm_logging PR #71/#73 cleanup this ticket came from (see
Context), since it needs real design work against this repo's current
mid-draft-escape architecture, not a mechanical port.

**Status:** ready-for-agent

## Context (found during the #71/#73 cleanup, verified against real code)

Same background as tickets 01/02. PR #73 (`feat/evals-layer4`, commit
`47101cb`) added flow-switching on top of PR #71's now-dropped
side-question loop, found live in all 7 languages: a booking request
mid-registration (or the reverse) just got the open flow's own question
re-asked, with the farmer's actual request silently ignored.

Mechanically, `_side_question_label()` (`services/chat_orchestrator/
adk_router.py`) was extended so the classifier's result can be
`"appointment"`/`"add_animal"` (the *other* flow), not just `"weather"`/
`"query"` -- gated by `CHAT_FLOW_SWITCH`. Each supervisor's `turn()`
(already receiving the `side_question` callback for ticket 01/02's
checks) was given a matching branch: `animal_registration/service.py`
checks `if side == "appointment": return self._side_question_response(...)`
with a `None` answer (nothing is answered -- the registration is just
closed unsaved, and the router starts the booking with the same message);
`appointment_supervisor/service.py` has the mirrored check for `side ==
"add_animal"`. The router side (`route_turn_adk`'s loop) reads
`result.get("side_question")`, and when it names the *other* flow,
confirms-cancels the current supervisor's draft, dispatches the same
message to the other flow's handler, and stitches both replies together
via `_then()` (closed-flow message, blank line, new flow's first reply).

All of this -- the `side_question` callback shape, `_side_question_response`,
the router's `for agent, flow_intent, supervisor, has_draft in (...)` loop
-- is #71's dropped mechanism. Not portable as-is.

## What to build, this time against the current sticky-routing shape

1. The user-visible contract is clear and mechanism-independent: a
   genuine request for the *other* flow, made while one is open, should
   close the open one (unsaved, like an explicit cancel) and start the
   other from the same message -- with both the "closed" acknowledgment
   and the new flow's first reply shown together (the `_then()` stitching
   idea is sound and reusable regardless of what calls it).
2. The hard part is the trigger: today `route_turn_adk`'s sticky-routing
   checks (`_has_active_booking_draft`/`_has_active_registration_draft`)
   route straight into the open supervisor with no classification at all
   -- that's deliberate (cheap, no LLM call on every booking turn, see the
   existing comments on those functions) and is exactly what needs
   changing in a *targeted* way: only when the open supervisor's own
   extraction found nothing useful for its own flow (the same "turn
   failed to advance the draft" signal `_try_mid_draft_escape` already
   uses) does it make sense to also ask "is this actually the *other*
   flow?" before falling back to a plain re-ask. Needs a real design
   decision on whether this becomes a third classification path
   `_try_mid_draft_escape` also handles (a query/weather/other-flow
   three-way split instead of its current two-way one), or a separate
   check layered after it returns nothing.
3. `_then()` is a small, clean, standalone function -- portable as-is
   once there's a real call site for it.

- [ ] Design: where the "is this actually the other flow?" check fits
      relative to `_try_mid_draft_escape`'s existing trigger condition
- [ ] Port `_then()` verbatim (reply-stitching helper, no dependency on
      the dropped loop)
- [ ] Implementation: close-and-switch in both directions
      (`appointment_supervisor` <-> `animal_registration`)
- [ ] Regression tests: booking->registration switch, registration->booking
      switch, a turn that's ambiguous (sounds like it could still belong to
      the open flow) does NOT switch
- [ ] Full suite green, both with and without AWS credentials
