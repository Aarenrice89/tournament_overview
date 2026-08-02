import hashlib
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from tournaments.management import database_backups


@override_settings(
    AWS_REGION="us-east-1",
    DATABASE_BACKUP_S3_BUCKET="backup-bucket",
    DATABASE_BACKUP_S3_PREFIX="postgres",
    DATABASE_BACKUP_S3_KMS_KEY_ID="",
    DATABASES={
        "default": {
            "NAME": "tournament_overview",
            "USER": "database-user",
            "PASSWORD": "database-password",
            "HOST": "db",
            "PORT": 5432,
        }
    },
)
class DatabaseBackupTests(SimpleTestCase):
    def test_pg_dump_command_uses_custom_archive_file(self):
        command, environment = database_backups.database_command("pg_dump", "/tmp/database.dump")

        self.assertEqual(
            command,
            [
                "pg_dump",
                "--host=db",
                "--port=5432",
                "--username=database-user",
                "--no-owner",
                "--no-acl",
                "--file=/tmp/database.dump",
                "tournament_overview",
            ],
        )
        self.assertEqual(environment["PGPASSWORD"], "database-password")

    def test_pg_restore_command_targets_configured_database(self):
        command, _ = database_backups.database_command("pg_restore", "/tmp/database.dump")

        self.assertIn("--dbname=tournament_overview", command)
        self.assertEqual(command[-1], "/tmp/database.dump")

    @patch("tournaments.management.database_backups.subprocess.run")
    def test_create_backup_uploads_and_verifies_archive(self, run):
        client = Mock()
        client.head_object.return_value = {
            "ContentLength": 0,
            "Metadata": {"sha256": hashlib.sha256(b"").hexdigest()},
        }
        client.list_objects_v2.return_value = {"Contents": [{"Key": "existing"}]}
        now = datetime(2026, 8, 5, 5, tzinfo=ZoneInfo("UTC"))

        key = database_backups.create_backup(client=client, now=now)

        self.assertEqual(key, "postgres/daily/2026/08/05/tournament_overview-20260805T050000Z.dump")
        self.assertIn("--format=custom", run.call_args.args[0])
        client.upload_file.assert_called_once()
        self.assertEqual(client.copy_object.call_count, 0)

    def test_retention_targets_adds_first_monthly_and_yearly_backup(self):
        client = Mock()
        client.list_objects_v2.return_value = {}
        now = datetime(2026, 1, 4, 6, tzinfo=ZoneInfo("UTC"))

        targets = database_backups.retention_targets(client, now)

        self.assertEqual(targets, ["daily", "weekly", "monthly", "yearly"])

    def test_download_archive_rejects_checksum_mismatch(self):
        client = Mock()
        client.head_object.return_value = {"Metadata": {"sha256": "not-the-file-checksum"}}

        def write_archive(bucket, key, filename):
            Path(filename).write_bytes(b"database archive")

        client.download_file.side_effect = write_archive

        with self.assertRaisesMessage(CommandError, "Backup checksum does not match"):
            database_backups.download_archive(client, "postgres/daily/example.dump")

    @patch("tournaments.management.commands.backup_database.create_backup")
    def test_backup_command_reports_uploaded_key(self, create_backup):
        create_backup.return_value = "postgres/daily/example.dump"

        call_command("backup_database")

        create_backup.assert_called_once_with()

    def test_restore_command_requires_confirmation(self):
        with self.assertRaisesMessage(CommandError, "--confirm-replace-database"):
            call_command("restore_database_backup", "postgres/daily/example.dump")
