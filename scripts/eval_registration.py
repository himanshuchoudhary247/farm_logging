#!/usr/bin/env python3
"""animal_registration extraction eval -- runs tests/eval/registration_cases.yaml
through the REAL AnimalRegistrationSupervisor._extract (live Bedrock) and checks
what the model put into the record_animal_registration tool call.

Why this exists: tests/test_animal_registration.py mocks _extract, so the unit
suite checks the state machine but never the extraction itself. The breed-loop
bugs shipped with every unit test green. scripts/eval_extraction.py and
eval_conversations.py only cover the shared call_bedrock path, not this
module's own tool spec and prompt. This fills that gap.

LLM output varies run to run, so each case runs --runs times (default 3) and
passes on a strict majority (2 of 3).

Nothing in the app is changed by this script: it builds an in-memory draft,
calls _extract, and reads the result. No draft file is written, no animal is
registered.

Usage:
    python scripts/eval_registration.py --dry-run            # offline: validate the case file only
    python scripts/eval_registration.py                      # configured extraction model, 3 runs/case
    python scripts/eval_registration.py --model deepseek     # shortcut from eval_extraction.py
    python scripts/eval_registration.py --lang hi,ta --runs 1
    python scripts/eval_registration.py --only reg-b-ta-sheep

Env: needs the same Bedrock credentials/region as the server (.env loaded).
BEDROCK_MODEL_EXTRACTION=<id> forces a model id, same as the other eval scripts.

Exit code: 0 if every case passes, 1 if any case fails or errors (usable as a
pre-merge check for PRs that touch the registration tool spec or prompt).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

VALID_STATES = {"COLLECTING", "COLLECTING_OPTIONAL", "CONFIRMING", "CORRECTING"}


@dataclass
class Case:
    id: str
    lang: str
    note: str
    state: str
    captured: Dict[str, Any]
    text: str
    expect: Dict[str, Any]
    expect_absent: List[str]


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
    cases: List[Case] = []
    for row in raw:
        cases.append(Case(
            id=row["id"],
            lang=row.get("lang", "en-IN"),
            note=row.get("note", ""),
            state=row["state"],
            captured=row.get("captured") or {},
            text=row["text"],
            expect=row.get("expect") or {},
            expect_absent=row.get("expect_absent") or [],
        ))
    return cases


def validate_cases(cases: List[Case]) -> List[str]:
    """Offline checks: every referenced field must exist in the real tool spec,
    ids must be unique, states must be ones _extract knows about."""
    from services.animal_registration.service import _ANIMAL_REGISTRATION_TOOL_SPEC

    known = set(_ANIMAL_REGISTRATION_TOOL_SPEC["inputSchema"]["json"]["properties"])
    problems: List[str] = []
    seen: set = set()
    for c in cases:
        if c.id in seen:
            problems.append(f"{c.id}: duplicate id")
        seen.add(c.id)
        if c.state not in VALID_STATES:
            problems.append(f"{c.id}: unknown state {c.state!r}")
        for key in list(c.expect) + list(c.expect_absent) + list(c.captured):
            if key not in known:
                problems.append(f"{c.id}: field {key!r} is not in the tool spec")
        overlap = set(c.expect) & set(c.expect_absent)
        if overlap:
            problems.append(f"{c.id}: {sorted(overlap)} in both expect and expect_absent")
    return problems


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _same(expected: Any, predicted: Any) -> bool:
    if isinstance(expected, bool):
        if isinstance(predicted, bool):
            return predicted is expected
        return str(predicted).strip().lower() == str(expected).lower()
    return str(expected).strip().lower() == str(predicted).strip().lower()


def check(case: Case, predicted: Dict[str, Any]) -> List[str]:
    """Returns the list of reasons the prediction fails; empty means pass."""
    reasons: List[str] = []
    for key, want in case.expect.items():
        got = predicted.get(key)
        # 'none' for confirmation_signal means "this turn is not a yes/no/cancel";
        # omitting the field says the same thing.
        if key == "confirmation_signal" and str(want).lower() == "none":
            if not _is_empty(got) and str(got).lower() != "none":
                reasons.append(f"{key}: expected none/omitted, got {got!r}")
            continue
        if _is_empty(got):
            reasons.append(f"{key}: expected {want!r}, missing")
        elif not _same(want, got):
            reasons.append(f"{key}: expected {want!r}, got {got!r}")
    for key in case.expect_absent:
        got = predicted.get(key)
        if not _is_empty(got):
            reasons.append(f"{key}: must be absent, got {got!r}")
    return reasons


class _FailureCatcher(logging.Handler):
    """_extract swallows Bedrock exceptions and returns {}. Without this, an
    auth/region error would look like a PASS on cases that expect nothing.
    Catches the warning _extract logs so those runs count as errors."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "extraction failed" in msg:
            self.messages.append(msg)


def run_one(sup: Any, case: Case, catcher: _FailureCatcher) -> RunResult:
    draft = sup._fresh(f"eval-{case.id}", "eval-farmer", case.lang)
    draft["state"] = case.state
    draft["draft"] = dict(case.captured)

    catcher.messages.clear()
    t0 = time.time()
    try:
        predicted = sup._extract(draft, case.text) or {}
    except Exception as exc:  # _extract normally catches; this is a safety net
        return RunResult(predicted={}, ms=(time.time() - t0) * 1000, passed=False, error=str(exc))
    ms = (time.time() - t0) * 1000
    if catcher.messages:
        return RunResult(predicted={}, ms=ms, passed=False, error=catcher.messages[-1])

    reasons = check(case, predicted)
    return RunResult(predicted=predicted, ms=ms, passed=not reasons, reasons=reasons)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(REPO_ROOT / "tests" / "eval" / "registration_cases.yaml"))
    ap.add_argument("--model", default="current",
                    help="Shortcut or model id (shortcuts from scripts/eval_extraction.py). Default: current config.")
    ap.add_argument("--lang", default="", help="Comma-separated language filter (en,hi,ta,te,kn). Default: all.")
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
        print("dry-run OK -- case file well-formed, every field exists in the tool spec")
        return 0

    if args.runs < 1:
        print("--runs must be at least 1")
        return 1

    # Reuse the shortcut table from the existing eval script instead of copying it.
    from scripts.eval_extraction import resolve_model  # noqa: E402

    model_id = resolve_model(args.model)
    os.environ["BEDROCK_MODEL_EXTRACTION"] = model_id
    from services.llm_service import bedrock_adapter as ba
    ba._llm_config_cache = None

    if not args.verbose:
        logging.getLogger("bedrock").setLevel(logging.WARNING)
    catcher = _FailureCatcher()
    reg_log = logging.getLogger("animal_registration")
    reg_log.addHandler(catcher)

    from services.animal_registration.service import AnimalRegistrationSupervisor

    needed = args.runs // 2 + 1
    print(f"\n=== {len(cases)} cases x {args.runs} runs against {model_id} (pass = {needed}/{args.runs}) ===")

    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        sup = AnimalRegistrationSupervisor(Path(tmp))
        for c in cases:
            results = [run_one(sup, c, catcher) for _ in range(args.runs)]
            n_pass = sum(r.passed for r in results)
            n_err = sum(r.error is not None for r in results)
            ok = n_pass >= needed
            print(f"{'PASS' if ok else 'FAIL'}  {n_pass}/{args.runs}  {c.id}"
                  + (f"  ({n_err} error)" if n_err else ""))
            rows.append({"case": c, "results": results, "ok": ok, "n_err": n_err})

    reg_log.removeHandler(catcher)

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
            print(f"  state={c.state}  text={c.text!r}")
            for i, res in enumerate(r["results"], 1):
                if res.error:
                    print(f"  run {i}: ERROR {res.error}")
                elif not res.passed:
                    print(f"  run {i}: {'; '.join(res.reasons)}")
                    print(f"         predicted={json.dumps(res.predicted, ensure_ascii=False)}")

    out_path = REPO_ROOT / "data" / "eval" / "registration" / f"{model_id.replace('/', '_').replace(':', '_')}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            c = r["case"]
            f.write(json.dumps({
                "id": c.id, "lang": c.lang, "note": c.note, "state": c.state,
                "text": c.text, "expect": c.expect, "expect_absent": c.expect_absent,
                "ok": r["ok"],
                "runs": [{"predicted": res.predicted, "ms": round(res.ms), "passed": res.passed,
                          "reasons": res.reasons, "error": res.error} for res in r["results"]],
            }, ensure_ascii=False) + "\n")
    print(f"\nper-case output: {out_path}")

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
