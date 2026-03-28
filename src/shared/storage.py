import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3

log = logging.getLogger(__name__)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PRESIGN_EXPIRY = 604800  # 7 days (S3 max)


class ImageStorage:
    """Upload images to Railway S3-compatible bucket."""

    def __init__(self):
        self._client = None
        self._bucket = None
        self._endpoint = None

    @property
    def ready(self) -> bool:
        return self._client is not None

    def connect(self) -> None:
        endpoint = os.getenv("S3_ENDPOINT_URL", "")
        bucket = os.getenv("S3_BUCKET_NAME", "")
        access_key = os.getenv("S3_ACCESS_KEY_ID", "")
        secret_key = os.getenv("S3_SECRET_ACCESS_KEY", "")

        if not all([endpoint, bucket, access_key, secret_key]):
            log.warning("S3 credentials not set — image uploads disabled")
            return

        self._endpoint = endpoint
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )
        log.info("S3 storage connected (bucket: %s)", bucket)

    async def upload(
        self, file_bytes: bytes, discord_id: int, content_type: str = "image/png"
    ) -> str | None:
        """Upload image bytes. Returns the S3 key (not a URL)."""
        if not self.ready:
            return None

        ext = "png"
        if "jpeg" in content_type or "jpg" in content_type:
            ext = "jpg"
        elif "gif" in content_type:
            ext = "gif"
        elif "webp" in content_type:
            ext = "webp"

        now = datetime.now(VN_TZ)
        key = f"gym-checkins/{discord_id}/{now.strftime('%Y-%m-%d_%H%M%S')}.{ext}"

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )
            log.info("Uploaded image: %s", key)
            return key
        except Exception:
            log.exception("Failed to upload image")
            return None

    def get_url(self, key: str) -> str | None:
        """Generate a presigned URL for an S3 key."""
        if not self.ready or not key:
            return None
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=PRESIGN_EXPIRY,
            )
        except Exception:
            log.exception("Failed to generate presigned URL for %s", key)
            return None
