#!/usr/bin/env python3
"""Appointment extraction eval (Extraction review - Root cause, part 2).

Runs tests/eval/appointment_cases.yaml through the REAL call_bedrock (live
Bedrock) with the same pending question appointment_supervisor sends through
process_text_input(pending_questions_override=...), and checks what the model
extracted.

Why this exists: the past appointment_supervisor bugs ("1122 is id only arnt
you smart enough", "FAKEANIMAL999", a bare number turned into a date/time)
only happen when the bot has just asked a specific question. eval_extraction.py
calls call_bedrock with no context and eval_conversations.py never sets the
pending override, so neither reproduces them. The unit tests mock extraction.

Same method as scripts/eval_registration.py: each case runs --runs times
(default 3) and passes on a strict majority (2 of 3).

Nothing in the app is changed: no session store, no draft, no booking. It
calls call_bedrock directly and reads the result.

Usage:
    python scripts/eval_appointment_extraction.py --dry-run
    python scripts/eval_appointment_extraction.py
    python scripts/eval_appointment_extraction.py --model deepseek --lang ml,kn --runs 1
    python scripts/eval_appointment_extraction.py --only apt-num-time-66

Exit code: 0 if every case passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Exact strings appointment_supervisor.turn() puts in pending_questions for
# these two states (services/appointment_supervisor/service.py). They are
# inline literals there, so they are mirrored here; field questions come from
# orchestrator.APPOINTMENT_FIELD_LABELS directly so those can't drift.
PENDING_CONFIRM = "confirm these details are correct (yes/no), or cancel"
PENDING_SUBMIT = "submit the appointment now (yes/submit), or cancel"

TOP_LEVEL_KEYS = {"intent", "confirmation_signal"}


@dataclass
class Case:
    id: str
    lang: str
    note: str
    pending: str
    entities: Dict[str, Any]
    text: str
    expect: Dict[str, Any]
    expect_absent: List[str]
    expect_one_of: List[str]


@dataclass
class RunResult:
    predicted: Dict[str, Any]
    ms: float
    passed: bool
    reasons: List[str] = field(default_factory=list)
    error: Optional[str] = None


def load_cases(path: Path) -> List[Case]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    return [Case(
        id=row["id"],
        lang=row.get("lang", "en-IN"),
        note=row.get("note", ""),
        pending=str(row["pending"]),
        entities=row.get("entities") or {},
        text=str(row["text"]),
        expect=row.get("expect") or {},
        expect_absent=row.get("expect_absent") or [],
        expect_one_of=row.get("expect_one_of") or [],
    ) for row in raw]


def resolve_pending(pending: str) -> str:
    from services.voice_agent.orchestrator import APPOINTMENT_FIELD_LABELS

    if pending == "confirm":
        return PENDING_CONFIRM
    if pending == "submit":
        return PENDING_SUBMIT
    if pending.startswith("field:"):
        name = pending.split(":", 1)[1]
        if name not in APPOINTMENT_FIELD_LABELS:
            raise KeyError(f"unknown field {name!r} (not in APPOINTMENT_FIELD_LABELS)")
        return APPOINTMENT_FIELD_LABELS[name]
    raise KeyError(f"unknown pending {pending!r} (use confirm, submit, or field:<name>)")


def validate_cases(cases: List[Case]) -> List[str]:
    from services.llm_service.bedrock_adapter import _EXTRACTION_TOOL_SPEC

    known = set(_EXTRACTION_TOOL_SPEC["inputSchema"]["json"]["properties"])
    problems: List[str] = []
    seen: set = set()
    for c in cases:
        if c.id in seen:
            problems.append(f"{c.id}: duplicate id")
        seen.add(c.id)
        try:
            resolve_pending(c.pending)
        except KeyError as exc:
            problems.append(f"{c.id}: {exc}")
        for key in list(c.expect) + c.expect_absent + c.expect_one_of + list(c.entities):
            if key not in known:
                problems.append(f"{c.id}: field {key!r} is not in _EXTRACTION_TOOL_SPEC")
        overlap = (set(c.expect) | set(c.expect_one_of)) & set(c.expect_absent)
        if overlap:
            problems.append(f"{c.id}: {sorted(overlap)} both expected and expected absent")
        if not (c.expect or c.expect_absent or c.expect_one_of):
            problems.append(f"{c.id}: asserts nothing")
    return problems


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or str(value).lower() == "none"


def _date_matches(expected: Any, got: Any) -> bool:
    exp = str(expected).strip().lower()
    got_s = str(got).strip().lower()
    if exp == got_s:
        return True
    # Same timezone build_prompt uses for today/tomorrow.
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    iso = {
        "today": today.isoformat(),
        "tomorrow": (today + timedelta(days=1)).isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
    }.get(exp)
    return iso is not None and iso == got_s


def _value(predicted: Dict[str, Any], key: str) -> Any:
    if key in TOP_LEVEL_KEYS:
        return predicted.get(key)
    return (predicted.get("entities") or {}).get(key)


def check(case: Case, predicted: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    for key, want in case.expect.items():
        got = _value(predicted, key)
        if _is_empty(got):
            reasons.append(f"{key}: expected {want!r}, missing")
        elif key == "date":
            if not _date_matches(want, got):
                reasons.append(f"{key}: expected {want!r}, got {got!r}")
        elif str(want).strip().lower() != str(got).strip().lower():
            reasons.append(f"{key}: expected {want!r}, got {got!r}")
    for key in case.expect_absent:
        got = _value(predicted, key)
        if not _is_empty(got):
            reasons.append(f"{key}: must be absent, got {got!r}")
    if case.expect_one_of and all(_is_empty(_value(predicted, k)) for k in case.expect_one_of):
        reasons.append(f"expected at least one of {case.expect_one_of}, got none")
    return reasons


def run_one(case: Case) -> RunResult:
    from services.llm_service.bedrock_adapter import call_bedrock

    context = {
        "intent": "CREATE_APPOINTMENT",
        "entities": dict(case.entities),
        "pending_questions": [resolve_pending(case.pending)],
    }
    t0 = time.time()
    try:
        predicted = call_bedrock(case.text, context=context) or {}
    except Exception as exc:
        return RunResult(predicted={}, ms=(time.time() - t0) * 1000, passed=False, error=str(exc))
    ms = (time.time() - t0) * 1000
    predicted = {k: v for k, v in predicted.items() if k != "_raw"}
    reasons = check(case, predicted)
    return RunResult(predicted=predicted, ms=ms, passed=not reasons, reasons=reasons)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(REPO_ROOT / "tests" / "eval" / "appointment_cases.yaml"))
    ap.add_argument("--model", default="current",
                    help="Shortcut or model id (shortcuts from scripts/eval_extraction.py). Default: current config.")
    ap.add_argument("--lang", default="", help="Comma-separated language filter (en,hi,ta,te,kn,ml). Default: all.")
    ap.add_argument("--only", default="", help="Comma-separated case ids to run.")
    ap.add_argument("--runs", type=int, default=3, help="Runs per case; passes on a strict majority. Default 3.")
    ap.add_argument("--dry-run", action="store_true", help="No Bedrock calls; only validate the case file.")
    ap.add_argument("--verbose", action="store_true", help="Keep per-call Bedrock LATENCY log lines.")
    args = ap.parse_args()

    cases = load_cases(Path(args.cases))
    if args.lang:
        wanted = {x.strip().lower() for x in args.lang.split(",")}
        cases = [c for c in cases if c.lang.split("-")[0].lower() in wanted]
    if args.only:
        ids = {x.strip() for x in args.only.split(",")}
        cases = [c for c in cases if c.id in ids]

    print(f"loaded {len(cases)} cases from {args.cases}")
    print(f"  languages: {', '.join(sorted({c.lang for c in cases}))}")

    problems = validate_cases(cases)
    if problems:
        print("case file problems:")
        for p in problems:
            print(f"  - {p}")
        return 1
    if args.dry_run:
        print("dry-run OK -- case file well-formed, every field and pending question resolves")
        return 0
    if args.runs < 1:
        print("--runs must be at least 1")
        return 1

    from scripts.eval_extraction import resolve_model  # noqa: E402

    model_id = resolve_model(args.model)
    os.environ["BEDROCK_MODEL_EXTRACTION"] = model_id
    from services.llm_service import bedrock_adapter as ba
    ba._llm_config_cache = None
    if not args.verbose:
        logging.getLogger("bedrock").setLevel(logging.WARNING)

    needed = args.runs // 2 + 1
    print(f"\n=== {len(cases)} cases x {args.runs} runs against {model_id} (pass = {needed}/{args.runs}) ===")

    rows: List[Dict[str, Any]] = []
    for c in cases:
        results = [run_one(c) for _ in range(args.runs)]
        n_pass = sum(r.passed for r in results)
        n_err = sum(r.error is not None for r in results)
        ok = n_pass >= needed
        print(f"{'PASS' if ok else 'FAIL'}  {n_pass}/{args.runs}  {c.id}"
              + (f"  ({n_err} error)" if n_err else ""))
        rows.append({"case": c, "results": results, "ok": ok, "n_err": n_err})

    failed = [r for r in rows if not r["ok"]]
    all_ms = [res.ms for r in rows for res in r["results"] if res.error is None]
    by_lang: Dict[str, List[bool]] = {}
    for r in rows:
        by_lang.setdefault(r["case"].lang, []).append(r["ok"])

    summary = {
        "model": model_id,
        "cases": len(rows),
        "runs_per_case": args.runs,
        "passed": len(rows) - len(failed),
        "failed": len(failed),
        "calls_with_errors": sum(r["n_err"] for r in rows),
        "pass_rate": round((len(rows) - len(failed)) / len(rows), 3) if rows else None,
        "pass_rate_by_lang": {k: round(sum(v) / len(v), 3) for k, v in sorted(by_lang.items())},
        "latency_ms_p50": round(statistics.median(all_ms), 0) if all_ms else None,
    }
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if failed:
        print("\n=== failures ===")
        for r in failed:
            c = r["case"]
            print(f"\n{c.id}  [{c.lang}]  {c.note}")
            print(f"  pending={c.pending}  text={c.text!r}")
            for i, res in enumerate(r["results"], 1):
                if res.error:
                    print(f"  run {i}: ERROR {res.error}")
                elif not res.passed:
                    print(f"  run {i}: {'; '.join(res.reasons)}")
                    print(f"         predicted={json.dumps(res.predicted, ensure_ascii=False)}")

    out_path = REPO_ROOT / "data" / "eval" / "appointment" / f"{model_id.replace('/', '_').replace(':', '_')}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            c = r["case"]
            f.write(json.dumps({
                "id": c.id, "lang": c.lang, "note": c.note, "pending": c.pending,
                "text": c.text, "expect": c.expect, "expect_absent": c.expect_absent,
                "expect_one_of": c.expect_one_of, "ok": r["ok"],
                "runs": [{"predicted": res.predicted, "ms": round(res.ms), "passed": res.passed,
                          "reasons": res.reasons, "error": res.error} for res in r["results"]],
            }, ensure_ascii=False) + "\n")
    print(f"\nper-case output: {out_path}")

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
