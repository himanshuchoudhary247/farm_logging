# 01: A "yes"/"no" that carries a correction gets read back, not submitted unseen

**What to build:** mid-booking, when the farmer's reply to a yes/no/submit
checkpoint also carries a new value (a different animal, a changed date,
etc.), apply the correction and show the updated readback instead of
treating the bare "yes"/"no" literally and submitting/rejecting unseen.
Separately: a question that names a *different* animal than the one
already in the booking ("which breed is KAALI?" while booking for GAURI)
must be answered as a question, not silently swap the booked animal.

**Blocked by:** None (can start immediately) -- deliberately deferred out
of the farm_logging PR #71/#73 cleanup this ticket came from (see
Context), since it needs real design work against this repo's current
mid-draft-escape architecture, not a mechanical port.

**Status:** ready-for-agent

## Context (found during the #71/#73 cleanup, verified against real code)

PR #71 (`feat/evals-layer3`) built a "side-question" router mechanism
(`adk_router.py`'s `_side_question_label`/`_side_question_envelope`,
injected into each supervisor's `turn()` as a `side_question` callback)
to answer off-topic questions mid-draft. PR #72 (`feat/mid-draft-topic-
switch`, already merged into `dev`) solved the same problem through a
different, better-tested mechanism (`services/chat_orchestrator/
mid_draft_escape.py`'s classify-*then-verify* `_try_mid_draft_escape`) and
was kept as the sole mechanism; #71's side-question system was dropped.

PR #73 (`feat/evals-layer4`, stacked on #71) added two more behaviors on
top of that same side-question loop, both real farmer-reported bugs (per
its own commit messages, not speculative):

- **Correction-with-yes** (`APPOINTMENT_CORRECTION_WITH_YES`, commit
  `47101cb`): "no wait, tomorrow was right" came back as
  `confirmation_signal="yes"` in English, and the booking went straight to
  "would you like to submit?" with the *old* date -- the correction was
  silently lost. Fix computed `said_now` (entities genuinely new this
  turn, diffed against the session cache) and treated `yes`/`no`/`submit`
  as a correction whenever `said_now` carries a real change, re-showing
  the readback instead of submitting/confirming blind.
- **Other-animal-question-check** (`APPOINTMENT_OTHER_ANIMAL_QUESTION_CHECK`,
  commits `47101cb` + `fd7ee95`): "which breed is KAALI?" asked while
  booking for GAURI was read as naming a new animal and silently replaced
  GAURI with KAALI in the draft. Fix routed a turn that names a *different*
  animal (and doesn't otherwise change a booking field) through the
  side-question classifier first -- a real question stays a question; an
  actual correction ("no, not GAURI, it's KAALI") still applies as before.
  `fd7ee95` additionally handled the case where the model read that same
  question as `confirmation_signal="no"` (seen in Telugu/Kannada) --
  without a specific carve-out, a bare "no" at the readback unconditionally
  reset the verified animal, so a disguised question still wiped it.

Both are implemented in `services/appointment_supervisor/service.py`'s
`_turn_locked`, both directly depend on the `side_question` parameter and
the cache-restore machinery (`cache_before`/`cache_after`) built around
it -- not portable as-is now that #71's mechanism is gone.

## What to build, this time against `_try_mid_draft_escape`

1. **Correction-with-yes**: the `said_now` diffing idea (only entities
   genuinely new *this* turn count as a correction, not stale cached
   values) is sound and mechanism-independent -- it can be computed the
   same way without the `side_question` callback. The real design question
   is where this check fits relative to `_try_mid_draft_escape`'s existing
   CONFIRMING-checkpoint gate (`services/appointment_supervisor/
   service.py`, the `awaiting_confirmation and confirmation_signal not in
   {"yes", "cancel"}` block) -- are these the same signal (a "yes" that
   doesn't quite fit should probably never auto-submit) or genuinely
   separate checks that need to compose.
2. **Other-animal-question-check**: `_try_mid_draft_escape(text, farmer_id,
   session_id, language)` already does real classify-then-verify for
   exactly this shape of question ("which breed is KAALI?" is a genuine
   query-agent question with real sql+data). The missing piece is the
   *trigger*: today the escape only fires when nothing was extracted
   (`COLLECTING`) or the signal is ambiguous (`CONFIRMING`) -- a turn that
   *does* extract a new animal name never reaches it. Needs a new trigger
   condition: "extraction named a different animal than the one already
   verified, with nothing else in this turn supporting a real correction"
   -- offer the escape a chance before accepting the swap.
3. Both need regression tests in `tests/test_appointment_supervisor.py`
   mirroring the shape of PR #72's own `test_cancel_at_confirming_is_not_
   swallowed_by_the_escape_probe`-style tests (found a real bug this same
   way during #72's own deep review -- same rigor applies here).

- [ ] Design: where `said_now`-style correction detection fits relative to
      the existing `_try_mid_draft_escape` CONFIRMING gate
- [ ] Design: a new escape trigger for "extraction named a different
      animal, nothing else supports a real correction"
- [ ] Implementation in `services/appointment_supervisor/service.py`
- [ ] Regression tests for both the original bugs (silent-submit-with-
      stale-date, silent-animal-swap) and the disguised-as-"no" variant
- [ ] Full suite green, both with and without AWS credentials
