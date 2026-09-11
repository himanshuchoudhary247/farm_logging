# Extraction model evaluation — 2026-09-11

## Context

`services/llm_service/bedrock_adapter.py:call_bedrock` is the **sole**
extraction engine for the voice pipeline (`services/voice_agent/orchestrator.py`).
As of commit `6c1bb06` all regex/rule-based field extraction was removed —
there is no fallback parser. Every entity (intent, species, symptoms, date,
time, animal name/tag, etc.) for every voice turn, in any of Kannada, Hindi,
Tamil, Telugu, Malayalam, or English, comes from one Bedrock call.

This doc records how the extraction model was chosen: the candidate list,
the eval methodology, the bugs the process surfaced (in our prompt, not just
in the models), and the final decision.

**Decision: `deepseek.v3-v1:0` is the `extraction` tier model** (see
`config/llm.yaml`). 100% turn-pass / 100% conversation-pass on the final
60-conversation × 6-language live run, 0 remaining failures.

## Why a comparison was needed

The original plan (see `/Users/sudhanshu/.claude/plans/elegant-roaming-river.md`
Section A6) picked `anthropic.claude-haiku-4-5` as the extraction default
based on published benchmarks. Once regex extraction was deleted, this
became a single point of failure for the entire pipeline, so every model
choice needed to be verified against this account's actual Bedrock access
(several planned models turned out to be inaccessible — see below) and
against real conversational Indic-language input, not just single-utterance
benchmarks.

## Models considered and their access status on this AWS account

Probed live via direct `boto3` `converse()` calls, 2026-09-11
(account `198799425726`, region `ap-south-1`):

| Model | Bedrock ID | Status |
|---|---|---|
| Claude Haiku 4.5 | `global.anthropic.claude-haiku-4-5-20251001-v1:0` | **Blocked** — `ResourceNotFoundException: Model use case details have not been submitted for this account.` Anthropic use-case form, not a code issue. Retry once cleared. |
| Claude 3 Haiku | `apac.anthropic.claude-3-haiku-20240307-v1:0` | Blocked, same reason |
| GPT-5.6 Luna | `in.openai.gpt-5.6-luna` | Blocked — `AccessDeniedException`, needs a model access request |
| Nova Micro | `apac.amazon.nova-micro-v1:0` | ✓ working (needs the `apac.` cross-region profile; direct `amazon.nova-micro-v1:0` fails) |
| Nova Lite | `apac.amazon.nova-lite-v1:0` | ✓ working |
| Nova Pro | `apac.amazon.nova-pro-v1:0` | ✓ working |
| Ministral 3B/8B/14B | `mistral.ministral-3-{3b,8b,14b}-instruct` | ✓ working. `mistral.mistral-small-2402-v1:0` from the original plan does **not exist** on this account — Ministral is the current small-Mistral line |
| GLM-4.7 Flash / full | `zai.glm-4.7-flash`, `zai.glm-4.7` | ✓ working |
| Qwen3-32B | `qwen.qwen3-32b-v1:0` | ✓ working — only Qwen3 model in the 25-50B range on this account (others are 80B+ MoE or 235B+ flagship) |
| DeepSeek V3 | `deepseek.v3-v1:0` | ✓ working. `deepseek.deepseek-v3-1-v1:0` from the original plan is an **invalid ID** |
| Cohere Command R/R7B, Llama 3.1/3.2, Nova 2 Lite | various | Invalid IDs on this account, not probed further |

10 verified-working models were carried into the full eval.

## Eval methodology

Two harnesses, both under `scripts/`:

1. **`scripts/eval_extraction.py`** — single-utterance golden set
   (`tests/eval/golden_extraction.yaml`, 200 cases: 50 each Kannada, Hindi,
   Tamil, Telugu). Reports field-level F1 (micro/macro), P50/P95 latency,
   $/1000-turns estimate.
2. **`scripts/eval_conversations.py`** — multi-turn conversation replay
   (`tests/eval/conversations.yaml`, 60 dialogs: 10 each Kannada, Hindi,
   Tamil, Telugu, English, Malayalam — 146 turns total). Replays each
   dialog through `orchestrator.process_text_input`, accumulating session
   state exactly as production does, and checks both per-turn and final
   conversation state against expected values. Two modes:
   - **OFFLINE** (default): `call_bedrock` stubbed to empty — proves session
     bookkeeping (merge, prefill, follow-up generation) without touching
     Bedrock. Not a quality signal once all extraction is LLM-driven.
   - **LIVE** (`BEDROCK_LIVE=1`): real Bedrock calls via whatever
     `BEDROCK_MODEL_EXTRACTION` env override names. This is the mode used
     for every result in this document.

Run commands:

```bash
# Golden set, single utterance
python scripts/eval_extraction.py --model deepseek

# Conversation replay, live
BEDROCK_LIVE=1 BEDROCK_MODEL_EXTRACTION=deepseek.v3-v1:0 \
  python scripts/eval_conversations.py
```

Raw artifacts from every run in this doc are saved under `data/eval/runs/`:
- `<model>.summary.txt` — full stdout (summary JSON + per-turn failure list)
- `<model>.trace.jsonl` — one line per conversation: every turn's input
  text, extracted entities, intent, pass/fail, and miss reasons
- `golden-set-200case/<model>.jsonl` — per-case golden-set predictions

## Round 1 — golden set, 4 models, original prompt

| Model | F1 micro | F1 macro | P50 ms | P95 ms | $/1000 turns |
|---|---|---|---|---|---|
| Ministral-8B | 0.598 | 0.591 | 685 | 1287 | $0.07 |
| Nova Micro | 0.537 | 0.591 | 571 | 847 | $0.045 |
| GLM-4.7-Flash | 0.544 | 0.469 | 564 | 1125 | $0.11 |
| Qwen3-32B | 0.527 | 0.513 | 377 | 1127 | $0.22 |

All four clustered 0.53-0.60 F1 — no clean winner. This flagged the prompt
itself as the likely bottleneck rather than model choice.

## Prompt review and fix (round 1 -> round 2)

Reviewing `_SYSTEM_PROMPT` in `bedrock_adapter.py` against the observed
failures found four concrete gaps (not vague "model weakness"):

1. **No rule for bare single-word follow-up answers.** A reply of just
   "ಹಸು" (cow) or "my cow" to a pending question was dropping species
   entirely on several models.
2. **No few-shot examples.** Cheap/small models benefit disproportionately
   from 2-3 concrete input→output pairs, especially for short follow-ups
   and code-mixed input.
3. **Vaccine/appointment intent ambiguity.** "need vaccine for my sheep"
   was misclassified `CREATE_ANIMAL` instead of `CREATE_APPOINTMENT` in
   three languages.
4. **Malayalam was never mentioned** in the supported-language list.

Fix (commit `f68f291`): added an explicit "CRITICAL RULE for short
answers" paragraph, six worked examples covering bare follow-ups and the
vaccine case, and Malayalam in the language list.

Re-running the same golden set against the same 4 models isolated the
prompt's effect:

| Model | F1 micro before → after | F1 macro before → after |
|---|---|---|
| Nova Micro | 0.537 → **0.652** (+21%) | 0.591 → 0.691 (+17%) |
| GLM-4.7-Flash | 0.544 → **0.627** (+15%) | 0.469 → 0.655 (+40%) |
| Qwen3-32B | 0.527 → **0.658** (+25%) | 0.513 → 0.672 (+31%) |
| Ministral-8B | 0.598 → **0.619** (+4%) | 0.591 → 0.572 (flat) |

Confirmed: prompt quality, not model choice, was the dominant factor.

## Round 2 — full conversation eval, 10 models, 6 languages, fixed prompt

60 conversations × 6 languages (Kannada, Hindi, Tamil, Telugu, English,
Malayalam), 146 turns total, live Bedrock, `BEDROCK_LIVE=1`.

| Model | Turn pass | Conv pass | Avg ms | P95 ms | $/1000 turns |
|---|---|---|---|---|---|
| DeepSeek V3 | 95.2% | 95.0% | 821 | 1317 | $0.60 |
| GLM-4.7 (full) | 93.2% | 90.0% | 1205 | 1780 | $0.51 |
| Ministral-14B | 89.0% | 86.7% | 635 | 1065 | $0.15 |
| Nova Pro | 84.9% | 81.7% | 821 | 1151 | $0.96 |
| Ministral-8B | 81.5% | 71.7% | 653 | 1144 | $0.11 |
| Nova Lite | 80.1% | 76.7% | 751 | 1080 | $0.07 |
| GLM-4.7-Flash | 80.1% | 75.0% | 610 | 1060 | $0.10 |
| Qwen3-32B | 79.5% | 75.0% | 535 | 1307 | $0.18 |
| Nova Micro | 76.7% | 70.0% | 644 | 896 | $0.04 |
| Ministral-3B | 69.2% | 56.7% | 544 | 801 | $0.03 |

### Per-language breakdown (turn-pass %)

| Model | KN | HI | TA | TE | EN | ML |
|---|---|---|---|---|---|---|
| DeepSeek V3 | 92 | 96 | 96 | 100 | 92 | 96 |
| GLM-full | 88 | 96 | 96 | 91 | 96 | 92 |
| Ministral-14B | 88 | 88 | 78 | 87 | 96 | 96 |
| Nova Pro | 77 | 96 | 78 | 91 | 96 | 71 |
| Ministral-8B | 77 | 77 | 87 | 87 | 92 | 71 |
| Nova Lite | 65 | 92 | 78 | 87 | 88 | 71 |
| GLM-Flash | 69 | 81 | 83 | 87 | 92 | 71 |
| Qwen3-32B | 77 | 85 | 78 | 78 | 88 | 71 |
| Nova Micro | 69 | 88 | 70 | 83 | 92 | 58 |
| Ministral-3B | 73 | 69 | 70 | 74 | 83 | 46 |

**Every model drops 10-25 points on Kannada and Malayalam vs Hindi/English**
— a cross-model Indic-script gap, not one model's flaw. Ministral-14B was
the only model that didn't collapse on Malayalam specifically (96% vs
58-71% for everyone else), likely a tokenizer-coverage artifact.

## Deep failure analysis — DeepSeek V3 vs Ministral-14B

Root-caused every failing turn for the top two candidates (raw traces in
`data/eval/runs/{deepseek-v3,ministral-14b}.trace.jsonl`). Found that most
failures were **our bugs, not model weakness**:

### Bug 1 — schema duplication (10 of 23 combined failures)

The prompt asked for both `issue` (string) and `symptoms` (array) to carry
the same fact. Models correctly extracted one and skipped restating it in
the other, since it looked redundant. This was previously silently patched
around by `appointment_supervisor._copy_entities`, but only for the
appointment flow — `LOG_HEALTH`-only turns had no such backstop.

**Fix** (commit `c8cfbac`): `orchestrator.py:_canonicalize_entities` now
backfills deterministically in both directions.

### Bug 2 — no time-of-day convention (2 failures, both models)

"tomorrow morning" / "कल सुबह" has no exact hour. Models correctly returned
the literal word `"morning"` since the prompt never defined what hour that
means for booking purposes.

**Fix**: added explicit defaults to the system prompt — `morning=09:00,
afternoon=14:00, evening=18:00, night=20:00`.

### Bug 3 — stale context override (1 DeepSeek-specific failure)

DeepSeek kept an old turn's `issue` ("not giving milk") after a later turn
explicitly stated a new one ("has fever").

**Fix**: added an explicit rule — "if the current message states a new
value for a field that already has a value, the new message wins."

### Verification — re-ran both models after the fixes

| Model | Before | After |
|---|---|---|
| DeepSeek V3 | 95.2% | **100.0%** (0 remaining failures, 60/60 conversations) |
| Ministral-14B | 89.0% | **93.8%** |

## Round 3 — final confirmation, all 10 models, fixed schema + prompt

Re-ran the full 10-model × 60-conversation × 6-language suite to confirm
the shared bug fixes lifted every model, not just the two retested above.

| Model | Turn % | Conv % | Avg ms | P95 ms | $/1000 turns |
|---|---|---|---|---|---|
| **DeepSeek V3** | **100.0%** | **100.0%** | 752 | 1304 | $0.60 |
| GLM-4.7 (full) | 99.3% | 100.0% | 1257 | 2184 | $0.51 |
| Nova Pro | 94.5% | 86.7% | 806 | 1104 | $0.96 |
| Ministral-14B | 92.5% | 85.0% | 662 | 1084 | $0.15 |
| Nova Lite | 91.1% | 83.3% | 722 | 987 | $0.07 |
| Ministral-8B | 88.4% | 76.7% | 619 | 977 | $0.11 |
| Qwen3-32B | 87.0% | 80.0% | 485 | 1013 | $0.18 |
| GLM-4.7-Flash | 85.6% | 76.7% | 657 | 1131 | $0.10 |
| Nova Micro | 84.2% | 71.7% | 678 | 936 | $0.04 |
| Ministral-3B | 70.5% | 53.3% | 543 | 813 | $0.03 |

Every model improved from the schema fix — confirms it wasn't an artifact
specific to the two models retested. Ranking barely moved.

## Decision

**`deepseek.v3-v1:0`** is set as the `extraction` tier model in
`config/llm.yaml`.

- 100% turn-pass, 100% conversation-pass, zero remaining failures on the
  final 60-conversation × 6-language run.
- Not the cheapest ($0.60/1000 turns) or fastest (752ms avg, 1304ms P95),
  but at this scale the cost difference between the cheapest and priciest
  working candidate is under $1/1000 turns — **negligible in absolute
  terms**. A 6+ point accuracy gap (wrong species, wrong date, wrong
  symptom on a livestock vet booking) is a worse failure mode than ~150ms
  of extra latency per turn.
- `extraction_alt` is set to `mistral.ministral-3-14b-instruct` — 92.5%
  turn-pass at ~4x lower cost and ~40% lower P95 latency. The one
  documented weak spot is goat/sheep confusion specifically on Kannada
  ಆಡು and Tamil ஆடு. Flip via
  `BEDROCK_MODEL_EXTRACTION=mistral.ministral-3-14b-instruct` for a
  cost-sensitive canary.

## Open items

- **Retry Claude Haiku 4.5** once the Anthropic use-case form clears on
  this AWS account (`global.anthropic.claude-haiku-4-5-20251001-v1:0`).
  It was the original plan default and has not been benchmarked against
  this eval suite at all.
- **GPT-5.6 Luna** (`generation` tier candidate) needs a model access
  request — currently falls back to Haiku, which is itself blocked, so
  `generation` is effectively unverified in production right now.
- Kannada/Malayalam remain the weakest languages across every model —
  worth a dedicated prompt pass (more Indic few-shot examples) rather than
  relying on model choice alone to close that gap.
- The golden set (`tests/eval/golden_extraction.yaml`) covers Kannada,
  Hindi, Tamil, Telugu only (50 each) — no Malayalam or English cases.
  The conversation set (`tests/eval/conversations.yaml`) has all 6; worth
  back-filling the golden set to match.

## How to reproduce or extend

```bash
# Re-run the golden set against any verified model shortcut
python scripts/eval_extraction.py --model deepseek,ministral-14b,nova

# Re-run conversations against a specific model
BEDROCK_LIVE=1 BEDROCK_MODEL_EXTRACTION=<bedrock-model-id> \
  python scripts/eval_conversations.py --lang kn,ml

# Add a new model shortcut
# edit MODEL_SHORTCUTS and PRICING in scripts/eval_extraction.py
```

Model shortcuts available in `scripts/eval_extraction.py`: `haiku`, `nova`,
`nova-lite`, `ministral-3b`, `ministral-8b`, `ministral-14b`, `mistral`
(alias for ministral-8b), `glm-flash`, `glm`, `qwen3-32b`, `luna`,
`deepseek`, `deepseek-v3.2`, `current` (reads `config/llm.yaml`).
