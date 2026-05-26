import os
import time
import logging
from typing import Optional
from botocore.config import Config
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
        self.client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": s3_uri},
            MediaFormat="wav",
            LanguageCode="en-US",
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
    text = service.transcribe_file(s3_uri)

    return text
