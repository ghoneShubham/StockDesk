"""
Day 14 — nightly pg_dump → S3 (+ optional local copy), prune old backups.
"""

from __future__ import annotations

import gzip
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Run pg_dump, gzip, upload to S3 under backups/, delete older than retention days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--retain-days",
            type=int,
            default=None,
            help="Override BACKUP_RETENTION_DAYS (default from settings).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned actions without dumping or uploading.",
        )

    def handle(self, *args, **options):
        bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "") or ""
        if not bucket:
            raise CommandError(
                "AWS_STORAGE_BUCKET_NAME is empty — set it before running backups."
            )

        retain = options["retain_days"]
        if retain is None:
            retain = int(getattr(settings, "BACKUP_RETENTION_DAYS", 7))
        prefix = getattr(settings, "BACKUP_S3_PREFIX", "backups").strip("/") or "backups"
        dry = options["dry_run"]

        db = settings.DATABASES["default"]
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        key = f"{prefix}/{timezone.localdate().isoformat()}/stockdesk-{stamp}.sql.gz"

        if dry:
            self.stdout.write(f"Would dump DB={db['NAME']} → s3://{bucket}/{key}")
            self.stdout.write(f"Would prune objects under {prefix}/ older than {retain} days")
            return

        env = os.environ.copy()
        if db.get("PASSWORD"):
            env["PGPASSWORD"] = str(db["PASSWORD"])

        dump_cmd = [
            "pg_dump",
            "-h",
            str(db.get("HOST") or "localhost"),
            "-p",
            str(db.get("PORT") or "5432"),
            "-U",
            str(db["USER"]),
            "-d",
            str(db["NAME"]),
            "--no-owner",
            "--no-acl",
            "-F",
            "p",
        ]

        with tempfile.TemporaryDirectory(prefix="stockdesk-backup-") as tmp:
            raw_path = Path(tmp) / "dump.sql"
            gz_path = Path(tmp) / "dump.sql.gz"
            self.stdout.write("Running pg_dump…")
            with raw_path.open("wb") as out:
                proc = subprocess.run(
                    dump_cmd,
                    stdout=out,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=False,
                )
            if proc.returncode != 0:
                err = (proc.stderr or b"").decode("utf-8", errors="replace")
                raise CommandError(f"pg_dump failed ({proc.returncode}): {err}")

            with raw_path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)

            self._upload(bucket, key, gz_path)
            self.stdout.write(self.style.SUCCESS(f"Uploaded s3://{bucket}/{key}"))

        deleted = self._prune(bucket, prefix, retain)
        self.stdout.write(f"Pruned {deleted} old backup object(s) (retain={retain}d).")

    def _upload(self, bucket: str, key: str, path: Path) -> None:
        import boto3

        client = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", None) or "ap-south-1",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
        extra = {"ContentType": "application/gzip"}
        client.upload_file(str(path), bucket, key, ExtraArgs=extra)

    def _prune(self, bucket: str, prefix: str, retain_days: int) -> int:
        import boto3

        client = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", None) or "ap-south-1",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
        cutoff = datetime.now(dt_timezone.utc) - timedelta(days=retain_days)
        deleted = 0
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
            for obj in page.get("Contents") or []:
                last_mod = obj["LastModified"]
                if last_mod.tzinfo is None:
                    last_mod = last_mod.replace(tzinfo=dt_timezone.utc)
                if last_mod < cutoff:
                    client.delete_object(Bucket=bucket, Key=obj["Key"])
                    deleted += 1
        return deleted
