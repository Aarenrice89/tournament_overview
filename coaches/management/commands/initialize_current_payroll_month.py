from django.core.management.base import BaseCommand

from coaches.services import central_today, initialize_payroll_month, payroll_month_for


class Command(BaseCommand):
    help = "Initializes payroll records for the current Central Time month."

    def handle(self, *args, **options):
        month = payroll_month_for(central_today())
        payrolls = initialize_payroll_month(month)
        self.stdout.write(self.style.SUCCESS(f"Ensured {len(payrolls)} coach payroll records for {month:%B %Y}."))
