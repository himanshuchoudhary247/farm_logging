import asyncio
import os
import subprocess
import time
import logging
from typing import Optional
from botocore.config import Config
from botocore.exceptions import ClientError
import boto3


class TranscribeService:
    def __init__(self):
        self.client = boto3.client(
            "transcribe",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            config=Config(retries={"max_attempts": 5, "mode": "standard"}),
        )
        self.log = logging.getLogger("transcribe")

    def transcribe_file(
        self,
        s3_uri: str,
        job_name: Optional[str] = None,
        media_format: str = "wav",
        language_code: Optional[str] = None,
    ) -> str:
        job_name = job_name or f"farmer-chat-{int(time.time())}"

        self.log.info(f"Starting transcription job {job_name} for {s3_uri}")
        # Explicit language from the frontend selector skips IdentifyLanguage,
        # cutting ~1-2s of language-detection latency per turn.
        default_language_code = os.getenv("AWS_TRANSCRIBE_LANGUAGE_CODE", "en-IN")
        enable_multilingual = os.getenv("AWS_TRANSCRIBE_MULTILINGUAL", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        req = {
            "TranscriptionJobName": job_name,
            "Media": {"MediaFileUri": s3_uri},
            "MediaFormat": media_format,
        }

        if language_code:
            req["LanguageCode"] = language_code
        elif enable_multilingual:
            language_opts_raw = os.getenv("AWS_TRANSCRIBE_LANGUAGE_OPTIONS", "en-IN,hi-IN,kn-IN,te-IN")
            language_options = [x.strip() for x in language_opts_raw.split(",") if x.strip()]
            if language_options:
                req["IdentifyLanguage"] = True
                req["LanguageOptions"] = language_options
            else:
                req["LanguageCode"] = default_language_code
        else:
            req["LanguageCode"] = default_language_code

        self.client.start_transcription_job(
            **req,
        )

        # Exponential-backoff polling: 200ms -> 300 -> 450 -> capped at 1s.
        # Prior fixed 500ms sleep wasted ~500ms on jobs that completed under 1s.
        start = time.time()
        delay = 0.2
        while True:
            status = self.client.get_transcription_job(TranscriptionJobName=job_name)
            state = status["TranscriptionJob"]["TranscriptionJobStatus"]
            if state in ("COMPLETED", "FAILED"):
                break
            if time.time() - start > 300:
                raise TimeoutError("Transcription timed out")
            time.sleep(delay)
            delay = min(delay * 1.5, 1.0)

        if state == "FAILED":
            self.log.error(f"Transcription failed for {job_name}")
            raise RuntimeError("Transcription failed")

        uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]

        import requests

        self.log.info(f"Fetching transcript from {uri}")
        data = requests.get(uri, timeout=10).json()
        text = data["results"]["transcripts"][0]["transcript"]
        self.log.info(f"Transcript: {text[:100]}")
        return text


def _to_pcm16k_mono(audio_bytes: bytes) -> bytes:
    """Decode any container ffmpeg understands (wav/webm/mp3/mp4/ogg) to raw
    16kHz mono signed-16-bit PCM — what Transcribe Streaming requires.
    Input format is auto-detected by ffmpeg from the byte stream; no need to
    pass the upload's declared media_format, which is occasionally wrong."""
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"],
        input=audio_bytes, capture_output=True, check=True,
    )
    return proc.stdout


async def _transcribe_streaming_async(pcm_bytes: bytes, language_code: str) -> str:
    """AWS Transcribe Streaming: no S3 upload, no job-poll loop. Audio is
    sent over a bidirectional HTTP/2 stream and the final transcript arrives
    as soon as AWS finishes processing — measured ~700-900ms for short
    farmer utterances vs 8-12s for the batch job API (see
    docs/model-evaluation-2026-09-11.md, STT section, for the batch-mode
    measurement this replaces)."""
    from amazon_transcribe.client import TranscribeStreamingClient
    from amazon_transcribe.handlers import TranscriptResultStreamHandler
    from amazon_transcribe.model import TranscriptEvent

    client = TranscribeStreamingClient(region=os.getenv("AWS_REGION", "ap-south-1"))
    stream = await client.start_stream_transcription(
        language_code=language_code,
        media_sample_rate_hz=16000,
        media_encoding="pcm",
    )

    collected = {"text": ""}

    class _Handler(TranscriptResultStreamHandler):
        async def handle_transcript_event(self, transcript_event: TranscriptEvent):
            for result in transcript_event.transcript.results:
                if not result.is_partial:
                    for alt in result.alternatives:
                        collected["text"] = alt.transcript

    async def _write_chunks():
        chunk_size = 1024 * 8  # SDK max is 32KB per send_audio_event
        for i in range(0, len(pcm_bytes), chunk_size):
            await stream.input_stream.send_audio_event(audio_chunk=pcm_bytes[i:i + chunk_size])
        await stream.input_stream.end_stream()

    handler = _Handler(stream.output_stream)
    await asyncio.gather(_write_chunks(), handler.handle_events())
    return collected["text"]


def transcribe_audio_streaming(audio_bytes: bytes, language_code: str = "en-IN") -> str:
    """Sync wrapper around the async Transcribe Streaming client. Safe to
    call from a worker thread (e.g. via asyncio.to_thread from a FastAPI
    handler) since asyncio.run() opens its own event loop per call."""
    t0 = time.time()
    pcm_bytes = _to_pcm16k_mono(audio_bytes)
    t_decode = time.time()
    text = asyncio.run(_transcribe_streaming_async(pcm_bytes, language_code))
    t_transcribe = time.time()
    logging.getLogger("transcribe").info(
        "LATENCY transcribe_streaming total=%dms decode=%dms stream=%dms",
        round((t_transcribe - t0) * 1000),
        round((t_decode - t0) * 1000),
        round((t_transcribe - t_decode) * 1000),
    )
    return text


def _transcribe_local(audio_bytes: bytes) -> str:
    try:
        import tempfile
        import whisper

        model_name = os.getenv("WHISPER_MODEL", "base")
        model = whisper.load_model(model_name)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(audio_bytes)
            local_path = f.name

        # Force English for better accuracy in dev
        result = model.transcribe(local_path, language="en")
        return result.get("text", "").strip()
    except ImportError:
        raise RuntimeError("Whisper not installed. Run: pip install openai-whisper")


# ---- Orchestrator-friendly wrapper ----
def transcribe_audio(audio_bytes: bytes, media_format: str = "wav", language_code: Optional[str] = None) -> str:
    """
    End-to-end transcription using AWS:
    1. Save temp file
    2. Upload to S3
    3. Run Transcribe job
    4. Return text
    """
    # Auto dev mode: if not explicitly set, fallback to local unless AWS is fully configured
    mode = os.getenv("TRANSCRIBE_MODE")
    if not mode:
        if os.getenv("VOICE_S3_BUCKET"):
            mode = "aws"
        else:
            mode = "local"
    mode = mode.lower()

    # -------- Local (dev) mode using Whisper --------
    if mode == "local":
        return _transcribe_local(audio_bytes)

    # -------- AWS streaming mode (no S3, no job-poll loop) --------
    if mode == "aws-streaming":
        lang = language_code or os.getenv("AWS_TRANSCRIBE_LANGUAGE_CODE", "en-IN")
        return transcribe_audio_streaming(audio_bytes, language_code=lang)

    # -------- AWS (prod) mode --------
    import tempfile
    import uuid
    from services.voice_agent.s3_upload import upload_file_to_s3

    bucket = os.getenv("VOICE_S3_BUCKET")
    if not bucket:
        raise ValueError("VOICE_S3_BUCKET not set for AWS mode")

    t0 = time.time()
    # Step 1: save temp file
    suffix = "." + (media_format if media_format != "mpeg" else "mp3")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(audio_bytes)
        local_path = f.name

    # Step 2: upload to S3
    extension = media_format if media_format != "mpeg" else "mp3"
    key = f"voice-input/{uuid.uuid4()}.{extension}"
    s3_uri = upload_file_to_s3(local_path, bucket, key)
    t_s3 = time.time()

    # Step 3: transcribe
    service = TranscribeService()
    try:
        text = service.transcribe_file(s3_uri, media_format=media_format, language_code=language_code)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        msg = e.response.get("Error", {}).get("Message", "")
        fallback_enabled = os.getenv("TRANSCRIBE_FALLBACK_TO_LOCAL", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        if code == "AccessDeniedException" and fallback_enabled:
            logging.getLogger("transcribe").warning(
                "AWS Transcribe access denied; falling back to local Whisper. "
                "Grant transcribe:StartTranscriptionJob and transcribe:GetTranscriptionJob to disable fallback."
            )
            return _transcribe_local(audio_bytes)

        raise RuntimeError(
            f"AWS transcription failed ({code or 'unknown'}: {msg or 'no details'}). Ensure IAM allows transcribe:StartTranscriptionJob and "
            "transcribe:GetTranscriptionJob, or set TRANSCRIBE_FALLBACK_TO_LOCAL=true."
        ) from e

    t_transcribe = time.time()
    s3_ms = round((t_s3 - t0) * 1000)
    transcribe_ms = round((t_transcribe - t_s3) * 1000)
    total_ms = round((t_transcribe - t0) * 1000)
    logging.getLogger("transcribe").info(
        "LATENCY transcribe_audio total=%dms s3_upload=%dms transcribe_job=%dms",
        total_ms, s3_ms, transcribe_ms,
    )

    return text
