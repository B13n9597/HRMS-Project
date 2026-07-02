from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0011_add_leavebalance_last_updated'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leavebalance',
            name='last_updated',
            field=models.DateField(),
        ),
    ]
