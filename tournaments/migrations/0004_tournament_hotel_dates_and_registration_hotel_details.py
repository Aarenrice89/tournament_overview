from django.db import migrations, models
from django.db.models import Q


def set_unregistered_statuses_to_not_applicable(apps, schema_editor):
    TournamentRegistration = apps.get_model("tournaments", "TournamentRegistration")
    TournamentRegistration.objects.filter(is_registered=False).update(registration_status="na")


def set_not_applicable_statuses_to_pending(apps, schema_editor):
    TournamentRegistration = apps.get_model("tournaments", "TournamentRegistration")
    TournamentRegistration.objects.filter(registration_status="na").update(registration_status="pending")


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0003_tournamentregistration_registration_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="hotel_open_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tournament",
            name="hotel_close_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tournamentregistration",
            name="hotel_compliant",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tournamentregistration",
            name="number_of_rooms_required",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="tournamentregistration",
            name="registration_status",
            field=models.CharField(
                choices=[("na", "N/A"), ("pending", "Pending"), ("accepted", "Accepted")],
                default="na",
                max_length=8,
            ),
        ),
        migrations.RunPython(set_unregistered_statuses_to_not_applicable, set_not_applicable_statuses_to_pending),
        migrations.AddConstraint(
            model_name="tournamentregistration",
            constraint=models.CheckConstraint(
                condition=(Q(is_registered=False, registration_status="na") | (Q(is_registered=True) & ~Q(registration_status="na"))),
                name="registration_status_matches_registered",
            ),
        ),
    ]
