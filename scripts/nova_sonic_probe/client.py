"""Reusable Nova Sonic turn-runner: synthesize an utterance with gTTS,
send it as real audio input over InvokeModelWithBidirectionalStream, and
collect the model's text transcript + speech-token usage + latency.

Run from the main app venv (Python 3.13, aws_sdk_bedrock_runtime + awscrt
in requirements.txt).
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import subprocess
import tempfile
import time
import uuid
import wave
from pathlib import Path

from gtts import gTTS

from aws_sdk_bedrock_runtime.client import AsyncBedrockRuntimeClient
from aws_sdk_bedrock_runtime.config import AsyncBedrockRuntimeConfig
from aws_sdk_bedrock_runtime.models import (
    BidirectionalInputPayloadPart,
    InvokeModelWithBidirectionalStreamInputChunk,
    InvokeModelWithBidirectionalStreamOperationInput,
)
from smithy_http.aio.crt import AWSCRTHTTPClient

MODEL_ID = "amazon.nova-sonic-v1:0"
SAMPLE_RATE = 16000
CHUNK_MS = 200
CHUNK_BYTES = int(SAMPLE_RATE * 2 * CHUNK_MS / 1000)
OUTPUT_SAMPLE_RATE = 24000  # matches audioOutputConfiguration below


def write_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def synthesize_pcm16k(text: str, gtts_lang: str) -> bytes:
    buf = io.BytesIO()
    gTTS(text=text, lang=gtts_lang).write_to_fp(buf)
    mp3_path = Path(tempfile.mkstemp(suffix=".mp3")[1])
    mp3_path.write_bytes(buf.getvalue())
    pcm_path = Path(tempfile.mkstemp(suffix=".pcm")[1])
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3_path), "-f", "s16le", "-ar", str(SAMPLE_RATE),
         "-ac", "1", str(pcm_path)],
        check=True, capture_output=True,
    )
    data = pcm_path.read_bytes()
    mp3_path.unlink(missing_ok=True)
    pcm_path.unlink(missing_ok=True)
    return data


def _event(payload: dict) -> InvokeModelWithBidirectionalStreamInputChunk:
    return InvokeModelWithBidirectionalStreamInputChunk(
        value=BidirectionalInputPayloadPart(bytes_=json.dumps(payload).encode("utf-8"))
    )


async def run_turn(
    utterance: str,
    gtts_lang: str,
    region: str = "us-east-1",
    system_prompt: str = "You are a friendly veterinary assistant for Indian farmers. Keep replies short.",
    voice_id: str = "matthew",
    timeout_s: float = 35.0,
    trailing_silence_ms: int = 2000,
) -> dict:
    pcm = synthesize_pcm16k(utterance, gtts_lang)
    if trailing_silence_ms:
        pcm += b"\x00" * int(SAMPLE_RATE * 2 * trailing_silence_ms / 1000)

    config = await AsyncBedrockRuntimeConfig.resolve(region=region, transport=AWSCRTHTTPClient())
    client = AsyncBedrockRuntimeClient(config=config)

    prompt_id = str(uuid.uuid4())
    sys_content_id = "sys-1"
    audio_content_id = "user-audio-1"

    result = {
        "utterance": utterance,
        "text_output": [],
        "audio_output_b64_chunks": [],
        "input_speech_tokens": 0,
        "output_speech_tokens": 0,
        "output_text_tokens": 0,
        "error": None,
        "latency_s": None,
        "raw_events": [],
        "_last_event_at": 0.0,
    }

    t0 = time.monotonic()
    try:
        stream = await client.invoke_model_with_bidirectional_stream(
            input=InvokeModelWithBidirectionalStreamOperationInput(model_id=MODEL_ID)
        )
    except Exception as exc:
        result["error"] = f"OPEN_FAILED: {type(exc).__name__}: {exc}"
        return result

    async def send_all():
        await stream.input_stream.send(_event({"event": {"sessionStart": {
            "inferenceConfiguration": {"maxTokens": 300, "topP": 0.9, "temperature": 0.6}
        }}}))
        await stream.input_stream.send(_event({"event": {"promptStart": {
            "promptName": prompt_id,
            "textOutputConfiguration": {"mediaType": "text/plain"},
            "audioOutputConfiguration": {
                "mediaType": "audio/lpcm", "sampleRateHertz": 24000,
                "sampleSizeBits": 16, "channelCount": 1,
                "voiceId": voice_id, "encoding": "base64", "audioType": "SPEECH",
            },
        }}}))
        await stream.input_stream.send(_event({"event": {"contentStart": {
            "promptName": prompt_id, "contentName": sys_content_id, "type": "TEXT",
            "interactive": True, "role": "SYSTEM",
            "textInputConfiguration": {"mediaType": "text/plain"},
        }}}))
        await stream.input_stream.send(_event({"event": {"textInput": {
            "promptName": prompt_id, "contentName": sys_content_id, "content": system_prompt,
        }}}))
        await stream.input_stream.send(_event({"event": {"contentEnd": {
            "promptName": prompt_id, "contentName": sys_content_id,
        }}}))

        await stream.input_stream.send(_event({"event": {"contentStart": {
            "promptName": prompt_id, "contentName": audio_content_id, "type": "AUDIO",
            "interactive": True, "role": "USER",
            "audioInputConfiguration": {
                "mediaType": "audio/lpcm", "sampleRateHertz": SAMPLE_RATE,
                "sampleSizeBits": 16, "channelCount": 1,
                "audioType": "SPEECH", "encoding": "base64",
            },
        }}}))
        for i in range(0, len(pcm), CHUNK_BYTES):
            chunk = pcm[i:i + CHUNK_BYTES]
            b64 = base64.b64encode(chunk).decode("ascii")
            await stream.input_stream.send(_event({"event": {"audioInput": {
                "promptName": prompt_id, "contentName": audio_content_id, "content": b64,
            }}}))
            await asyncio.sleep(CHUNK_MS / 1000 * 0.5)
        await stream.input_stream.send(_event({"event": {"contentEnd": {
            "promptName": prompt_id, "contentName": audio_content_id,
        }}}))
        # Wait for the assistant to finish speaking (no new events for a
        # quiet window) before tearing the session down, or give up after
        # a hard cap either way.
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.3)
            if time.monotonic() - result["_last_event_at"] > 1.5 and result["_last_event_at"] > 0:
                break
        await stream.input_stream.send(_event({"event": {"promptEnd": {"promptName": prompt_id}}}))
        await stream.input_stream.send(_event({"event": {"sessionEnd": {}}}))
        await stream.input_stream.close()

    async def recv_all():
        try:
            _, output_stream = await stream.await_output()
            async for output in output_stream:
                raw = getattr(getattr(output, "value", None), "bytes_", None)
                if not raw:
                    continue
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except Exception:
                    continue
                result["raw_events"].append(payload)
                result["_last_event_at"] = time.monotonic()
                ev = payload.get("event", {})
                if "textOutput" in ev:
                    result["text_output"].append(ev["textOutput"].get("content", ""))
                if "audioOutput" in ev:
                    result["audio_output_b64_chunks"].append(ev["audioOutput"].get("content", ""))
                if "usageEvent" in ev:
                    tot = ev["usageEvent"].get("total", {})
                    result["input_speech_tokens"] = tot.get("input", {}).get("speechTokens", 0)
                    result["output_speech_tokens"] = tot.get("output", {}).get("speechTokens", 0)
                    result["output_text_tokens"] = tot.get("output", {}).get("textTokens", 0)
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"

    try:
        await asyncio.wait_for(
            asyncio.gather(send_all(), recv_all(), return_exceptions=True),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        result["error"] = (result["error"] or "") + " TIMEOUT"

    result["latency_s"] = round(time.monotonic() - t0, 2)
    await client.close()
    return result


if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "My cow has a fever, what should I do?"
    lang = sys.argv[2] if len(sys.argv) > 2 else "en"
    out = asyncio.run(run_turn(text, lang))

    if out["audio_output_b64_chunks"]:
        pcm = b"".join(base64.b64decode(c) for c in out["audio_output_b64_chunks"])
        wav_idx = sys.argv.index("--wav") if "--wav" in sys.argv else None
        wav_path = Path(sys.argv[wav_idx + 1]) if wav_idx else Path("nova_sonic_reply.wav")
        write_wav(wav_path, pcm, OUTPUT_SAMPLE_RATE)
        out["reply_wav_path"] = str(wav_path)
        out["reply_audio_seconds"] = round(len(pcm) / 2 / OUTPUT_SAMPLE_RATE, 2)

    show_raw = "--raw" in sys.argv
    hidden = {"_last_event_at", "audio_output_b64_chunks"} | (set() if show_raw else {"raw_events"})
    keys = [k for k in out if k not in hidden]
    print(json.dumps({k: out[k] for k in keys}, indent=2, ensure_ascii=False))
