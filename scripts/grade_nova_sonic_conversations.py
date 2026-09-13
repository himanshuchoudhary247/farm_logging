"""LLM-judge grading pass over data/eval/runs/nova_sonic_conversations.jsonl.

`got_reply` (did any reply text come back at all) doesn't measure whether
the turn was actually handled correctly — ASR output is free-form/romanized
across languages, not exact-match comparable to the original text. This
script asks DeepSeek V3 (same model already validated for extraction this
session) to judge, per turn:
  - asr_correct: did the transcript preserve the meaning of what the farmer
    said (romanization/spelling drift is fine; meaning drift/mishearing
    is not)
  - reply_relevant: does the reply meaningfully engage with that meaning
    (a hallucinated response built on a mishearing is not relevant even if
    fluent)

Turn passes only if both are true. Conversation passes only if every turn
in it passes (same "conversation-pass" definition used by the text
extraction eval, scripts/eval_conversations.py).

Output: data/eval/runs/nova_sonic_conversations.graded.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.llm_service.bedrock_adapter import BedrockTextAdapter, TaskTier
IN_PATH = ROOT / "data" / "eval" / "runs" / "nova_sonic_conversations.jsonl"
OUT_PATH = ROOT / "data" / "eval" / "runs" / "nova_sonic_conversations.graded.jsonl"

JUDGE_TOOL_SPEC = {
    "name": "grade_turn",
    "description": "Grade one Nova Sonic voice-agent turn for ASR accuracy and reply relevance.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "asr_correct": {
                    "type": "boolean",
                    "description": "True if the ASR transcript preserves the meaning of what the farmer said. Romanization/spelling drift is fine (e.g. 'jvara' for 'ಜ್ವರ' is correct). Meaning drift, mishearing as an unrelated word, or cross-language contamination is NOT correct.",
                },
                "reply_relevant": {
                    "type": "boolean",
                    "description": "True if the assistant reply meaningfully engages with the farmer's actual meaning (as given by user_text, the ground truth). A fluent but hallucinated reply built on a mishearing is NOT relevant. An empty reply is NOT relevant.",
                },
                "reasoning": {"type": "string", "description": "One short sentence."},
            },
            "required": ["asr_correct", "reply_relevant", "reasoning"],
        }
    },
}

JUDGE_SYSTEM = """You are grading a voice-agent transcript for a farmer livestock assistant app.
You will see: the farmer's actual message (ground truth, in its native language),
the ASR transcript the speech model produced, and the reply the model gave.
Judge asr_correct and reply_relevant strictly against the ground-truth meaning
of user_text, not against how fluent the reply sounds. Call grade_turn."""


def grade_turn(row: dict) -> dict:
    adapter = BedrockTextAdapter(task=TaskTier.EXTRACTION)
    prompt = (
        f"user_text (ground truth, {row['lang']}): {row['user_text']}\n"
        f"asr_transcript: {row['asr_transcript']}\n"
        f"reply_text: {row['reply_text']}"
    )
    result = adapter.converse_with_tool(
        messages=[{"role": "user", "content": prompt}],
        tool_spec=JUDGE_TOOL_SPEC,
        system=JUDGE_SYSTEM,
        tool_choice_name="grade_turn",
    )
    tool_input = result.get("tool_input") or {}
    return {
        "asr_correct": bool(tool_input.get("asr_correct")),
        "reply_relevant": bool(tool_input.get("reply_relevant")),
        "reasoning": tool_input.get("reasoning", ""),
    }


def main() -> None:
    rows = [json.loads(l) for l in IN_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    graded = []
    for i, row in enumerate(rows, 1):
        if row.get("error") or not row.get("asr_transcript"):
            verdict = {"asr_correct": False, "reply_relevant": False, "reasoning": "no ASR transcript / error"}
        else:
            try:
                verdict = grade_turn(row)
            except Exception as exc:
                verdict = {"asr_correct": False, "reply_relevant": False, "reasoning": f"judge error: {exc}"}
        row = {**row, **verdict, "turn_pass": verdict["asr_correct"] and verdict["reply_relevant"]}
        graded.append(row)
        print(f"[{i}/{len(rows)}] {row['conv_id']} turn{row['turn_idx']} lang={row['lang']} "
              f"asr={verdict['asr_correct']} reply={verdict['reply_relevant']} :: {verdict['reasoning']}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for r in graded:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_lang: dict[str, dict] = {}
    by_conv: dict[str, list] = {}
    for r in graded:
        s = by_lang.setdefault(r["lang"], {"turns": 0, "pass": 0})
        s["turns"] += 1
        s["pass"] += int(r["turn_pass"])
        by_conv.setdefault(r["conv_id"], []).append(r["turn_pass"])

    conv_lang = {r["conv_id"]: r["lang"] for r in graded}
    conv_pass_by_lang: dict[str, dict] = {}
    for conv_id, passes in by_conv.items():
        lang = conv_lang[conv_id]
        s = conv_pass_by_lang.setdefault(lang, {"convs": 0, "pass": 0})
        s["convs"] += 1
        s["pass"] += int(all(passes))

    print(f"\nwrote {len(graded)} graded rows to {OUT_PATH}")
    print("\n=== turn-level accuracy ===")
    print(f"{'lang':8} {'turns':>6} {'pass':>6} {'acc':>7}")
    for lang in sorted(by_lang):
        s = by_lang[lang]
        print(f"{lang:8} {s['turns']:>6} {s['pass']:>6} {s['pass']/s['turns']*100:>6.1f}%")

    print("\n=== conversation-level accuracy (all turns must pass) ===")
    print(f"{'lang':8} {'convs':>6} {'pass':>6} {'acc':>7}")
    for lang in sorted(conv_pass_by_lang):
        s = conv_pass_by_lang[lang]
        print(f"{lang:8} {s['convs']:>6} {s['pass']:>6} {s['pass']/s['convs']*100:>6.1f}%")


if __name__ == "__main__":
    main()
