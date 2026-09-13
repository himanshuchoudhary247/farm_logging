"""Nova Sonic audio-turn replay over tests/eval/conversations.yaml.

Each turn's `user` text is synthesized to speech (gTTS) and sent through
Nova Sonic as real audio (services/../scripts/nova_sonic_probe/client.py),
same dataset used for the text-extraction eval (scripts/eval_conversations.py)
so the two number sets are directly comparable.

Turns are sent single-shot (no carried Nova Sonic session across turns) —
Nova Sonic has no extraction/entity contract to check against `expect`, so
this measures a narrower thing than the text eval: did real speech in
produce a real ASR transcript, and did the model generate any reply at all.

ml still shown broken even after the trailing-silence fix (2026-09-13:
fluent but wrong replies on misheard ASR) — capped at 2 conversations to
avoid re-spending tokens confirming the same result. en/hi/kn/ta/te run in
full (10/10) for a complete comparison against the text-extraction eval.

Output: data/eval/runs/nova_sonic_conversations.jsonl
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent / "nova_sonic_probe"))
from client import run_turn  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONV_PATH = ROOT / "tests" / "eval" / "conversations.yaml"
OUT_PATH = ROOT / "data" / "eval" / "runs" / "nova_sonic_conversations.jsonl"

LANG_TO_GTTS = {"kn-IN": "kn", "hi-IN": "hi", "ta-IN": "ta", "te-IN": "te", "en-IN": "en", "ml-IN": "ml"}
FULL_LANGS = {"en-IN", "hi-IN", "kn-IN", "ta-IN", "te-IN"}
CAPPED_CONVS_PER_LANG = 2

CONCURRENCY = 3


async def run_one(conv_id: str, lang: str, turn_idx: int, user_text: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        t0 = time.monotonic()
        out = await run_turn(user_text, LANG_TO_GTTS[lang])
        asr = out["text_output"][0] if out["text_output"] else None
        reply_text = " ".join(out["text_output"][1:]) if len(out["text_output"]) > 1 else ""
        got_reply = bool(reply_text.strip())
        return {
            "conv_id": conv_id,
            "lang": lang,
            "turn_idx": turn_idx,
            "user_text": user_text,
            "asr_transcript": asr,
            "reply_text": reply_text or None,
            "got_reply": got_reply,
            "error": out["error"],
            "latency_s": out["latency_s"],
            "wall_s": round(time.monotonic() - t0, 2),
        }


async def main() -> None:
    conversations = yaml.safe_load(CONV_PATH.read_text(encoding="utf-8"))

    by_lang: dict[str, list] = {}
    for c in conversations:
        by_lang.setdefault(c["lang"], []).append(c)

    selected = []
    for lang, convs in by_lang.items():
        n = len(convs) if lang in FULL_LANGS else min(CAPPED_CONVS_PER_LANG, len(convs))
        selected.extend(convs[:n])

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = []
    for conv in selected:
        for i, turn in enumerate(conv["turns"]):
            tasks.append(run_one(conv["id"], conv["lang"], i, turn["user"], sem))

    print(f"running {len(tasks)} turns across {len(selected)} conversations "
          f"(en/hi/kn/ta/te full 10/10, ml capped at {CAPPED_CONVS_PER_LANG}/10)...")

    results = []
    for fut in asyncio.as_completed(tasks):
        r = await fut
        results.append(r)
        print(f"  [{len(results)}/{len(tasks)}] {r['conv_id']} turn{r['turn_idx']} "
              f"lang={r['lang']} got_reply={r['got_reply']} err={r['error']}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nwrote {len(results)} results to {OUT_PATH}")

    by_lang_stats: dict[str, dict] = {}
    for r in results:
        s = by_lang_stats.setdefault(r["lang"], {"turns": 0, "asr_ok": 0, "got_reply": 0, "errors": 0, "latencies": []})
        s["turns"] += 1
        if r["asr_transcript"]:
            s["asr_ok"] += 1
        if r["got_reply"]:
            s["got_reply"] += 1
        if r["error"]:
            s["errors"] += 1
        if r["latency_s"] is not None:
            s["latencies"].append(r["latency_s"])

    print("\n=== Nova Sonic audio-turn summary ===")
    print(f"{'lang':8} {'turns':>6} {'asr_ok':>7} {'got_reply':>10} {'errors':>7} {'avg_latency_s':>14}")
    for lang in sorted(by_lang_stats):
        s = by_lang_stats[lang]
        avg_lat = round(sum(s["latencies"]) / len(s["latencies"]), 2) if s["latencies"] else None
        print(f"{lang:8} {s['turns']:>6} {s['asr_ok']:>7} {s['got_reply']:>10} {s['errors']:>7} {avg_lat!s:>14}")


if __name__ == "__main__":
    asyncio.run(main())
