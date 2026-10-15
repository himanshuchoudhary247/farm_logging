"""Save a baseline from eval runs, and compare new runs against it.

Chocolate's answers come from an LLM, so the same question can pass once and
fail the next time. One run is not enough to call something a regression.
So a baseline stores, for every conversation, how often it passed across
several runs (its pass rate), plus latency per agent.

Usage (from the farm_logging repo root):

    # 1. Make a baseline from the last 3 runs in evals/results/
    python -m evals.compare --save-baseline --latest 3

    # 2. Later, after code changes: run evals again, then compare
    python -m evals.run --layer 1 --repeat 3
    python -m evals.compare --latest 1

    # Or name result files directly
    python -m evals.compare evals/results/20261015-231007.json

Verdicts per conversation:
    REGRESSION  baseline passed (almost) always, now fails most of the time
    FIXED       baseline failed (almost) always, now passes most of the time
    WORSE       pass rate dropped a lot, but it was not stable before
    FLAKY       passes sometimes, fails sometimes (before and/or now)
    SAME        no meaningful change
    NEW         conversation is not in the baseline yet

Exit code is 1 when there is at least one REGRESSION, else 0.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVALS_DIR / "results"
BASELINE_PATH = EVALS_DIR / "baseline" / "baseline.json"

STABLE_PASS = 0.9    # pass rate at or above this counts as "always passes"
STABLE_FAIL = 0.1    # pass rate at or below this counts as "always fails"
BIG_DROP = 0.5       # drop in pass rate that counts as WORSE
SLOW_FACTOR = 1.5    # p50 this many times the baseline ...
SLOW_MIN_MS = 1000   # ... and at least this many ms slower -> flagged as slower


# ---------------------------------------------------------------- loading

def load_runs(paths: list[Path]) -> list[dict]:
    runs = []
    for p in paths:
        run = json.loads(p.read_text(encoding="utf-8"))
        run["_file"] = p.name
        runs.append(run)
    return runs


def latest_result_files(n: int) -> list[Path]:
    files = sorted(RESULTS_DIR.glob("*.json"))
    return files[-n:] if n > 0 else []


def _pct(values: list[float], p: float) -> float:
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(p / 100 * (len(values) - 1))))
    return values[k]


def aggregate(runs: list[dict]) -> dict:
    """Turn one or more runs into pass rates per conversation and latency per agent."""
    convs: dict[str, dict] = {}
    lat: dict[str, list[float]] = {}
    for run in runs:
        for r in run.get("results", []):
            c = convs.setdefault(r["id"], {"passes": 0, "runs": 0, "layer": r.get("layer"),
                                           "language": r.get("language"), "title": r.get("title", "")})
            c["runs"] += 1
            c["passes"] += 1 if r["passed"] else 0
            for t in r.get("turns", []):
                if t.get("error"):
                    continue
                agent = (t.get("expect") or {}).get("agent") or t.get("agent") or "?"
                lat.setdefault(agent, []).append(t["ms"])
    for c in convs.values():
        c["rate"] = round(c["passes"] / c["runs"], 3) if c["runs"] else 0.0
    latency = {a: {"n": len(v), "p50": round(statistics.median(v)), "p90": round(_pct(v, 90))}
               for a, v in sorted(lat.items()) if v}
    return {"conversations": dict(sorted(convs.items())), "latency_ms": latency}


# ---------------------------------------------------------------- verdicts

def verdict(base: dict | None, now: dict) -> str:
    if base is None:
        return "NEW"
    b, n = base["rate"], now["rate"]
    if b >= STABLE_PASS and n < 0.5:
        return "REGRESSION"
    if b <= STABLE_FAIL and n >= 0.5 and n > b:
        return "FIXED"
    if b - n >= BIG_DROP:
        return "WORSE"
    if STABLE_FAIL < b < STABLE_PASS or STABLE_FAIL < n < STABLE_PASS:
        return "FLAKY"
    return "SAME"


def compare(baseline: dict, current: dict) -> dict:
    rows = []
    for cid, now in current["conversations"].items():
        base = baseline["conversations"].get(cid)
        rows.append({"id": cid, "verdict": verdict(base, now),
                     "base": f"{base['passes']}/{base['runs']}" if base else "-",
                     "now": f"{now['passes']}/{now['runs']}", "title": now.get("title", "")})
    slower = []
    for agent, now in current["latency_ms"].items():
        base = baseline["latency_ms"].get(agent)
        if base and now["p50"] > base["p50"] * SLOW_FACTOR and now["p50"] - base["p50"] >= SLOW_MIN_MS:
            slower.append({"agent": agent, "base_p50": base["p50"], "now_p50": now["p50"]})
    return {"rows": rows, "slower": slower}


ORDER = ["REGRESSION", "WORSE", "FIXED", "FLAKY", "NEW", "SAME"]
ICON = {"REGRESSION": "[RED]   ", "WORSE": "[ORANGE]", "FIXED": "[GREEN] ",
        "FLAKY": "[YELLOW]", "NEW": "[NEW]   ", "SAME": "        "}


def print_report(baseline: dict, current: dict, result: dict, files: list[str]) -> None:
    print(f"Baseline: {baseline.get('created_at', '?')}  commit {baseline.get('git_commits', '?')}  "
          f"({baseline.get('run_count', '?')} runs)")
    print(f"Current : {', '.join(files)}")
    counts = {v: sum(1 for r in result["rows"] if r["verdict"] == v) for v in ORDER}
    print("Summary : " + "  ".join(f"{v} {counts[v]}" for v in ORDER if counts[v]))
    print()
    print(f"{'':9}{'id':<12}{'baseline':>9}{'now':>7}  title")
    for v in ORDER:
        for r in result["rows"]:
            if r["verdict"] == v and v != "SAME":
                print(f"{ICON[v]} {r['id']:<12}{r['base']:>9}{r['now']:>7}  {r['title']}")
    print()
    print("Latency p50 (ms)          baseline     now")
    for agent, now in current["latency_ms"].items():
        base = baseline["latency_ms"].get(agent, {}).get("p50", "-")
        flag = "  <- slower" if any(s["agent"] == agent for s in result["slower"]) else ""
        print(f"  {agent:<24}{base:>8}{now['p50']:>8}{flag}")


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Save or compare against an eval baseline.")
    ap.add_argument("files", nargs="*", help="result JSON files from evals/results/")
    ap.add_argument("--latest", type=int, default=0, help="use the last N result files")
    ap.add_argument("--save-baseline", action="store_true",
                    help="write evals/baseline/baseline.json from the given runs")
    args = ap.parse_args(argv)

    paths = [Path(f) for f in args.files] + latest_result_files(args.latest)
    if not paths:
        print("Give result files or --latest N.")
        return 2
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print("Not found: " + ", ".join(missing))
        return 2
    runs = load_runs(paths)
    aborted = [r["_file"] for r in runs if r.get("aborted")]
    if aborted:
        print("Warning: these runs stopped early, their numbers are partial: " + ", ".join(aborted))
    current = aggregate(runs)

    if args.save_baseline:
        if aborted:
            print("Refusing to save a baseline from runs that stopped early.")
            return 2
        partial = [r["_file"] for r in runs
                   if (r.get("filters") or {}).get("only") or (r.get("filters") or {}).get("lang")]
        if partial:
            print("Refusing to save a baseline from runs made with --only or --lang "
                  "(they test only part of the suite): " + ", ".join(partial))
            return 2
        baseline = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "git_commits": sorted({r.get("git_commit", "?") for r in runs}),
            "run_count": len(runs),
            "source_runs": [r["_file"] for r in runs],
            **current,
        }
        BASELINE_PATH.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
        total = len(current["conversations"])
        stable = sum(1 for c in current["conversations"].values() if c["rate"] >= STABLE_PASS)
        print(f"Saved baseline: {BASELINE_PATH.relative_to(EVALS_DIR.parent)}")
        print(f"  {len(runs)} runs, {total} conversations, {stable} pass every time")
        for cid, c in current["conversations"].items():
            if c["rate"] <= STABLE_FAIL:
                print(f"  always fails: {cid:<12} {c['passes']}/{c['runs']}  {c['title']}")
            elif c["rate"] < STABLE_PASS:
                print(f"  flaky:        {cid:<12} {c['passes']}/{c['runs']}  {c['title']}")
        return 0

    if not BASELINE_PATH.exists():
        print("No baseline yet. Create one first:\n  python -m evals.compare --save-baseline --latest 3")
        return 2
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    result = compare(baseline, current)
    print_report(baseline, current, result, [r["_file"] for r in runs])
    return 1 if any(r["verdict"] == "REGRESSION" for r in result["rows"]) else 0


if __name__ == "__main__":
    sys.exit(main())
