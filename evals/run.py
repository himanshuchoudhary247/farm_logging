"""Run the Chocolate eval conversations against a running API server.

Usage (from the farm_logging repo root, with the API server already running):

    python -m evals.run                      # all layers
    python -m evals.run --layer 1            # one layer
    python -m evals.run --lang hi-IN         # one language
    python -m evals.run --only L1-en-004     # one conversation (repeatable)
    python -m evals.run --repeat 3           # run each conversation 3 times

Each run writes evals/results/<run_id>.json and prints a short summary.
Exit code is 0 only when every turn passes.

Data safety: the farmer's data/ files must have no local changes when a run
starts (so every run starts from the same state). Conversations that save
something (bookings, registrations) are run last, and data/ is put back with
`git checkout -- data/` after each of them and at the end, even on Ctrl+C.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from evals.judge import KNOWN_AGENTS, check_turn, turn_passed

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
CONV_DIR = EVALS_DIR / "conversations"
RESULTS_DIR = EVALS_DIR / "results"
DATA_DIR = REPO_ROOT / "data"
# Registration drafts, one JSON file per chat session (file name is a hash,
# the session_id is inside). Untracked by git, so git checkout won't remove them.
INTAKES_DIR = DATA_DIR / "animal_registration_intakes"

MAX_CONN_ERRORS_IN_A_ROW = 5     # server not reachable at all
MAX_SERVER_ERRORS_IN_A_ROW = 5   # server reachable but every turn returns HTTP 5xx


# ---------------------------------------------------------------- loading

def load_conversations(layers: list[int] | None = None) -> list[dict]:
    """Load every conversations/layer*.json file and flatten to one list."""
    convs: list[dict] = []
    for path in sorted(CONV_DIR.glob("layer*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        layer = doc["layer"]
        if layers and layer not in layers:
            continue
        for c in doc["conversations"]:
            c = dict(c)
            c["layer"] = layer
            c.setdefault("farmer_id", doc.get("farmer_id", "f-001"))
            c["_file"] = path.name
            convs.append(c)
    return convs


def validate_conversations(convs: list[dict]) -> list[str]:
    """Return a list of problems in the conversation files (empty = OK)."""
    problems: list[str] = []
    seen: set[str] = set()
    for c in convs:
        cid = c.get("id", "<no id>")
        if cid in seen:
            problems.append(f"{cid}: duplicate id")
        seen.add(cid)
        if not c.get("language"):
            problems.append(f"{cid}: missing language")
        if not c.get("turns"):
            problems.append(f"{cid}: no turns")
        for i, t in enumerate(c.get("turns", []), 1):
            if not str(t.get("user", "")).strip():
                problems.append(f"{cid} turn {i}: empty user text")
            agent = (t.get("expect") or {}).get("agent")
            if agent and agent not in KNOWN_AGENTS:
                problems.append(f"{cid} turn {i}: unknown agent {agent!r}")
        if c.get("data_checks") and not c.get("mutates"):
            problems.append(f"{cid}: has data_checks but mutates is false")
        for bad in sorted(set(_PLACEHOLDER.findall(json.dumps(c, ensure_ascii=False))) - {"tag", "past-time"}):
            token = "{" + bad + "}"
            if not (_DATE_PLACEHOLDER.fullmatch(token) or _WEEKDAY_PLACEHOLDER.fullmatch(token) or _dom_ok(token)):
                problems.append(f"{cid}: unknown placeholder {token}")
    return problems


# Placeholders, all counted from "now" in India (the bot works out dates in
# IST too), so a conversation checks the right answer on any day it runs:
#   {tag}        unique per run, so new IDs never clash
#   {date}, {date+2}, {date-1}   that day as YYYY-MM-DD. Lets a booking check
#                the date the bot understood, not only the time: Kannada
#                "ನಾಡಿದ್ದು" was saved as today and the old check still passed.
#   {next-mon}   first Monday strictly after today (mon..sun); {next-mon+7}
#                the one a week later -- "next Monday" can mean either.
#   {this-mon}   today if today is Monday, else {next-mon} -- "on Monday"
#                said on a Monday can mean today.
#   {past-time}  HH:00 two hours ago (00:00 just after midnight): a time
#                today that has always passed, for the "today 10 am at 1 pm"
#                booking case.
IST = timezone(timedelta(hours=5, minutes=30))
_PLACEHOLDER = re.compile(r"\{([^{}\s\"]+)\}")
_DATE_PLACEHOLDER = re.compile(r"\{date(?:([+-])(\d{1,3}))?\}")
_WEEKDAY_PLACEHOLDER = re.compile(r"\{(next|this)-(mon|tue|wed|thu|fri|sat|sun)(?:\+(\d{1,3}))?\}")
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _date_for(match: re.Match, today) -> str:
    sign, days = match.group(1), int(match.group(2) or 0)
    return (today + timedelta(days=-days if sign == "-" else days)).isoformat()


# {dom-25}: the next 25th on or after today (this month's if it hasn't
# passed yet, else next month's) -- the rule the extraction prompt states
# for "the 25th" / "25 tarikh". Only 1..28, so every month has that day.
_DOM_PLACEHOLDER = re.compile(r"\{dom-(\d{1,2})\}")
_MAX_DOM = 28


def _dom_ok(token: str) -> bool:
    m = _DOM_PLACEHOLDER.fullmatch(token)
    return bool(m) and 1 <= int(m.group(1)) <= _MAX_DOM


def _dom_for(match: re.Match, today) -> str:
    day = int(match.group(1))
    if today.day <= day:
        return today.replace(day=day).isoformat()
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return today.replace(year=year, month=month, day=day).isoformat()


def _weekday_for(match: re.Match, today) -> str:
    kind, name, extra = match.group(1), match.group(2), int(match.group(3) or 0)
    ahead = (_WEEKDAYS.index(name) - today.weekday()) % 7
    if ahead == 0 and kind == "next":
        ahead = 7
    return (today + timedelta(days=ahead + extra)).isoformat()


def fill(value, tag: str, today=None, now=None):
    """Replace the placeholders above in strings, lists and dicts. `today`
    (a date) or `now` (a datetime) pin the clock for tests."""
    if now is None:
        now = datetime.now(IST)
        if today is not None:
            now = now.replace(year=today.year, month=today.month, day=today.day)
    if today is None:
        today = now.date()
    if isinstance(value, str):
        value = value.replace("{tag}", tag)
        value = value.replace("{past-time}", f"{max(now.hour - 2, 0):02d}:00")
        value = _WEEKDAY_PLACEHOLDER.sub(lambda m: _weekday_for(m, today), value)
        value = _DOM_PLACEHOLDER.sub(lambda m: _dom_for(m, today), value)
        return _DATE_PLACEHOLDER.sub(lambda m: _date_for(m, today), value)
    if isinstance(value, list):
        return [fill(v, tag, today, now) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, tag, today, now) for k, v in value.items()}
    return value


# ---------------------------------------------------------------- data safety

def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)


def data_is_clean() -> tuple[bool, str]:
    # Only tracked files matter. Untracked runtime folders (data/cache/,
    # data/animal_registration_intakes/) are created by the app itself.
    res = _git("status", "--porcelain", "--untracked-files=no", "--", "data")
    if res.returncode != 0:
        return False, res.stderr.strip() or "git status failed"
    return res.stdout.strip() == "", res.stdout.strip()


def restore_data() -> None:
    _git("checkout", "--", "data")


def remove_eval_intakes(tag: str) -> int:
    """Delete registration drafts made by this run (session_id starts with eval-<tag>-).

    Drafts from real use or older tests are never touched.
    """
    removed = 0
    if not INTAKES_DIR.is_dir():
        return 0
    prefix = f"eval-{tag}-"
    for path in INTAKES_DIR.glob("*.json"):
        try:
            sid = str(json.loads(path.read_text(encoding="utf-8")).get("session_id", ""))
        except (OSError, ValueError, AttributeError):
            continue
        if sid.startswith(prefix):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def git_commit() -> str:
    sha = _git("rev-parse", "--short", "HEAD").stdout.strip() or "unknown"
    dirty = _git("status", "--porcelain", "--untracked-files=no", "--", ".").stdout.strip()
    return sha + ("-dirty" if dirty else "")


def _count_items(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list)]
        return sum(len(v) for v in lists) if lists else len(data)
    return 0


def snapshot_counts(conv: dict) -> dict:
    counts = {}
    for chk in conv.get("data_checks", []):
        if chk.get("grew"):
            p = DATA_DIR / chk["file"]
            counts[chk["file"]] = _count_items(p) if p.exists() else 0
    return counts


def run_data_checks(conv: dict, before: dict) -> list[dict]:
    out = []
    for chk in conv.get("data_checks", []):
        p = DATA_DIR / chk["file"]
        if not p.exists():
            out.append({"name": f"data:{chk['file']}", "ok": False, "detail": "file missing"})
            continue
        if "contains" in chk:
            ok = chk["contains"] in p.read_text(encoding="utf-8")
            out.append({"name": f"data:{chk['file']}", "ok": ok, "detail": f"contains {chk['contains']!r}"})
        if chk.get("grew"):
            now = _count_items(p)
            was = before.get(chk["file"], 0)
            out.append({"name": f"data:{chk['file']}", "ok": now > was, "detail": f"items {was} -> {now}"})
    return out


# ---------------------------------------------------------------- HTTP

def server_reachable(base_url: str) -> bool:
    u = urlparse(base_url)
    try:
        with socket.create_connection((u.hostname, u.port or 80), timeout=3):
            return True
    except OSError:
        return False


def chat_turn(base_url: str, farmer_id: str, session_id: str, text: str, language: str,
              timeout: float) -> tuple[dict | None, float, str | None, bool]:
    """POST one turn. Returns (json, ms, error, is_connection_error)."""
    url = f"{base_url.rstrip('/')}/farmers/{farmer_id}/chat/turn"
    body = json.dumps({"session_id": session_id, "text": text, "language": language,
                       "include_audio": False}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data, (time.perf_counter() - t0) * 1000, None, False
    except urllib.error.HTTPError as e:
        ms = (time.perf_counter() - t0) * 1000
        detail = e.read().decode("utf-8", "replace")[:300]
        return None, ms, f"HTTP {e.code}: {detail}", False
    except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError) as e:
        ms = (time.perf_counter() - t0) * 1000
        return None, ms, f"connection: {e}", True


# ---------------------------------------------------------------- running

class ServerDown(RuntimeError):
    pass


def run_conversation(conv: dict, *, base_url: str, tag: str, rep: int, timeout: float,
                     conn_errors: list[int]) -> dict:
    conv = fill(conv, tag)
    session_id = f"eval-{tag}-{conv['id']}-r{rep}"
    before = snapshot_counts(conv)
    turns_out = []
    for i, turn in enumerate(conv["turns"], 1):
        data, ms, err, is_conn = chat_turn(base_url, conv["farmer_id"], session_id,
                                           turn["user"], conv["language"], timeout)
        conn_errors[0] = conn_errors[0] + 1 if is_conn else 0
        is_5xx = bool(err) and err.startswith("HTTP 5")
        conn_errors[1] = conn_errors[1] + 1 if is_5xx else 0
        agent = (data or {}).get("agent")
        reply = (data or {}).get("reply_text") or ""
        checks = check_turn(turn.get("expect", {}), agent=agent, reply=reply, ms=ms,
                            language=conv["language"], error=err, user_text=turn["user"])
        turns_out.append({
            "turn": i, "user": turn["user"], "expect": turn.get("expect", {}),
            "agent": agent, "reply": reply, "ms": round(ms), "error": err,
            "checks": checks, "passed": turn_passed(checks),
        })
        if conn_errors[0] >= MAX_CONN_ERRORS_IN_A_ROW:
            raise ServerDown(f"{MAX_CONN_ERRORS_IN_A_ROW} connection errors in a row. Is the API server running?")
        if conn_errors[1] >= MAX_SERVER_ERRORS_IN_A_ROW:
            raise ServerDown(f"{MAX_SERVER_ERRORS_IN_A_ROW} server errors (HTTP 5xx) in a row. "
                             "Check the server terminal for the error (internet, AWS keys, Bedrock).")
        if err:  # later turns depend on this one, so stop the conversation here
            break
    data_checks = run_data_checks(conv, before) if len(turns_out) == len(conv["turns"]) else []
    passed = (len(turns_out) == len(conv["turns"])
              and all(t["passed"] for t in turns_out)
              and all(c["ok"] for c in data_checks))
    return {
        "id": conv["id"], "rep": rep, "layer": conv["layer"], "language": conv["language"],
        "title": conv.get("title", ""), "session_id": session_id, "passed": passed,
        "turns": turns_out, "data_checks": data_checks,
    }


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(p / 100 * (len(values) - 1))))
    return values[k]


def summarize(results: list[dict]) -> dict:
    def rate(items):
        return {"passed": sum(1 for r in items if r["passed"]), "total": len(items)}

    by = lambda key: {k: rate([r for r in results if r[key] == k])
                      for k in sorted({r[key] for r in results})}
    turns = [t for r in results for t in r["turns"]]
    lat: dict[str, list[float]] = {}
    for t in turns:
        if not t["error"]:
            lat.setdefault(t["expect"].get("agent") or t["agent"] or "?", []).append(t["ms"])
    all_ms = [t["ms"] for t in turns if not t["error"]]
    latency = {a: {"n": len(v), "p50": round(statistics.median(v)), "p90": round(_pct(v, 90)),
                   "max": round(max(v))} for a, v in sorted(lat.items())}
    if all_ms:
        latency["ALL"] = {"n": len(all_ms), "p50": round(statistics.median(all_ms)),
                          "p90": round(_pct(all_ms, 90)), "max": round(max(all_ms))}
    return {
        "conversations": rate(results),
        "turns": {"passed": sum(1 for t in turns if t["passed"]), "total": len(turns)},
        "by_layer": by("layer"),
        "by_language": by("language"),
        "latency_ms": latency,
        "errors": sum(1 for t in turns if t["error"]),
    }


def print_report(run: dict) -> None:
    s = run["summary"]
    c, t = s["conversations"], s["turns"]
    print()
    print(f"Run {run['run_id']}  commit {run['git_commit']}")
    print(f"Conversations passed: {c['passed']}/{c['total']}   Turns passed: {t['passed']}/{t['total']}"
          f"   Errors: {s['errors']}")
    print("By layer:    " + "  ".join(f"L{k}: {v['passed']}/{v['total']}" for k, v in s["by_layer"].items()))
    print("By language: " + "  ".join(f"{k}: {v['passed']}/{v['total']}" for k, v in s["by_language"].items()))
    print("Latency (ms)       n     p50     p90     max")
    for a, v in s["latency_ms"].items():
        print(f"  {a:<24}{v['n']:>4}{v['p50']:>8}{v['p90']:>8}{v['max']:>8}")
    failed = [r for r in run["results"] if not r["passed"]]
    if failed:
        print("\nFailed:")
        for r in failed:
            bad = next((tt for tt in r["turns"] if not tt["passed"]), None)
            if bad:
                why = "; ".join(f"{ch['name']}: {ch['detail']}" for ch in bad["checks"] if not ch["ok"])
                print(f"  {r['id']} (r{r['rep']}) turn {bad['turn']}: {why}")
                print(f"      reply: {bad['reply'][:140]!r}")
            else:
                why = "; ".join(f"{ch['name']}: {ch['detail']}" for ch in r["data_checks"] if not ch["ok"])
                print(f"  {r['id']} (r{r['rep']}) data: {why or 'conversation stopped early'}")
    print(f"\nSaved: {run['_path']}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="Run Chocolate eval conversations.")
    ap.add_argument("--base-url", default="http://127.0.0.1:8001")
    ap.add_argument("--layer", type=int, action="append", help="layer number (repeatable)")
    ap.add_argument("--lang", action="append", help="language like hi-IN (repeatable)")
    ap.add_argument("--only", action="append", help="conversation id (repeatable)")
    ap.add_argument("--repeat", type=int, default=1, help="runs per conversation")
    ap.add_argument("--timeout", type=float, default=240, help="seconds per turn")
    ap.add_argument("--no-reset", action="store_true",
                    help="skip the clean-data check and data restore (not recommended)")
    ap.add_argument("--validate", action="store_true", help="only check the JSON files and exit")
    args = ap.parse_args(argv)

    convs = load_conversations(args.layer)
    problems = validate_conversations(convs)
    if problems:
        print("Conversation file problems:\n  " + "\n  ".join(problems))
        return 2
    if args.lang:
        convs = [c for c in convs if c["language"] in args.lang]
    if args.only:
        convs = [c for c in convs if c["id"] in args.only]
    if args.validate:
        print(f"OK: {len(convs)} conversations, {sum(len(c['turns']) for c in convs)} turns")
        return 0
    if not convs:
        print("No conversations match the filters.")
        return 2

    if not server_reachable(args.base_url):
        print(f"API server not reachable at {args.base_url}. Start it first:\n"
              "  uvicorn services.api_service.main:app --host 127.0.0.1 --port 8001")
        return 2

    if not args.no_reset:
        clean, detail = data_is_clean()
        if not clean:
            print("data/ has local changes, so the run would not start from a known state:\n"
                  f"{detail}\nCommit or stash them, or run `git checkout -- data` if they are leftovers.")
            return 2

    # Read-only conversations first (all repeats), the ones that save data last.
    # So a booking or registration in repeat 1 can never leak into a count
    # question of repeat 2, even if a server-side cache misses the data restore.
    plan = sorted(((c, rep) for c in convs for rep in range(1, args.repeat + 1)),
                  key=lambda cr: (bool(cr[0].get("mutates")), cr[1], cr[0]["layer"], cr[0]["id"]))
    started = datetime.now()
    run_id = started.strftime("%Y%m%d-%H%M%S")
    tag = started.strftime("%m%d%H%M%S")
    RESULTS_DIR.mkdir(exist_ok=True)

    total = len(convs) * args.repeat
    print(f"Running {len(convs)} conversations x {args.repeat} = {total} against {args.base_url}")
    results: list[dict] = []
    conn_errors = [0, 0]  # [connection errors in a row, HTTP 5xx in a row]
    aborted = None
    n = 0
    try:
        for conv, rep in plan:
            n += 1
            res = run_conversation(conv, base_url=args.base_url, tag=tag, rep=rep,
                                   timeout=args.timeout, conn_errors=conn_errors)
            results.append(res)
            secs = sum(t["ms"] for t in res["turns"]) / 1000
            print(f"[{n}/{total}] {'PASS' if res['passed'] else 'FAIL'}  {res['id']:<12} r{rep} "
                  f"{res['language']:<6} {secs:6.1f}s  {res['title']}")
            if conv.get("mutates") and not args.no_reset:
                restore_data()
    except ServerDown as e:
        aborted = str(e)
        print(f"\nStopped: {aborted}")
    except KeyboardInterrupt:
        aborted = "interrupted"
        print("\nStopped by user.")
    finally:
        if not args.no_reset:
            restore_data()
            removed = remove_eval_intakes(tag)
            if removed:
                print(f"Removed {removed} registration draft file(s) made by this run.")

    run = {
        "run_id": run_id,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "base_url": args.base_url,
        "filters": {"layer": args.layer, "lang": args.lang, "only": args.only, "repeat": args.repeat},
        "aborted": aborted,
        "summary": summarize(results),
        "results": results,
    }
    path = RESULTS_DIR / f"{run_id}.json"
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    run["_path"] = str(path.relative_to(REPO_ROOT))
    print_report(run)
    ok = not aborted and all(r["passed"] for r in results)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
