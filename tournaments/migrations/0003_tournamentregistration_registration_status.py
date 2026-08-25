from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0002_make_tournament_dates_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournamentregistration",
            name="registration_status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("accepted", "Accepted")],
                default="pending",
                max_length=8,
            ),
        ),
    ]
