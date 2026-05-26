import os
import boto3
import logging
from botocore.config import Config


def upload_file_to_s3(local_path: str, bucket: str, key: str) -> str:
    log = logging.getLogger("s3_upload")
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        config=Config(retries={"max_attempts": 5, "mode": "standard"}),
    )
    log.info(f"Uploading {local_path} to s3://{bucket}/{key}")
    s3.upload_file(local_path, bucket, key)
    log.info("Upload complete")
    return f"s3://{bucket}/{key}"
