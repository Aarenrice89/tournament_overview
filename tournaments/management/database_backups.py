import hashlib
import os
import subprocess
from datetime import UTC
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import boto3
from django.conf import settings
from django.core.management.base import CommandError
from django.utils import timezone

CENTRAL_TIME = ZoneInfo("America/Chicago")


def get_s3_client():
    return boto3.client("s3", region_name=settings.AWS_REGION or None)


def get_backup_settings():
    if not settings.DATABASE_BACKUP_S3_BUCKET:
        raise CommandError("DATABASE_BACKUP_S3_BUCKET must be configured.")
    return settings.DATABASE_BACKUP_S3_BUCKET, settings.DATABASE_BACKUP_S3_PREFIX.strip("/")


def database_command(command, archive_path):
    database = settings.DATABASES["default"]
    environment = os.environ.copy()
    environment["PGPASSWORD"] = str(database["PASSWORD"])
    arguments = [
        command,
        f"--host={database['HOST']}",
        f"--port={database['PORT']}",
        f"--username={database['USER']}",
        "--no-owner",
        "--no-acl",
    ]
    if command == "pg_dump":
        arguments.extend([f"--file={archive_path}", database["NAME"]])
    else:
        arguments.extend([f"--dbname={database['NAME']}", str(archive_path)])
    return arguments, environment


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as archive:
        for chunk in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_key(retention, now):
    timestamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    local_time = now.astimezone(CENTRAL_TIME)
    return (
        f"{retention}/{local_time.year:04d}/{local_time.month:02d}/{local_time.day:02d}/"
        f"{settings.DATABASES['default']['NAME']}-{timestamp}.dump"
    )


def object_key(retention, now):
    _, prefix = get_backup_settings()
    return f"{prefix}/{archive_key(retention, now)}"


def upload_archive(client, archive_path, key, retention):
    bucket, _ = get_backup_settings()
    checksum = sha256(archive_path)
    extra_args = {
        "Metadata": {
            "sha256": checksum,
            "database": settings.DATABASES["default"]["NAME"],
            "created-at": timezone.now().isoformat(),
        },
        "Tagging": urlencode({"retention": retention}),
    }
    if settings.DATABASE_BACKUP_S3_KMS_KEY_ID:
        extra_args.update(
            {
                "ServerSideEncryption": "aws:kms",
                "SSEKMSKeyId": settings.DATABASE_BACKUP_S3_KMS_KEY_ID,
            }
        )
    client.upload_file(str(archive_path), bucket, key, ExtraArgs=extra_args)
    uploaded = client.head_object(Bucket=bucket, Key=key)
    if uploaded["ContentLength"] != Path(archive_path).stat().st_size:
        raise CommandError(f"Uploaded archive size does not match local archive: {key}")
    if uploaded.get("Metadata", {}).get("sha256") != checksum:
        raise CommandError(f"Uploaded archive checksum metadata does not match: {key}")


def prefix_has_backup(client, retention, now):
    bucket, prefix = get_backup_settings()
    local_time = now.astimezone(CENTRAL_TIME)
    period_prefix = f"{prefix}/{retention}/{local_time.year:04d}/"
    if retention == "monthly":
        period_prefix += f"{local_time.month:02d}/"
    response = client.list_objects_v2(Bucket=bucket, Prefix=period_prefix, MaxKeys=1)
    return bool(response.get("Contents"))


def retention_targets(client, now):
    targets = ["daily"]
    local_time = now.astimezone(CENTRAL_TIME)
    if local_time.weekday() == 6:
        targets.append("weekly")
    if not prefix_has_backup(client, "monthly", now):
        targets.append("monthly")
    if not prefix_has_backup(client, "yearly", now):
        targets.append("yearly")
    return targets


def copy_archive(client, source_key, destination_key, retention):
    bucket, _ = get_backup_settings()
    client.copy_object(
        Bucket=bucket,
        Key=destination_key,
        CopySource={"Bucket": bucket, "Key": source_key},
        MetadataDirective="COPY",
        TaggingDirective="REPLACE",
        Tagging=urlencode({"retention": retention}),
    )


def create_backup(client=None, now=None, retention="daily", classify=True):
    client = client or get_s3_client()
    now = now or timezone.now()
    with NamedTemporaryFile(suffix=".dump", delete=False) as temporary_archive:
        archive_path = Path(temporary_archive.name)
    try:
        command, environment = database_command("pg_dump", archive_path)
        command.insert(1, "--format=custom")
        subprocess.run(command, check=True, env=environment, capture_output=True, text=True)
        key = object_key(retention, now)
        upload_archive(client, archive_path, key, retention)
        if classify:
            for target in retention_targets(client, now):
                if target != retention:
                    copy_archive(client, key, object_key(target, now), target)
        return key
    except subprocess.CalledProcessError as error:
        raise CommandError(error.stderr or "pg_dump failed.") from error
    finally:
        archive_path.unlink(missing_ok=True)


def download_archive(client, key):
    bucket, _ = get_backup_settings()
    metadata = client.head_object(Bucket=bucket, Key=key).get("Metadata", {})
    expected_checksum = metadata.get("sha256")
    if not expected_checksum:
        raise CommandError(f"Backup is missing checksum metadata: {key}")
    with NamedTemporaryFile(suffix=".dump", delete=False) as temporary_archive:
        archive_path = Path(temporary_archive.name)
    client.download_file(bucket, key, str(archive_path))
    if sha256(archive_path) != expected_checksum:
        archive_path.unlink(missing_ok=True)
        raise CommandError(f"Backup checksum does not match: {key}")
    return archive_path
