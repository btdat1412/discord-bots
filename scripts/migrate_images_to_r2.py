"""Copy gym_checkins images from the old Railway S3 bucket to Cloudflare R2.

Safe by design:
- Reads source object keys from `gym_checkins.image_url` in the DB
- Never deletes from the source bucket (that bucket IS the rollback)
- Idempotent: skips keys already present in destination with matching size
- Verifies destination object size matches source after upload
- Writes a JSON manifest of every action to scripts/migration_manifest_*.json

Required env vars (load from .env or export):
  GYM_RAT_DATABASE_URL          Postgres DSN for the gym_rat DB

  # Source (Railway)
  OLD_S3_ENDPOINT_URL
  OLD_S3_BUCKET_NAME
  OLD_S3_ACCESS_KEY_ID
  OLD_S3_SECRET_ACCESS_KEY

  # Destination (R2)
  S3_ENDPOINT_URL
  S3_BUCKET_NAME
  S3_ACCESS_KEY_ID
  S3_SECRET_ACCESS_KEY

Usage:
  python scripts/migrate_images_to_r2.py             # dry run, lists what would migrate
  python scripts/migrate_images_to_r2.py --apply     # actually copy
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import asyncpg
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("migrate")

PARALLEL_WORKERS = 8


def make_client(prefix: str):
    endpoint = os.getenv(f"{prefix}ENDPOINT_URL", "")
    bucket = os.getenv(f"{prefix}BUCKET_NAME", "")
    access_key = os.getenv(f"{prefix}ACCESS_KEY_ID", "")
    secret_key = os.getenv(f"{prefix}SECRET_ACCESS_KEY", "")
    if not all([endpoint, bucket, access_key, secret_key]):
        raise SystemExit(f"Missing {prefix}* env vars")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )
    return client, bucket


async def fetch_keys(dsn: str) -> list[str]:
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT DISTINCT image_url FROM gym_checkins WHERE image_url IS NOT NULL"
        )
    finally:
        await conn.close()
    return [r["image_url"] for r in rows]


def head_size(client, bucket: str, key: str) -> int | None:
    try:
        resp = client.head_object(Bucket=bucket, Key=key)
        return int(resp["ContentLength"])
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def migrate_one(src_client, src_bucket, dst_client, dst_bucket, key: str) -> dict:
    record = {"key": key, "source_size": None, "dest_size": None, "status": "", "error": None}
    try:
        src_size = head_size(src_client, src_bucket, key)
        if src_size is None:
            record["status"] = "source_missing"
            return record
        record["source_size"] = src_size

        existing_dst = head_size(dst_client, dst_bucket, key)
        if existing_dst == src_size:
            record["dest_size"] = existing_dst
            record["status"] = "skip_already_migrated"
            return record

        obj = src_client.get_object(Bucket=src_bucket, Key=key)
        body = obj["Body"].read()
        content_type = obj.get("ContentType", "application/octet-stream")

        dst_client.put_object(
            Bucket=dst_bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )

        verify_size = head_size(dst_client, dst_bucket, key)
        record["dest_size"] = verify_size
        if verify_size != src_size:
            record["status"] = "size_mismatch"
            record["error"] = f"src={src_size} dst={verify_size}"
        else:
            record["status"] = "copied"
    except Exception as exc:
        record["status"] = "error"
        record["error"] = repr(exc)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually copy (default is dry run)")
    args = parser.parse_args()

    dsn = os.getenv("GYM_RAT_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("Missing GYM_RAT_DATABASE_URL")

    src_client, src_bucket = make_client("OLD_S3_")
    dst_client, dst_bucket = make_client("S3_")
    log.info("Source: %s/%s", src_client.meta.endpoint_url, src_bucket)
    log.info("Destination: %s/%s", dst_client.meta.endpoint_url, dst_bucket)

    keys = asyncio.run(fetch_keys(dsn))
    log.info("Found %d image keys in DB", len(keys))

    if not args.apply:
        log.info("DRY RUN — re-run with --apply to actually copy")
        for key in keys[:20]:
            print(f"  would migrate: {key}")
        if len(keys) > 20:
            print(f"  ... and {len(keys) - 20} more")
        return 0

    manifest: list[dict] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
        futures = {
            pool.submit(migrate_one, src_client, src_bucket, dst_client, dst_bucket, k): k
            for k in keys
        }
        for i, fut in enumerate(as_completed(futures), 1):
            rec = fut.result()
            manifest.append(rec)
            log.info("[%d/%d] %s %s", i, len(keys), rec["status"], rec["key"])

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = Path(__file__).parent / f"migration_manifest_{ts}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    counts: dict[str, int] = {}
    for r in manifest:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    log.info("Summary: %s", counts)
    log.info("Manifest written to %s", manifest_path)
    failed = [r for r in manifest if r["status"] in ("error", "size_mismatch", "source_missing")]
    if failed:
        log.warning("%d items failed — inspect manifest", len(failed))
        return 1
    log.info("All %d items migrated successfully", len(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
