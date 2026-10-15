# Chocolate evals

Fixed chat conversations, saved as JSON, that we run again and again against the
Chocolate agents. Each run checks the answers and the speed and saves the results.
Later runs are compared with a saved baseline to catch regressions.

## Layers

| Layer | File | What it tests |
|---|---|---|
| 1 | `conversations/layer1_normal.json` | One clear intent: simple questions and full happy-path flows |
| 2 | `layer2_complex.json` (coming) | Harder versions: typos, missing details, corrections mid-flow |
| 3 | `layer3_mixed.json` (coming) | Two things mixed in one conversation |
| 4 | `layer4_twist.json` (coming) | The farmer changes the topic completely mid-flow |

All 7 languages are covered: en, hi, mr, ta, te, kn, ml.

## How to run

1. Start the API server (in a separate terminal):
   `uvicorn services.api_service.main:app --host 127.0.0.1 --port 8001`
2. Make sure `data/` has no local changes (`git status data`).
3. From the repo root:

```
python -m evals.run                    # everything
python -m evals.run --layer 1          # one layer
python -m evals.run --lang hi-IN       # one language
python -m evals.run --only L1-en-004   # one conversation
python -m evals.run --repeat 3         # each conversation 3 times
python -m evals.run --validate         # only check the JSON files
```

Results are saved to `evals/results/<run_id>.json` (not committed).
Restart the server before a run if an earlier run or manual test changed data,
so the query agent does not answer from old cached data.

## Baseline and regressions

The LLM does not answer the same way every time, so one run is not enough to
call something broken. Run each conversation 3 times and save that as the
baseline (commit `evals/baseline/baseline.json`):

```
python -m evals.run --layer 1 --repeat 3
python -m evals.compare --save-baseline --latest 1
```

After a code change, run again and compare:

```
python -m evals.run --layer 1 --repeat 3
python -m evals.compare --latest 1
```

| Verdict | Meaning |
|---|---|
| REGRESSION | passed every time in the baseline, now fails most of the time (exit code 1) |
| WORSE | pass rate dropped by half or more |
| FIXED | failed every time in the baseline, now passes most of the time |
| FLAKY | passes sometimes, fails sometimes |
| NEW | not in the baseline yet |

An agent is marked slower when its p50 latency is 1.5x the baseline and at
least 1 second slower. A baseline is refused if a run stopped early or used
`--only` / `--lang`.

## Data safety

Bookings and registrations really write to `data/`. So the runner refuses to
start if `data/` has local changes, runs the conversations that save data last,
and puts `data/` back with `git checkout -- data` after each of them and at the
end of the run (also on Ctrl+C).

## Conversation format

```json
{
  "id": "L1-en-001",
  "language": "en-IN",
  "title": "Goat count",
  "mutates": false,
  "turns": [
    {"user": "How many goats do I have?",
     "expect": {"agent": "query_agent", "number": 14}}
  ]
}
```

`expect` keys (all optional):

- `agent`: agent that must answer
- `reply_contains_any` / `reply_contains_all` / `reply_not_contains`: text checks, case-insensitive
- `number`: number that must be in the reply. Indian digits count, so `१४` is 14
- `script`: set `false` to skip the check that the reply is in the farmer's script
- `max_ms`: latency limit for that turn

Conversation keys: `mutates: true` if it saves data; `data_checks` such as
`{"file": "animals.json", "contains": "EVAL-{tag}-EN005"}` or
`{"file": "appointments.json", "grew": true}`. `{tag}` is replaced with a
unique value per run, so new IDs never clash.

The expected numbers come from `data/animals.json` for farmer f-001
(53 animals: goat 14, sheep 7, buffalo 16, cow 9, chicken 7).
`tests/test_evals.py` fails if that data changes, so the JSON gets updated too.
