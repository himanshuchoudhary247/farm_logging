import os
import sys


REQUIRED_ENV = [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "VOICE_BUCKET",
]


def validate_env() -> None:
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        print("\n[ENV ERROR] Missing required environment variables:\n")
        for m in missing:
            print(f"  - {m}")
        print("\nSet them in your .env file or export them before running.\n")
        sys.exit(1)
