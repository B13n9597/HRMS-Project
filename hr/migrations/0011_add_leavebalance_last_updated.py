from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0010_attendance_signature_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='leavebalance',
            name='last_updated',
            field=models.DateField(null=True, blank=True),
        ),
    ]
