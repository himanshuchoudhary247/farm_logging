import logging
import os
import time
from typing import Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

_log = logging.getLogger("tts")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_POLLY_CONFIG = Config(
    max_pool_connections=10,
    connect_timeout=2,
    read_timeout=10,
    retries={"max_attempts": 2, "mode": "adaptive"},
)

_polly_client = None


def _get_polly_client():
    global _polly_client
    if _polly_client is None:
        _polly_client = boto3.client(
            "polly",
            region_name=os.getenv("AWS_REGION", "ap-south-1"),
            config=_POLLY_CONFIG,
        )
    return _polly_client


def _infer_lang(text: str) -> str:
    t = str(text or "")
    if any("\u0900" <= ch <= "\u097F" for ch in t):
        return "hi"
    return "en"


def synthesize_speech(text: str, target_lang: Optional[str] = None) -> Tuple[Optional[bytes], Optional[str]]:
    if not text or not text.strip():
        return None, None

    enabled = os.getenv("TTS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None, None

    region = os.getenv("AWS_REGION", "ap-south-1")
    lang = (target_lang or _infer_lang(text)).strip().lower()

    voice_hi = os.getenv("AWS_POLLY_VOICE_HI", "Aditi")
    voice_en = os.getenv("AWS_POLLY_VOICE_EN", "Raveena")
    voice_kn = os.getenv("AWS_POLLY_VOICE_KN", voice_hi)
    voice_te = os.getenv("AWS_POLLY_VOICE_TE", voice_hi)
    if lang == "hi":
        voice_id = voice_hi
        language_code = os.getenv("AWS_POLLY_LANGUAGE_CODE_HI", "hi-IN")
    elif lang == "kn":
        voice_id = voice_kn
        language_code = os.getenv("AWS_POLLY_LANGUAGE_CODE_KN", "kn-IN")
    elif lang == "te":
        voice_id = voice_te
        language_code = os.getenv("AWS_POLLY_LANGUAGE_CODE_TE", "te-IN")
    else:
        voice_id = voice_en
        language_code = os.getenv("AWS_POLLY_LANGUAGE_CODE_EN", "en-IN")

    engine = os.getenv("AWS_POLLY_ENGINE", "standard")

    client = _get_polly_client()

    fallback_chain = [
        (voice_id, language_code, engine),
    ]
    if lang in ("kn", "te"):
        fallback_chain.append((voice_hi, os.getenv("AWS_POLLY_LANGUAGE_CODE_HI", "hi-IN"), "standard"))
        fallback_chain.append((voice_en, os.getenv("AWS_POLLY_LANGUAGE_CODE_EN", "en-IN"), "standard"))

    t0 = time.time()
    for v_id, lc, eng in fallback_chain:
        try:
            resp = client.synthesize_speech(
                Text=text,
                OutputFormat="mp3",
                VoiceId=v_id,
                LanguageCode=lc,
                Engine=eng,
            )
            stream = resp.get("AudioStream")
            if stream is None:
                continue
            audio = stream.read()
            _log.info("LATENCY tts voice=%s ms=%.0f bytes=%d", v_id, (time.time() - t0) * 1000, len(audio))
            return audio, None
        except ClientError:
            continue

    _log.info("LATENCY tts failed after %.0fms", (time.time() - t0) * 1000)
    return None, "polly_unsupported_language"
