#!/usr/bin/env python3
"""Extraction parity eval — runs the golden-set utterances against one or
more Bedrock models and reports field-level F1, latency, and $/1000 turns.

Usage:
    python scripts/eval_extraction.py                       # runs configured extraction tier
    python scripts/eval_extraction.py --model haiku,nova    # named shortcuts
    python scripts/eval_extraction.py --lang kn,hi          # subset by language
    python scripts/eval_extraction.py --dry-run             # offline: just parse + validate golden set

Env override:
    AWS_REGION, LLM_CONFIG_PATH standard.
    BEDROCK_MODEL_EXTRACTION=<id>   force a specific model id.

Model shortcuts:
    haiku      -> apac.anthropic.claude-haiku-4-5-20251001-v1:0
    nova       -> amazon.nova-micro-v1:0
    mistral    -> mistral.mistral-small-2402-v1:0
    luna       -> in.openai.gpt-5.6-luna
    deepseek   -> deepseek.deepseek-v3-1-v1:0
    current    -> whatever config/llm.yaml models.extraction.id resolves to
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
from typing import Any, Dict, Iterable, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

MODEL_SHORTCUTS = {
    "haiku": "apac.anthropic.claude-haiku-4-5-20251001-v1:0",
    "nova": "amazon.nova-micro-v1:0",
    "mistral": "mistral.mistral-small-2402-v1:0",
    "luna": "in.openai.gpt-5.6-luna",
    "deepseek": "deepseek.deepseek-v3-1-v1:0",
    "current": None,  # resolved from config
}

# Rough list-price cost per 1K in-tokens + per 1K out-tokens (USD, ap-south-1).
# Update as pricing changes. Used only for a rough $/1000-turns estimate.
PRICING = {
    "apac.anthropic.claude-haiku-4-5-20251001-v1:0": (0.001, 0.005),
    "amazon.nova-micro-v1:0": (0.000035, 0.00014),
    "mistral.mistral-small-2402-v1:0": (0.001, 0.003),
    "in.openai.gpt-5.6-luna": (0.001, 0.004),
    "deepseek.deepseek-v3-1-v1:0": (0.0005, 0.002),
    "mistral.mistral-large-3-675b-instruct": (0.008, 0.024),
}


@dataclass
class Case:
    id: str
    lang: str
    text: str
    expected: Dict[str, Any]


@dataclass
class Score:
    case_id: str
    ms: float
    predicted: Dict[str, Any]
    tp: int = 0
    fp: int = 0
    fn: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    error: Optional[str] = None


def load_golden(path: Path) -> List[Case]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    cases: List[Case] = []
    for row in raw:
        cases.append(Case(
            id=row["id"],
            lang=row.get("lang", "en-IN"),
            text=row["text"],
            expected=row.get("expected") or {},
        ))
    return cases


def flatten_expected(exp: Dict[str, Any]) -> Dict[str, Any]:
    """Turn nested expected into {field_key: value} for scoring."""
    out: Dict[str, Any] = {}
    if "intent" in exp:
        out["intent"] = exp["intent"]
    ent = exp.get("entities") or {}
    for k in ("species", "issue", "date", "time", "animal_name", "animal_tag"):
        if k in ent:
            out[f"entities.{k}"] = ent[k]
    if "symptoms" in ent:
        out["entities.symptoms"] = sorted(str(s).lower() for s in ent["symptoms"])
    return out


def flatten_predicted(pred: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if pred.get("intent"):
        out["intent"] = pred["intent"]
    ent = pred.get("entities") or {}
    for k in ("species", "issue", "date", "time", "animal_name", "animal_tag"):
        v = ent.get(k)
        if v not in (None, ""):
            out[f"entities.{k}"] = v
    sy = ent.get("symptoms")
    if isinstance(sy, list) and sy:
        out["entities.symptoms"] = sorted(str(s).lower() for s in sy)
    return out


def score_case(expected: Dict[str, Any], predicted: Dict[str, Any]) -> tuple[int, int, int]:
    """Field-level TP/FP/FN. date matches if predicted contains any expected token."""
    exp = flatten_expected(expected)
    pred = flatten_predicted(predicted)
    tp = fp = fn = 0
    all_keys = set(exp) | set(pred)
    for k in all_keys:
        e = exp.get(k)
        p = pred.get(k)
        if e is None:
            if p is not None:
                fp += 1
            continue
        if p is None:
            fn += 1
            continue
        # Value comparison. Symptom lists: any-overlap counts.
        if k == "entities.symptoms":
            if set(e) & set(p):
                tp += 1
            else:
                fp += 1
                fn += 1
        elif k in ("entities.date",):
            if str(e).lower() in str(p).lower() or str(p).lower() in str(e).lower():
                tp += 1
            else:
                fp += 1
                fn += 1
        elif str(e).lower() == str(p).lower():
            tp += 1
        else:
            fp += 1
            fn += 1
    return tp, fp, fn


def f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0  # nothing expected, nothing predicted
    denom = 2 * tp + fp + fn
    return (2 * tp / denom) if denom else 0.0


def resolve_model(shortcut_or_id: str) -> str:
    if shortcut_or_id in MODEL_SHORTCUTS:
        v = MODEL_SHORTCUTS[shortcut_or_id]
        if v is not None:
            return v
        # 'current' — read from config
        from services.llm_service.bedrock_adapter import model_for_task, TaskTier
        return model_for_task(TaskTier.EXTRACTION)["id"]
    return shortcut_or_id


def run_one(case: Case, model_id: str) -> Score:
    """Invoke Bedrock adapter for a single case with model override."""
    os.environ["BEDROCK_MODEL_EXTRACTION"] = model_id
    # Clear config cache so env override is respected on this call
    from services.llm_service import bedrock_adapter as ba
    ba._llm_config_cache = None
    from services.llm_service.bedrock_adapter import call_bedrock

    t0 = time.time()
    try:
        pred = call_bedrock(case.text, context=None)
    except Exception as exc:
        return Score(case_id=case.id, ms=(time.time() - t0) * 1000,
                     predicted={}, error=str(exc))
    ms = (time.time() - t0) * 1000
    tp, fp, fn = score_case(case.expected, pred)
    return Score(case_id=case.id, ms=ms, predicted=pred, tp=tp, fp=fp, fn=fn)


def summarize(scores: List[Score], model_id: str) -> Dict[str, Any]:
    tp = sum(s.tp for s in scores)
    fp = sum(s.fp for s in scores)
    fn = sum(s.fn for s in scores)
    ms = [s.ms for s in scores if s.error is None]
    errors = [s for s in scores if s.error]
    per_case_f1 = [f1(s.tp, s.fp, s.fn) for s in scores if s.error is None]

    price = PRICING.get(model_id, (0.001, 0.003))
    # Assume ~500 in / 200 out per turn as coarse cost model.
    cost_per_turn = 0.500 * price[0] + 0.200 * price[1]

    return {
        "model": model_id,
        "cases": len(scores),
        "errors": len(errors),
        "field_f1_micro": round(f1(tp, fp, fn), 3),
        "field_f1_macro": round(statistics.mean(per_case_f1) if per_case_f1 else 0.0, 3),
        "latency_ms_p50": round(statistics.median(ms), 0) if ms else None,
        "latency_ms_p95": round(sorted(ms)[int(len(ms) * 0.95) - 1], 0) if len(ms) >= 20 else None,
        "cost_per_1000_turns_usd": round(cost_per_turn * 1000, 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=str(REPO_ROOT / "tests" / "eval" / "golden_extraction.yaml"))
    ap.add_argument("--model", default="current",
                    help="Comma-separated shortcut(s) or model id(s). Default: current (from config).")
    ap.add_argument("--lang", default="",
                    help="Comma-separated language filter (kn,hi,ta,te). Default: all.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Skip live Bedrock calls; only parse + validate golden set.")
    ap.add_argument("--json", action="store_true", help="Emit summary as JSON.")
    args = ap.parse_args()

    cases = load_golden(Path(args.golden))
    if args.lang:
        wanted = {x.strip().lower() for x in args.lang.split(",")}
        cases = [c for c in cases if c.lang.split("-")[0].lower() in wanted]

    print(f"loaded {len(cases)} cases from {args.golden}")
    langs = sorted({c.lang for c in cases})
    print(f"  languages: {', '.join(langs)}")

    if args.dry_run:
        # Validate expected shapes
        for c in cases:
            flatten_expected(c.expected)
        print("dry-run OK — golden set well-formed")
        return 0

    models = [resolve_model(m.strip()) for m in args.model.split(",")]
    all_summaries = []
    for model_id in models:
        print(f"\n=== running {len(cases)} cases against {model_id} ===")
        scores = []
        for i, c in enumerate(cases, 1):
            s = run_one(c, model_id)
            scores.append(s)
            marker = "!" if s.error else ("." if f1(s.tp, s.fp, s.fn) >= 0.5 else "x")
            print(marker, end="", flush=True)
            if i % 50 == 0:
                print(f"  {i}/{len(cases)}")
        print()
        summary = summarize(scores, model_id)
        all_summaries.append(summary)
        print(json.dumps(summary, indent=2))

        # Also dump per-case for later diffing
        out_path = REPO_ROOT / "data" / "eval" / f"{model_id.replace('/', '_').replace(':', '_')}.jsonl"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for c, s in zip(cases, scores):
                f.write(json.dumps({
                    "id": c.id, "lang": c.lang, "text": c.text,
                    "expected": c.expected, "predicted": s.predicted,
                    "ms": s.ms, "tp": s.tp, "fp": s.fp, "fn": s.fn,
                    "error": s.error,
                }, ensure_ascii=False) + "\n")
        print(f"per-case output: {out_path}")

    if len(all_summaries) > 1:
        print("\n=== comparison ===")
        print(json.dumps(all_summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
