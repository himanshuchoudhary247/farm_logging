#!/usr/bin/env python3
"""Full voice-pipeline conversation replay — the same 146-turn dataset as
eval_conversations.py, but through the REAL production voice path instead
of raw text:

  turn text -> gTTS synth -> services.voice_agent.transcribe.transcribe_audio
  (STT, whatever STT_PROVIDER resolves to) -> STT transcript ->
  orchestrator.process_text_input (Bedrock extraction, accumulated session
  state, exactly as eval_conversations.py) -> response_text ->
  services.voice_agent.tts.synthesize_speech (TTS)

Measures the combined effect of STT transcription error + extraction on
final accuracy (the pure-text eval only measures extraction), plus real
per-stage latency (STT/extraction/TTS) and TTS output validity.

Usage:
    python scripts/eval_conversations_voice.py
    python scripts/eval_conversations_voice.py --lang kn,hi
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_conversations import check_turn, check_final, load_conversations  # noqa: E402

GTTS_LANG = {"kn": "kn", "hi": "hi", "ta": "ta", "te": "te", "en": "en", "ml": "ml"}


def synth_wav_bytes(text: str, gtts_lang: str) -> bytes:
    from gtts import gTTS
    import io
    buf = io.BytesIO()
    gTTS(text=text, lang=gtts_lang).write_to_fp(buf)
    mp3 = Path(tempfile.mkstemp(suffix=".mp3")[1])
    mp3.write_bytes(buf.getvalue())
    wav = Path(tempfile.mkstemp(suffix=".wav")[1])
    subprocess.run(["ffmpeg", "-y", "-i", str(mp3), "-ar", "16000", "-ac", "1", str(wav)],
                    check=True, capture_output=True)
    data = wav.read_bytes()
    mp3.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)
    return data


@dataclass
class TurnResult:
    idx: int
    user_text: str
    stt_transcript: str
    ms_stt: float
    ms_extract: float
    ms_tts: float
    tts_bytes: int
    tts_err: Optional[str]
    expected: Dict[str, Any]
    got_entities: Dict[str, Any]
    got_intent: Optional[str]
    passed: bool
    misses: List[str] = field(default_factory=list)


@dataclass
class ConvResult:
    id: str
    lang: str
    turns: List[TurnResult]
    final_expected: Dict[str, Any]
    final_state: Dict[str, Any]
    final_passed: bool
    final_misses: List[str] = field(default_factory=list)


def run_conversation(conv: Dict[str, Any]) -> ConvResult:
    from services.voice_agent import orchestrator
    from services.voice_agent.transcribe import transcribe_audio
    from services.voice_agent.tts import synthesize_speech
    from services.voice_agent.session_store import clear_session, get_session

    lang_code = conv.get("lang", "en-IN")
    lang_short = lang_code.split("-")[0].lower()
    gtts_lang = GTTS_LANG.get(lang_short, "en")

    sid = f"voiceconv-{conv['id']}-{int(time.time()*1000)}"
    clear_session(sid)

    turn_results: List[TurnResult] = []
    for i, turn in enumerate(conv["turns"], 1):
        user_text = turn["user"]
        expected = turn.get("expect") or {}

        wav = synth_wav_bytes(user_text, gtts_lang)

        t0 = time.time()
        stt_text = transcribe_audio(wav, media_format="wav", language_code=lang_code)
        ms_stt = (time.time() - t0) * 1000

        t1 = time.time()
        out = orchestrator.process_text_input(stt_text, session_id=sid)
        ms_extract = (time.time() - t1) * 1000

        got_entities = out.get("entities") or {}
        got_intent = out.get("intent")
        # orchestrator.process_text_input doesn't compose the spoken reply
        # (that's appointment_supervisor.service, one layer up, needing
        # farmer/animal context this eval doesn't have) — follow_up_questions
        # is the real text that would be spoken back mid-flow, good enough
        # to exercise the TTS stage honestly.
        response_text = " ".join(out.get("follow_up_questions") or [])

        t2 = time.time()
        tts_audio, tts_err = synthesize_speech(response_text, lang_short) if response_text else (None, None)
        ms_tts = (time.time() - t2) * 1000
        tts_bytes = len(tts_audio) if tts_audio else 0

        passed, misses = check_turn(expected, got_entities, got_intent)
        turn_results.append(TurnResult(
            idx=i, user_text=user_text, stt_transcript=stt_text,
            ms_stt=ms_stt, ms_extract=ms_extract, ms_tts=ms_tts,
            tts_bytes=tts_bytes, tts_err=tts_err,
            expected=expected, got_entities=got_entities, got_intent=got_intent,
            passed=passed, misses=misses,
        ))

    final = conv.get("final") or {}
    session = get_session(sid)
    entities = session.get("entities") or {}
    intent = session.get("intent")
    final_ok, final_misses = check_final(final, intent, entities)

    return ConvResult(
        id=conv["id"], lang=lang_code,
        turns=turn_results, final_expected=final,
        final_state={"intent": intent, "entities": entities},
        final_passed=final_ok, final_misses=final_misses,
    )


def summarize(results: List[ConvResult]) -> Dict[str, Any]:
    total_convs = len(results)
    total_turns = sum(len(r.turns) for r in results)
    turn_pass = sum(1 for r in results for t in r.turns if t.passed)
    final_pass = sum(1 for r in results if r.final_passed)

    by_lang: Dict[str, Dict[str, Any]] = {}
    for r in results:
        lang = r.lang.split("-")[0]
        d = by_lang.setdefault(lang, {
            "convs": 0, "convs_pass": 0, "turns": 0, "turns_pass": 0,
            "stt_ms": [], "extract_ms": [], "tts_ms": [], "tts_fail": 0,
        })
        d["convs"] += 1
        d["convs_pass"] += int(r.final_passed)
        d["turns"] += len(r.turns)
        d["turns_pass"] += sum(1 for t in r.turns if t.passed)
        for t in r.turns:
            d["stt_ms"].append(t.ms_stt)
            d["extract_ms"].append(t.ms_extract)
            d["tts_ms"].append(t.ms_tts)
            if t.tts_err:
                d["tts_fail"] += 1

    by_lang_summary = {}
    for lang, d in by_lang.items():
        by_lang_summary[lang] = {
            "convs": d["convs"], "convs_pass": d["convs_pass"],
            "turns": d["turns"], "turns_pass": d["turns_pass"],
            "turn_pass_pct": round(d["turns_pass"] / d["turns"] * 100, 1) if d["turns"] else 0,
            "avg_stt_ms": round(statistics.mean(d["stt_ms"]), 0) if d["stt_ms"] else 0,
            "avg_extract_ms": round(statistics.mean(d["extract_ms"]), 0) if d["extract_ms"] else 0,
            "avg_tts_ms": round(statistics.mean(d["tts_ms"]), 0) if d["tts_ms"] else 0,
            "tts_fail": d["tts_fail"],
        }

    return {
        "conversations": total_convs, "conversations_passed": final_pass,
        "turns": total_turns, "turns_passed": turn_pass,
        "turn_pass_rate": round(turn_pass / total_turns * 100, 1) if total_turns else 0,
        "final_pass_rate": round(final_pass / total_convs * 100, 1) if total_convs else 0,
        "by_lang": by_lang_summary,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO_ROOT / "tests" / "eval" / "conversations.yaml"))
    ap.add_argument("--lang", default="")
    ap.add_argument("--id", default="")
    args = ap.parse_args()

    convs = load_conversations(Path(args.data))
    if args.id:
        convs = [c for c in convs if c["id"] == args.id]
    if args.lang:
        wanted = {x.strip().lower() for x in args.lang.split(",")}
        convs = [c for c in convs if c.get("lang", "en-IN").split("-")[0].lower() in wanted]

    print(f"loaded {len(convs)} conversations, running full voice pipeline (STT -> extraction -> TTS)...")

    results = []
    for i, c in enumerate(convs, 1):
        r = run_conversation(c)
        results.append(r)
        print(f"[{i}/{len(convs)}] {r.id} lang={r.lang} final_pass={r.final_passed} "
              f"turns_pass={sum(1 for t in r.turns if t.passed)}/{len(r.turns)}")

    summary = summarize(results)
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    out_path = REPO_ROOT / "data" / "eval" / "runs" / "conversations_voice.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "id": r.id, "lang": r.lang, "final_passed": r.final_passed,
                "final_misses": r.final_misses, "final_state": r.final_state,
                "turns": [
                    {"idx": t.idx, "user_text": t.user_text, "stt_transcript": t.stt_transcript,
                     "ms_stt": round(t.ms_stt), "ms_extract": round(t.ms_extract), "ms_tts": round(t.ms_tts),
                     "tts_bytes": t.tts_bytes, "tts_err": t.tts_err,
                     "passed": t.passed, "misses": t.misses,
                     "got_intent": t.got_intent, "got_entities": t.got_entities}
                    for t in r.turns
                ],
            }, ensure_ascii=False) + "\n")
    print(f"\nper-conversation trace: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
