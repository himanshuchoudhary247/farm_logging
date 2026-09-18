import os
import sys


REQUIRED_ENV = [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "VOICE_BUCKET",
]


def validate_env() -> None:
    # Dev-proxy mode: this machine calls our own /proxy/bedrock+transcribe+tts
    # endpoints over HTTP instead of AWS directly, so it needs none of its
    # own AWS credentials -- the proxy server holds those. Only
    # DEV_PROXY_API_KEY is required in that mode.
    if os.getenv("LLM_PROXY_BASE_URL"):
        if not os.getenv("DEV_PROXY_API_KEY"):
            print("\n[ENV ERROR] LLM_PROXY_BASE_URL is set but DEV_PROXY_API_KEY is missing.\n")
            sys.exit(1)
        return

    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        print("\n[ENV ERROR] Missing required environment variables:\n")
        for m in missing:
            print(f"  - {m}")
        print("\nSet them in your .env file or export them before running.\n")
        sys.exit(1)
