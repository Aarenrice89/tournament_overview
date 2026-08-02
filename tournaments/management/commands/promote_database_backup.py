from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tournaments.management.database_backups import (
    copy_archive,
    get_backup_settings,
    get_s3_client,
    object_key,
)


class Command(BaseCommand):
    help = "Copy a verified database backup into the known-good S3 retention prefix."

    def add_arguments(self, parser):
        parser.add_argument("s3_key")

    def handle(self, *args, **options):
        source_key = options["s3_key"]
        _, prefix = get_backup_settings()
        if not source_key.startswith(f"{prefix}/"):
            raise CommandError("The selected backup must be in the configured backup prefix.")
        if "/known-good/" in source_key:
            raise CommandError("The selected backup is already marked known-good.")
        destination_key = object_key("known-good", timezone.now())
        copy_archive(get_s3_client(), source_key, destination_key, "known-good")
        self.stdout.write(self.style.SUCCESS(f"Known-good backup created: {destination_key}"))
