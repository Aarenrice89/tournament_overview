from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tournament",
            name="end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="tournament",
            name="registration_closes_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="tournament",
            name="registration_opens_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
