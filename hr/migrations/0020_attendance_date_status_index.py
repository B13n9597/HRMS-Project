from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('hr', '0019_merge_20260730_1258')]

    operations = [
        migrations.AddIndex(
            model_name='attendance',
            index=models.Index(fields=['date', 'status'], name='attendance_date_status_idx'),
        ),
    ]
