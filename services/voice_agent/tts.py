import hashlib
import logging
import os
import time
from pathlib import Path
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


def _tts_cache_dir() -> Path:
    override = os.getenv("TTS_CACHE_DIR")
    if override:
        return Path(override)
    from storage import get_data_dir
    return get_data_dir() / "tts_cache"


def _tts_cache_key(text: str, voice_id: str, language_code: str, engine: str) -> str:
    payload = f"{voice_id}|{language_code}|{engine}|{text}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def _tts_cache_read(cache_key: str) -> Optional[bytes]:
    if os.getenv("TTS_CACHE_DISABLED", "").lower() in {"1", "true", "yes", "on"}:
        return None
    try:
        path = _tts_cache_dir() / f"{cache_key}.mp3"
        if path.exists():
            return path.read_bytes()
    except Exception as exc:
        _log.debug("tts cache read failed: %s", exc)
    return None


def _tts_cache_write(cache_key: str, audio: bytes) -> None:
    if os.getenv("TTS_CACHE_DISABLED", "").lower() in {"1", "true", "yes", "on"}:
        return
    try:
        cache_dir = _tts_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{cache_key}.mp3").write_bytes(audio)
    except Exception as exc:
        _log.debug("tts cache write failed: %s", exc)


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
        cache_key = _tts_cache_key(text, v_id, lc, eng)
        cached = _tts_cache_read(cache_key)
        if cached is not None:
            _log.info("LATENCY tts cache_hit voice=%s ms=%.0f bytes=%d", v_id, (time.time() - t0) * 1000, len(cached))
            return cached, None
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
            _tts_cache_write(cache_key, audio)
            _log.info("LATENCY tts voice=%s ms=%.0f bytes=%d", v_id, (time.time() - t0) * 1000, len(audio))
            return audio, None
        except ClientError:
            continue

    _log.info("LATENCY tts failed after %.0fms", (time.time() - t0) * 1000)
    return None, "polly_unsupported_language"
