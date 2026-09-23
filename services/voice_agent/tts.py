import hashlib
import io
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


def _polly_voice_for(lang: str) -> Tuple[str, str]:
    """Voice/language-code for a language Polly is configured to support.
    Env AWS_POLLY_VOICE_<LANG> / AWS_POLLY_LANGUAGE_CODE_<LANG> override per
    language; falls back to a sane default rather than a hardcoded per-
    language table, so adding a language to polly_languages in
    config/llm.yaml needs no code change."""
    upper = lang.upper()
    default_voice = "Aditi" if lang == "hi" else "Raveena"
    voice_id = os.getenv(f"AWS_POLLY_VOICE_{upper}", default_voice)
    language_code = os.getenv(f"AWS_POLLY_LANGUAGE_CODE_{upper}", f"{lang}-IN")
    return voice_id, language_code


def _synthesize_polly(text: str, lang: str) -> Tuple[Optional[bytes], Optional[str]]:
    voice_id, language_code = _polly_voice_for(lang)
    engine = os.getenv("AWS_POLLY_ENGINE", "standard")
    cache_key = _tts_cache_key(text, voice_id, language_code, engine)
    cached = _tts_cache_read(cache_key)
    if cached is not None:
        _log.info("LATENCY tts provider=polly cache_hit voice=%s bytes=%d", voice_id, len(cached))
        return cached, None
    t0 = time.time()
    try:
        resp = _get_polly_client().synthesize_speech(
            Text=text, OutputFormat="mp3", VoiceId=voice_id,
            LanguageCode=language_code, Engine=engine,
        )
        stream = resp.get("AudioStream")
        if stream is None:
            return None, "polly_empty_stream"
        audio = stream.read()
        _tts_cache_write(cache_key, audio)
        _log.info("LATENCY tts provider=polly voice=%s ms=%.0f bytes=%d", voice_id, (time.time() - t0) * 1000, len(audio))
        return audio, None
    except ClientError as exc:
        _log.info("LATENCY tts provider=polly FAILED voice=%s ms=%.0f err=%s", voice_id, (time.time() - t0) * 1000, exc)
        return None, str(exc)


def _synthesize_gtts(text: str, lang: str) -> Tuple[Optional[bytes], Optional[str]]:
    cache_key = _tts_cache_key(text, "gtts", lang, "default")
    cached = _tts_cache_read(cache_key)
    if cached is not None:
        _log.info("LATENCY tts provider=gtts cache_hit lang=%s bytes=%d", lang, len(cached))
        return cached, None
    t0 = time.time()
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        gTTS(text=text, lang=lang).write_to_fp(buf)
        audio = buf.getvalue()
        _tts_cache_write(cache_key, audio)
        _log.info("LATENCY tts provider=gtts lang=%s ms=%.0f bytes=%d", lang, (time.time() - t0) * 1000, len(audio))
        return audio, None
    except Exception as exc:
        _log.info("LATENCY tts provider=gtts FAILED lang=%s ms=%.0f err=%s", lang, (time.time() - t0) * 1000, exc)
        return None, str(exc)


_PROVIDERS = {"aws-polly": _synthesize_polly, "gtts": _synthesize_gtts}


def synthesize_speech(text: str, target_lang: Optional[str] = None) -> Tuple[Optional[bytes], Optional[str]]:
    if not text or not text.strip():
        return None, None

    enabled = os.getenv("TTS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None, None

    proxy = os.getenv("LLM_PROXY_BASE_URL")
    if proxy:
        import base64
        import requests
        key = os.getenv("DEV_PROXY_API_KEY")
        resp = requests.post(
            f"{proxy}/proxy/tts",
            json={"text": text, "language": target_lang},
            headers={"X-Dev-Proxy-Key": key} if key else {},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        audio_b64 = body.get("audio_base64")
        return (base64.b64decode(audio_b64) if audio_b64 else None), body.get("error")

    lang = (target_lang or _infer_lang(text)).strip().lower()

    from services.llm_service.bedrock_adapter import get_tts_polly_languages, get_tts_fallback_provider

    polly_languages = get_tts_polly_languages()
    fallback_name = get_tts_fallback_provider()
    fallback_fn = _PROVIDERS.get(fallback_name, _synthesize_gtts)

    if lang in polly_languages:
        audio, err = _synthesize_polly(text, lang)
        if audio:
            return audio, None
        # Polly errored even for a supported language (throttling, transient
        # fault) — same generic fallback as an unsupported language, not a
        # special case.
    audio, err = fallback_fn(text, lang)
    if audio:
        return audio, None
    return None, err or "tts_failed"
