# Nova Sonic access/quality probe

Verifies Amazon Nova Sonic (speech-to-speech, `InvokeModelWithBidirectionalStream`)
access and multilingual quality with real audio turns.

App venv moved to Python 3.13 (2026-09-13) specifically so this SDK
(`aws_sdk_bedrock_runtime`, the only one that supports the bidirectional-
stream API — plain boto3 doesn't) can run in-process. Deps are in the main
`requirements.txt` (`aws_sdk_bedrock_runtime`, `awscrt`, `gtts`).

`ffmpeg` must be on PATH (used to convert gTTS mp3 output to 16kHz mono PCM).

## Usage

```bash
source venv/bin/activate
python scripts/nova_sonic_probe/client.py "My cow has a fever, what should I do?" en
python scripts/nova_sonic_probe/client.py "मेरी गाय को बुखार है" hi
python scripts/nova_sonic_probe/client.py "..." kn --raw   # --raw dumps every event
```

Second arg is the gTTS language code used to synthesize the input audio
(`en`, `hi`, `kn`, `ta`, `te`, `ml`, ...).

## Findings (2026-09-13, us-east-1)

- **Access confirmed**: real `InvokeModelWithBidirectionalStream` calls
  succeed and bill usage tokens on this account.
- **Regional availability**: `amazon.nova-sonic-v1:0` exists in `us-east-1`
  and `ap-northeast-1` only (checked against `ap-south-1`, `ap-south-2`,
  `ap-southeast-1`, `ap-southeast-2`). Not available in `ap-south-1`, where
  FarmHerd is hosted — any use means a cross-region call.
- **Language coverage** (real audio turns, not text-only):
  - `en`: correct ASR, relevant conversational replies.
  - `hi`: correct ASR (romanized transcript), but replies sometimes came
    back in English rather than Hindi.
  - `kn` / `ta` / `te` / `ml`: ASR degraded to phonetic garbage or a bare
    echo of the input with no generated reply. Not usable as tested.
- **Reliability**: roughly 1 in 5 English turns returned an empty response
  with no error — server-side turn-taking (VAD) on synthetic gTTS audio
  isn't fully consistent. Real human speech may behave differently; not
  tested here.
- Config knobs for this (model id, region, voice, allowed languages) live in
  `config/llm.yaml` under `nova_sonic:`, resolved via
  `services.llm_service.bedrock_adapter.get_nova_sonic_config()`. They are
  not wired into `services/voice_agent/transcribe.py` or `tts.py` — doing
  that for real traffic needs the app's runtime on Python 3.12+ first.

## Conversation-turn eval (2026-09-13, `scripts/eval_nova_sonic_conversations.py`)

Same dataset as the text-extraction eval (`tests/eval/conversations.yaml`,
146 turns, 6 languages) — 84 turns run as real Nova Sonic audio calls
(en/hi full 10/10 conversations; kn/ta/te/ml capped at 2/10 each, already
proven broken on isolated single-utterance probes above — running the full
10 would just re-spend Bedrock speech tokens confirming the same result).
Single-shot per turn, no carried Nova Sonic session across turns. Raw
results: `data/eval/runs/nova_sonic_conversations.jsonl`.

| lang  | turns | asr_ok | got_reply | errors | avg latency (s) |
|-------|------:|-------:|----------:|-------:|-----------------:|
| en-IN |    24 |      3 |         2 |      0 |             4.51 |
| hi-IN |    26 |      1 |         1 |      0 |             4.34 |
| kn-IN |     9 |      0 |         0 |      0 |             3.78 |
| ta-IN |     8 |      0 |         0 |      0 |             3.83 |
| te-IN |     8 |      0 |         0 |      0 |             3.90 |
| ml-IN |     9 |      0 |         0 |      0 |             3.87 |

**New finding**: even en/hi — the two languages that gave good replies on
the full-sentence isolated probes above — collapse to near-zero success
(en 2/24, hi 1/26) on real conversation turns. Most conversation turns are
short fragments (single word or a few words: species name, symptom, "yes",
"tomorrow morning") rather than full sentences, and Nova Sonic's
turn-taking (server-side VAD) appears to frequently fail to detect
end-of-speech or produce any output at all for short utterances — 0 hard
errors, just silent no-output turns. FarmHerd's actual turn style is
dominated by exactly this short-fragment pattern, so this is a worse result
than the single-utterance probes suggested, not a better one.

## Conclusion

Runtime blocker is gone (app is on Python 3.13 now). Language gap remains:
2 of 6 target languages (en, hi) work on full sentences; kn/ta/te/ml don't
work at all. On real conversation-shaped turns (short fragments), even
en/hi drop to near-zero reply rate. Nova Sonic is not a viable replacement
for the Transcribe+Bedrock+Polly pipeline in FarmHerd's actual usage
pattern.
