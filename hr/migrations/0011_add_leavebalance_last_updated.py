from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Safely add last_updated to hr_leavebalance using IF NOT EXISTS
    to handle cases where the column was added manually or via another migration path.
    """

    dependencies = [
        ('hr', '0010_attendance_signature_text'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='hr_leavebalance' AND column_name='last_updated'
                    ) THEN
                        ALTER TABLE hr_leavebalance ADD COLUMN last_updated DATE NULL;
                    END IF;
                END
                $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
            state_operations=[
                migrations.AddField(
                    model_name='leavebalance',
                    name='last_updated',
                    field=models.DateField(null=True, blank=True),
                ),
            ],
        ),
    ]
