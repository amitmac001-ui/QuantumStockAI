from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0004_mark_verified_suspended_instruments"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="three_year_high",
            field=models.DecimalField(
                blank=True, decimal_places=4, max_digits=20, null=True
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="three_year_high_session",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="three_year_observations",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="company",
            name="three_year_window_start",
            field=models.DateField(blank=True, null=True),
        ),
    ]
