"""
Migration: Add `session` field to OPDDay.

OPDDay was unique on (doctor, date).
Now unique on (doctor, date, session) — morning and evening are separate rows.

Existing rows are assigned session="morning" (safe default).

Instructions:
  1. Check your last migration filename in bookings/migrations/
  2. Update the dependencies line below to match it
  3. Run: python manage.py migrate
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # ── CHANGE THIS to your actual last migration filename ──────────────
        # Look inside bookings/migrations/ and use the highest-numbered file.
        # Examples:
        #   ("bookings", "0001_initial"),
        #   ("bookings", "0003_booking_add_walkin_name"),
        ("booking", "0001_initial"),
    ]

    operations = [

        # Step 1: Add session column with default="morning" for existing rows
        migrations.AddField(
            model_name="opdday",
            name="session",
            field=models.CharField(
                max_length=10,
                choices=[("morning", "Morning (10AM – 12PM)"), ("evening", "Evening (3PM – 5PM)")],
                default="morning",
            ),
            preserve_default=False,
        ),

        # Step 2: Drop old unique_together (doctor, date)
        migrations.AlterUniqueTogether(
            name="opdday",
            unique_together=set(),
        ),

        # Step 3: Add new unique_together (doctor, date, session)
        migrations.AlterUniqueTogether(
            name="opdday",
            unique_together={("doctor", "date", "session")},
        ),

        # Step 4: Update ordering to include session
        migrations.AlterModelOptions(
            name="opdday",
            options={"ordering": ["-date", "session"]},
        ),
    ]
