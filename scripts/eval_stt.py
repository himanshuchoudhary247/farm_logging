#!/usr/bin/env python3
"""STT model comparison: AWS Transcribe vs Voxtral (Bedrock), 6 languages.

Audio corpus is synthesized via gTTS (NOT real farmer speech — Polly can't
produce kn/ta/te/ml at all, see docs/model-evaluation-2026-09-11.md and this
script's own findings). Results measure relative STT accuracy on a
consistent, repeatable synthetic voice, not real-world WER. Treat as a
signal for choosing between the two candidates, not a production accuracy
guarantee.

Pipeline per test case:
  1. gTTS synthesizes the reference sentence -> mp3
  2. ffmpeg converts to 16kHz mono PCM wav (Bedrock Converse audio + Transcribe both want this)
  3a. AWS Transcribe: upload wav to S3, start job, poll, fetch transcript
  3b. Voxtral: Converse API with an audio content block, ask for verbatim transcript
  4. Compare each transcript to the reference sentence (normalized char overlap,
     since word-tokenization doesn't apply cleanly across these scripts)

Usage:
    python scripts/eval_stt.py                  # all 6 languages, default 10 sentences/lang
    python scripts/eval_stt.py --lang kn,ml      # subset
    python scripts/eval_stt.py --n 5             # fewer sentences per language, faster
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
import yaml
from gtts import gTTS

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

REGION = "ap-south-1"
S3_BUCKET = "farmer-chat-audio-bucket-198799425726"
S3_PREFIX = "stt-eval/"

GTTS_LANG = {"kn": "kn", "hi": "hi", "ta": "ta", "te": "te", "ml": "ml", "en": "en"}
TRANSCRIBE_LANG_CODE = {"kn": "kn-IN", "hi": "hi-IN", "ta": "ta-IN", "te": "te-IN", "ml": "ml-IN", "en": "en-IN"}

VOXTRAL_MODEL = "mistral.voxtral-small-24b-2507"


def load_sentences(lang: str, n: int) -> List[str]:
    """Pull first N unique sentences for a language from the golden extraction
    set (kn/hi/ta/te) or conversations set (en/ml, and as a backfill)."""
    sentences: List[str] = []

    golden_path = REPO_ROOT / "tests" / "eval" / "golden_extraction.yaml"
    if golden_path.exists():
        with open(golden_path, encoding="utf-8") as f:
            rows = yaml.safe_load(f) or []
        for row in rows:
            if row.get("lang", "").split("-")[0] == lang:
                sentences.append(row["text"])

    if len(sentences) < n:
        conv_path = REPO_ROOT / "tests" / "eval" / "conversations.yaml"
        with open(conv_path, encoding="utf-8") as f:
            convs = yaml.safe_load(f) or []
        for conv in convs:
            if conv.get("lang", "").split("-")[0] == lang:
                for turn in conv["turns"]:
                    text = turn["user"]
                    if text not in sentences:
                        sentences.append(text)
                if len(sentences) >= n:
                    break

    # de-dupe, cap
    seen = set()
    out = []
    for s in sentences:
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= n:
            break
    return out


def synthesize_gtts_wav(text: str, lang: str) -> bytes:
    """gTTS -> mp3 bytes -> ffmpeg -> 16kHz mono PCM wav bytes."""
    buf = io.BytesIO()
    gTTS(text=text, lang=GTTS_LANG[lang]).write_to_fp(buf)
    mp3_bytes = buf.getvalue()

    with tempfile.NamedTemporaryFile(suffix=".mp3") as mp3_f, tempfile.NamedTemporaryFile(suffix=".wav") as wav_f:
        mp3_f.write(mp3_bytes)
        mp3_f.flush()
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_f.name, "-ar", "16000", "-ac", "1", "-f", "wav", wav_f.name],
            check=True, capture_output=True,
        )
        wav_f.seek(0)
        return wav_f.read()


def normalized_overlap(reference: str, hypothesis: str) -> float:
    """Character-level overlap ratio. Word-tokenization doesn't apply cleanly
    across Latin/Devanagari/Dravidian scripts with different whitespace
    conventions, so this uses a simple normalized character bag comparison —
    coarse, but consistent across all 6 languages."""
    ref = "".join(reference.split()).strip()
    hyp = "".join((hypothesis or "").split()).strip()
    if not ref:
        return 1.0 if not hyp else 0.0
    if not hyp:
        return 0.0
    # Longest common subsequence ratio (cheap, no extra deps)
    m, n = len(ref), len(hyp)
    if m * n > 4_000_000:  # guard against pathological length
        common = len(set(ref) & set(hyp))
        return common / len(set(ref) | set(hyp))
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[m][n]
    return (2 * lcs) / (m + n)


def transcribe_via_aws(wav_bytes: bytes, lang: str) -> Dict[str, Any]:
    s3 = boto3.client("s3", region_name=REGION)
    tr = boto3.client("transcribe", region_name=REGION)

    key = f"{S3_PREFIX}{uuid.uuid4()}.wav"
    t0 = time.time()
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=wav_bytes)
    s3_uri = f"s3://{S3_BUCKET}/{key}"

    job_name = f"stt-eval-{uuid.uuid4().hex[:16]}"
    tr.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": s3_uri},
        MediaFormat="wav",
        LanguageCode=TRANSCRIBE_LANG_CODE[lang],
    )

    delay = 0.3
    while True:
        status = tr.get_transcription_job(TranscriptionJobName=job_name)
        state = status["TranscriptionJob"]["TranscriptionJobStatus"]
        if state in ("COMPLETED", "FAILED"):
            break
        if time.time() - t0 > 60:
            raise TimeoutError("transcribe job timeout")
        time.sleep(delay)
        delay = min(delay * 1.4, 1.5)

    ms = (time.time() - t0) * 1000
    s3.delete_object(Bucket=S3_BUCKET, Key=key)

    if state == "FAILED":
        reason = status["TranscriptionJob"].get("FailureReason", "unknown")
        return {"transcript": "", "ms": ms, "error": reason}

    import requests
    uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
    data = requests.get(uri, timeout=10).json()
    transcript = data["results"]["transcripts"][0]["transcript"]
    return {"transcript": transcript, "ms": ms, "error": None}


def transcribe_via_voxtral(wav_bytes: bytes, lang: str) -> Dict[str, Any]:
    client = boto3.client("bedrock-runtime", region_name=REGION)
    t0 = time.time()
    try:
        resp = client.converse(
            modelId=VOXTRAL_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"audio": {"format": "wav", "source": {"bytes": wav_bytes}}},
                    {"text": (
                        "Transcribe this audio verbatim in the SAME language and SAME script "
                        "the speaker used. Do not translate to English. Do not transliterate "
                        "into a different script (e.g. do not write Kannada speech in "
                        "Devanagari). Return ONLY the raw transcript text, nothing else."
                    )},
                ],
            }],
            inferenceConfig={"maxTokens": 300, "temperature": 0},
        )
        ms = (time.time() - t0) * 1000
        content = resp.get("output", {}).get("message", {}).get("content", [])
        text = content[0].get("text", "") if content else ""
        return {"transcript": text.strip(), "ms": ms, "error": None}
    except Exception as exc:
        ms = (time.time() - t0) * 1000
        return {"transcript": "", "ms": ms, "error": str(exc)[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="kn,hi,ta,te,ml,en")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", default=str(REPO_ROOT / "data" / "eval" / "runs" / "stt_comparison.jsonl"))
    args = ap.parse_args()

    langs = [x.strip() for x in args.lang.split(",")]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    with open(out_path, "w", encoding="utf-8") as out_f:
        for lang in langs:
            sentences = load_sentences(lang, args.n)
            print(f"\n=== {lang} — {len(sentences)} sentences ===")
            for i, text in enumerate(sentences, 1):
                print(f"  [{i}/{len(sentences)}] {text[:40]!r}", end=" ", flush=True)
                try:
                    wav = synthesize_gtts_wav(text, lang)
                except Exception as exc:
                    print(f"gTTS/ffmpeg FAILED: {exc}")
                    continue

                aws_r = transcribe_via_aws(wav, lang)
                vox_r = transcribe_via_voxtral(wav, lang)

                aws_score = normalized_overlap(text, aws_r["transcript"])
                vox_score = normalized_overlap(text, vox_r["transcript"])

                row = {
                    "lang": lang, "reference": text,
                    "aws_transcribe": aws_r, "aws_score": round(aws_score, 3),
                    "voxtral": vox_r, "voxtral_score": round(vox_score, 3),
                }
                results.append(row)
                out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                out_f.flush()
                print(f"aws={aws_score:.2f}({aws_r['ms']:.0f}ms) voxtral={vox_score:.2f}({vox_r['ms']:.0f}ms)")

    # summary
    from collections import defaultdict
    by_lang = defaultdict(lambda: {"aws": [], "vox": [], "aws_ms": [], "vox_ms": []})
    for r in results:
        by_lang[r["lang"]]["aws"].append(r["aws_score"])
        by_lang[r["lang"]]["vox"].append(r["voxtral_score"])
        by_lang[r["lang"]]["aws_ms"].append(r["aws_transcribe"]["ms"])
        by_lang[r["lang"]]["vox_ms"].append(r["voxtral"]["ms"])

    print("\n\n=== SUMMARY (char-overlap score, 0-1; higher is better) ===")
    print(f"{'lang':<6}{'aws_avg':>10}{'vox_avg':>10}{'aws_ms':>10}{'vox_ms':>10}")
    for lang in langs:
        d = by_lang[lang]
        if not d["aws"]:
            continue
        aws_avg = sum(d["aws"]) / len(d["aws"])
        vox_avg = sum(d["vox"]) / len(d["vox"])
        aws_ms = sum(d["aws_ms"]) / len(d["aws_ms"])
        vox_ms = sum(d["vox_ms"]) / len(d["vox_ms"])
        print(f"{lang:<6}{aws_avg:>10.3f}{vox_avg:>10.3f}{aws_ms:>10.0f}{vox_ms:>10.0f}")

    print(f"\nper-case results: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
