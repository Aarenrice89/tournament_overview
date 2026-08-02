from django.core.management.base import BaseCommand

from tournaments.management.database_backups import create_backup


class Command(BaseCommand):
    help = "Create a PostgreSQL backup and upload it to S3."

    def handle(self, *args, **options):
        key = create_backup()
        self.stdout.write(self.style.SUCCESS(f"Database backup uploaded: {key}"))
