#!/usr/bin/env python3
"""
sift_s3_sync.py — Periodic S3 sync for Protocol SIFT audit logs.

Designed to run from cron. Uploads all .jsonl files from the case logs/
directory to the configured S3 bucket. Files that have not changed since
the last upload are skipped (ETag comparison against S3 object metadata).

Required env vars:
    SIFT_S3_BUCKET — S3 bucket name (required; script exits cleanly if unset)
    SIFT_S3_REGION — AWS region (default: us-west-2)
    SIFT_S3_PREFIX — S3 key prefix (default: sift-logs)

Optional args:
    --logs-dir PATH   Override the logs directory (default: ./logs)
    --dry-run         Print what would be uploaded without uploading

S3 key structure:
    <prefix>/<YYYY-MM-DD>/<session_id>/events.jsonl

Example cron entry (every 15 minutes):
    */15 * * * * SIFT_S3_BUCKET=agent_logs_sift SIFT_S3_REGION=us-west-2 \\
        python3 ~/.claude/analysis-scripts/sift_s3_sync.py \\
        --logs-dir /cases/CLIENT-IR-2025-001/logs >> ~/sift-s3-sync.log 2>&1
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SIFT_S3_BUCKET = os.environ.get("SIFT_S3_BUCKET", "")
SIFT_S3_REGION = os.environ.get("SIFT_S3_REGION", "us-west-2")
SIFT_S3_PREFIX = os.environ.get("SIFT_S3_PREFIX", "sift-logs")
DEFAULT_LOGS_DIR = Path.home() / ".protocol-sift"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s3_key(session_id: str, path: Path = None) -> str:
    # session_id format: SIFT-YYYY-MM-DD-<hex>; fall back to file mtime for other names
    if len(session_id) >= 15 and session_id[4:5] == "-" and session_id[12:13] == "-":
        date_str = session_id[5:15]
    elif path is not None:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        date_str = mtime.strftime("%Y-%m-%d")
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{SIFT_S3_PREFIX}/{date_str}/{session_id}/events.jsonl"


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def sync(logs_dir: Path, dry_run: bool = False) -> int:
    if not SIFT_S3_BUCKET:
        print(f"[sift-s3-sync] {_now()}  SIFT_S3_BUCKET not set — nothing to sync.", file=sys.stderr)
        return 0

    if not logs_dir.is_dir():
        print(f"[sift-s3-sync] {_now()}  Logs directory not found: {logs_dir}", file=sys.stderr)
        return 0

    import boto3
    from botocore.exceptions import ClientError

    s3 = boto3.client("s3", region_name=SIFT_S3_REGION)

    files = sorted(logs_dir.glob("*.jsonl"))
    if not files:
        print(f"[sift-s3-sync] {_now()}  No .jsonl files found in {logs_dir} — nothing to sync.")
        return 0

    uploaded = skipped = errors = 0

    for path in files:
        session_id = path.stem
        key = _s3_key(session_id, path)

        try:
            local_md5 = _md5(path)

            # skip if S3 already has an identical copy (ETag == MD5 for simple PutObject)
            try:
                head = s3.head_object(Bucket=SIFT_S3_BUCKET, Key=key)
                remote_etag = head.get("ETag", "").strip('"')
                if remote_etag == local_md5:
                    skipped += 1
                    continue
            except ClientError as e:
                if e.response["Error"]["Code"] not in ("404", "NoSuchKey"):
                    raise
                # object does not exist yet — fall through to upload

            if dry_run:
                print(f"[dry-run]       {_now()}  would upload {path.name} → s3://{SIFT_S3_BUCKET}/{key}")
                uploaded += 1
                continue

            s3.put_object(
                Bucket=SIFT_S3_BUCKET,
                Key=key,
                Body=path.read_bytes(),
                ContentType="application/x-ndjson",
            )
            print(f"[sift-s3-sync] {_now()}  uploaded {path.name} → s3://{SIFT_S3_BUCKET}/{key}")
            uploaded += 1

        except Exception as exc:
            print(f"[sift-s3-sync] {_now()}  ERROR uploading {path.name}: {exc}", file=sys.stderr)
            errors += 1

    print(
        f"[sift-s3-sync] {_now()}  "
        f"done — uploaded: {uploaded}, skipped (unchanged): {skipped}, errors: {errors}"
    )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Protocol SIFT audit logs (.jsonl) to S3.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--logs-dir",
        default=str(DEFAULT_LOGS_DIR),
        help=f"Path to the logs directory (default: {DEFAULT_LOGS_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be uploaded without uploading anything.",
    )
    args = parser.parse_args()

    sys.exit(sync(Path(args.logs_dir), dry_run=args.dry_run))


if __name__ == "__main__":
    main()
