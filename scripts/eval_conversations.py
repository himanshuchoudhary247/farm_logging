#!/usr/bin/env python3
"""Multi-turn conversation replay eval.

Replays each dialog in tests/eval/conversations.yaml through
services.voice_agent.orchestrator.process_text_input, tracks accumulated
session state per turn, and reports:

  * per-turn pass rate (all expected keys present with matching values)
  * per-conversation final-state pass rate
  * average time per turn
  * failures broken down by dialog id + turn index

LLM stubbed by default (offline). Set BEDROCK_LIVE=1 to hit real Bedrock via
whatever model config/llm.yaml routes to.

Usage:
    python scripts/eval_conversations.py
    python scripts/eval_conversations.py --lang kn,hi
    python scripts/eval_conversations.py --id kn-conv-01-booking-cow-fever
    BEDROCK_LIVE=1 python scripts/eval_conversations.py --lang kn
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@dataclass
class TurnResult:
    idx: int
    user: str
    ms: float
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


def load_conversations(path: Path) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def _resolve_relative_date(word: str) -> Optional[str]:
    from datetime import date, timedelta
    today = date.today()
    return {
        "today": today.isoformat(),
        "tomorrow": (today + timedelta(days=1)).isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
    }.get(word.lower())


def value_match(expected: Any, got: Any) -> bool:
    if isinstance(expected, list):
        if not isinstance(got, list):
            return False
        exp_norm = [str(x).lower() for x in expected]
        got_norm = [str(x).lower() for x in got]
        return any(e in got_norm for e in exp_norm)
    exp_s = str(expected).lower()
    got_s = str(got).lower()
    if exp_s == got_s:
        return True
    # Relative date tokens: accept ISO equivalent.
    iso = _resolve_relative_date(exp_s)
    if iso and iso == got_s:
        return True
    return False


def check_turn(expected: Dict[str, Any], got_entities: Dict[str, Any], got_intent: Optional[str]) -> tuple[bool, List[str]]:
    misses: List[str] = []
    for key, exp_val in (expected or {}).items():
        if key == "intent":
            if got_intent != exp_val:
                misses.append(f"intent: expected {exp_val!r}, got {got_intent!r}")
            continue
        got_val = got_entities.get(key)
        # date can also be satisfied by date_relative field.
        if key == "date" and got_val in (None, "", []):
            got_val = got_entities.get("date_relative")
        if got_val in (None, "", []):
            misses.append(f"{key}: missing (expected {exp_val!r})")
            continue
        if not value_match(exp_val, got_val):
            misses.append(f"{key}: expected {exp_val!r}, got {got_val!r}")
    return (len(misses) == 0), misses


def check_final(expected: Dict[str, Any], intent: Optional[str], entities: Dict[str, Any]) -> tuple[bool, List[str]]:
    misses: List[str] = []
    if "intent" in expected and intent != expected["intent"]:
        misses.append(f"intent: expected {expected['intent']!r}, got {intent!r}")
    for key, exp_val in (expected.get("entities") or {}).items():
        got_val = entities.get(key)
        if key == "date" and got_val in (None, "", []):
            got_val = entities.get("date_relative")
        if got_val in (None, "", []):
            misses.append(f"{key}: missing (expected {exp_val!r})")
            continue
        if not value_match(exp_val, got_val):
            misses.append(f"{key}: expected {exp_val!r}, got {got_val!r}")
    return (len(misses) == 0), misses


def run_conversation(conv: Dict[str, Any], live: bool) -> ConvResult:
    from services.voice_agent import orchestrator
    from services.voice_agent.session_store import clear_session, get_session

    if not live:
        # Stub LLM: offline path only tests rule extractors + session merge.
        orchestrator.call_bedrock = lambda text, **kw: {
            "intent": None, "entities": {}, "confidence": 0.0,
            "missing_fields": [], "follow_up_questions": [],
        }

    sid = f"conv-{conv['id']}-{int(time.time()*1000)}"
    clear_session(sid)

    turn_results: List[TurnResult] = []
    for i, turn in enumerate(conv["turns"], 1):
        text = turn["user"]
        expected = turn.get("expect") or {}
        t0 = time.time()
        out = orchestrator.process_text_input(text, session_id=sid)
        ms = (time.time() - t0) * 1000
        got_entities = out.get("entities") or {}
        got_intent = out.get("intent")
        passed, misses = check_turn(expected, got_entities, got_intent)
        turn_results.append(TurnResult(
            idx=i, user=text, ms=ms, expected=expected,
            got_entities=got_entities, got_intent=got_intent,
            passed=passed, misses=misses,
        ))

    final = conv.get("final") or {}
    session = get_session(sid)
    entities = session.get("entities") or {}
    intent = session.get("intent")
    final_ok, final_misses = check_final(final, intent, entities)

    return ConvResult(
        id=conv["id"], lang=conv.get("lang", "en-IN"),
        turns=turn_results, final_expected=final,
        final_state={"intent": intent, "entities": entities},
        final_passed=final_ok, final_misses=final_misses,
    )


def summarize(results: List[ConvResult]) -> Dict[str, Any]:
    total_convs = len(results)
    total_turns = sum(len(r.turns) for r in results)
    turn_pass = sum(1 for r in results for t in r.turns if t.passed)
    final_pass = sum(1 for r in results if r.final_passed)
    all_ms = [t.ms for r in results for t in r.turns]

    by_lang: Dict[str, Dict[str, int]] = {}
    for r in results:
        lang = r.lang.split("-")[0]
        d = by_lang.setdefault(lang, {"convs": 0, "convs_pass": 0, "turns": 0, "turns_pass": 0})
        d["convs"] += 1
        d["convs_pass"] += int(r.final_passed)
        d["turns"] += len(r.turns)
        d["turns_pass"] += sum(1 for t in r.turns if t.passed)

    return {
        "conversations": total_convs,
        "conversations_passed": final_pass,
        "turns": total_turns,
        "turns_passed": turn_pass,
        "turn_pass_rate": round(turn_pass / total_turns * 100, 1) if total_turns else 0,
        "final_pass_rate": round(final_pass / total_convs * 100, 1) if total_convs else 0,
        "avg_turn_ms": round(statistics.mean(all_ms), 2) if all_ms else 0,
        "p95_turn_ms": round(sorted(all_ms)[int(len(all_ms) * 0.95) - 1], 2) if len(all_ms) >= 20 else None,
        "by_lang": by_lang,
    }


def print_failures(results: List[ConvResult], verbose: bool) -> None:
    fails = [r for r in results if not r.final_passed or any(not t.passed for t in r.turns)]
    if not fails:
        print("\nno failures — all conversations green")
        return
    print(f"\n=== failures ({len(fails)}) ===")
    for r in fails:
        print(f"\n{r.id}  lang={r.lang}")
        for t in r.turns:
            marker = "." if t.passed else "x"
            print(f"  {marker} turn {t.idx}: {t.user!r}  ms={t.ms:.1f}")
            for m in t.misses:
                print(f"      - {m}")
            if verbose and t.passed:
                print(f"      state: intent={t.got_intent} entities={t.got_entities}")
        if not r.final_passed:
            print(f"  FINAL FAIL:")
            for m in r.final_misses:
                print(f"      - {m}")
            print(f"      state: {r.final_state}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO_ROOT / "tests" / "eval" / "conversations.yaml"))
    ap.add_argument("--lang", default="", help="filter by lang prefix, comma-separated (kn,hi,ta,te,en)")
    ap.add_argument("--id", default="", help="run only this conversation id")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    live = os.getenv("BEDROCK_LIVE", "").lower() in {"1", "true", "yes", "on"}
    print(f"mode: {'LIVE bedrock' if live else 'OFFLINE (LLM stubbed)'}")

    convs = load_conversations(Path(args.data))
    if args.id:
        convs = [c for c in convs if c["id"] == args.id]
    if args.lang:
        wanted = {x.strip().lower() for x in args.lang.split(",")}
        convs = [c for c in convs if c.get("lang", "en-IN").split("-")[0].lower() in wanted]

    print(f"loaded {len(convs)} conversations from {args.data}")

    results = [run_conversation(c, live=live) for c in convs]

    summary = summarize(results)
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print_failures(results, verbose=args.verbose)

    # Dump per-conversation trace
    out_path = REPO_ROOT / "data" / "eval" / "conversations.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "id": r.id, "lang": r.lang,
                "final_passed": r.final_passed,
                "final_misses": r.final_misses,
                "final_state": r.final_state,
                "turns": [
                    {"idx": t.idx, "user": t.user, "ms": t.ms,
                     "passed": t.passed, "misses": t.misses,
                     "got_intent": t.got_intent, "got_entities": t.got_entities}
                    for t in r.turns
                ],
            }, ensure_ascii=False) + "\n")
    print(f"\nper-conversation trace: {out_path}")

    return 0 if summary["turns_passed"] == summary["turns"] and summary["conversations_passed"] == summary["conversations"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
