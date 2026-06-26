import os
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

    def transcribe_file(self, s3_uri: str, job_name: Optional[str] = None) -> str:
        job_name = job_name or f"farmer-chat-{int(time.time())}"

        self.log.info(f"Starting transcription job {job_name} for {s3_uri}")
        language_code = os.getenv("AWS_TRANSCRIBE_LANGUAGE_CODE", "en-IN")
        enable_multilingual = os.getenv("AWS_TRANSCRIBE_MULTILINGUAL", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        req = {
            "TranscriptionJobName": job_name,
            "Media": {"MediaFileUri": s3_uri},
            "MediaFormat": "wav",
        }

        if enable_multilingual:
            language_opts_raw = os.getenv("AWS_TRANSCRIBE_LANGUAGE_OPTIONS", "en-IN,hi-IN,kn-IN,te-IN")
            language_options = [x.strip() for x in language_opts_raw.split(",") if x.strip()]
            if language_options:
                req["IdentifyLanguage"] = True
                req["LanguageOptions"] = language_options
        else:
            req["LanguageCode"] = language_code

        self.client.start_transcription_job(
            **req,
        )

        start = time.time()
        while True:
            status = self.client.get_transcription_job(TranscriptionJobName=job_name)
            state = status["TranscriptionJob"]["TranscriptionJobStatus"]
            if state in ("COMPLETED", "FAILED"):
                break
            if time.time() - start > 300:
                raise TimeoutError("Transcription timed out")
            time.sleep(2)

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
def transcribe_audio(audio_bytes: bytes) -> str:
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

    # -------- AWS (prod) mode --------
    import tempfile
    import uuid
    from services.voice_agent.s3_upload import upload_file_to_s3

    bucket = os.getenv("VOICE_S3_BUCKET")
    if not bucket:
        raise ValueError("VOICE_S3_BUCKET not set for AWS mode")

    # Step 1: save temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(audio_bytes)
        local_path = f.name

    # Step 2: upload to S3
    key = f"voice-input/{uuid.uuid4()}.wav"
    s3_uri = upload_file_to_s3(local_path, bucket, key)

    # Step 3: transcribe
    service = TranscribeService()
    try:
        text = service.transcribe_file(s3_uri)
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

    return text
