import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3

log = logging.getLogger(__name__)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PRESIGN_EXPIRY = 604800  # 7 days (S3 max)


class ImageStorage:
    """Upload images to an S3-compatible bucket (Cloudflare R2, AWS S3, etc.)."""

    def __init__(self):
        self._client = None
        self._bucket = None
        self._endpoint = None
        self._public_base_url = None

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
        # Public base URL (e.g. https://pub-xxx.r2.dev or https://img.domain).
        # When set, get_url() returns "{base}/{key}" so Discord/CDN can cache.
        # When unset, falls back to presigned URLs.
        public_base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
        self._public_base_url = public_base or None

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )
        mode = "public-url" if self._public_base_url else "presigned"
        log.info("S3 storage connected (bucket: %s, mode: %s)", bucket, mode)

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
        """Return a URL for an S3 key.

        Uses PUBLIC_BASE_URL when set (cacheable at CDN edge), otherwise
        falls back to a 7-day presigned URL.
        """
        if not self.ready or not key:
            return None
        if self._public_base_url:
            return f"{self._public_base_url}/{key}"
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=PRESIGN_EXPIRY,
            )
        except Exception:
            log.exception("Failed to generate presigned URL for %s", key)
            return None
