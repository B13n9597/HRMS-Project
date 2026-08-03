from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('hr', '0021_recruitment_onboarding_and_leave_policy')]

    operations = [
        migrations.AddField(
            model_name='employee', name='employment_phase',
            field=models.CharField(
                choices=[('Probation', 'Probation'), ('Permanent', 'Permanent')],
                default='Probation', max_length=12,
            ),
        ),
    ]
