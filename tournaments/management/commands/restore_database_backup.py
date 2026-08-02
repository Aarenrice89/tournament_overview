import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tournaments.management.database_backups import (
    create_backup,
    database_command,
    download_archive,
    get_s3_client,
)


class Command(BaseCommand):
    help = "Restore a checksum-verified PostgreSQL backup from S3."

    def add_arguments(self, parser):
        parser.add_argument("s3_key")
        parser.add_argument("--confirm-replace-database", action="store_true")
        parser.add_argument("--allow-production-restore", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_replace_database"]:
            raise CommandError("Pass --confirm-replace-database to replace the current database.")
        if not settings.DEBUG and not options["allow_production_restore"]:
            raise CommandError("Pass --allow-production-restore when DEBUG is false.")

        client = get_s3_client()
        emergency_key = create_backup(client=client, retention="pre-restore", classify=False)
        self.stdout.write(f"Current database backed up before restore: {emergency_key}")
        archive_path = download_archive(client, options["s3_key"])
        try:
            command, environment = database_command("pg_restore", archive_path)
            command[1:1] = ["--clean", "--if-exists", "--single-transaction", "--exit-on-error"]
            subprocess.run(command, check=True, env=environment, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            raise CommandError(error.stderr or "pg_restore failed.") from error
        finally:
            archive_path.unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Database restored from: {options['s3_key']}"))
