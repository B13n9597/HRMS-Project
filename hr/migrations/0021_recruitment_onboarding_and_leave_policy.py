from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('hr', '0020_attendance_date_status_index')]

    operations = [
        migrations.AddField(model_name='employee', name='middle_name', field=models.CharField(blank=True, default='', max_length=50)),
        migrations.AddField(model_name='employee', name='gender', field=models.CharField(blank=True, choices=[('Male', 'Male'), ('Female', 'Female')], default='', max_length=10)),
        migrations.AddField(model_name='employee', name='marital_status', field=models.CharField(blank=True, choices=[('Single', 'Single'), ('Married', 'Married')], default='', max_length=10)),
        migrations.AddField(model_name='employee', name='emergency_contact', field=models.CharField(blank=True, default='', max_length=20)),
        migrations.AddField(model_name='employee', name='fayda_id', field=models.FileField(blank=True, null=True, upload_to='ids/')),
        migrations.AddField(model_name='employee', name='qualification', field=models.CharField(blank=True, default='', max_length=100)),
        migrations.AddField(model_name='employee', name='field_of_study', field=models.CharField(blank=True, default='', max_length=100)),
        migrations.AddField(model_name='employee', name='institution', field=models.CharField(blank=True, default='', max_length=150)),
        migrations.AddField(model_name='applicant', name='middle_name', field=models.CharField(blank=True, default='', max_length=50)),
        migrations.AddField(model_name='applicant', name='gender', field=models.CharField(choices=[('Male', 'Male'), ('Female', 'Female')], default='Male', max_length=10), preserve_default=False),
        migrations.AddField(model_name='applicant', name='marital_status', field=models.CharField(choices=[('Single', 'Single'), ('Married', 'Married')], default='Single', max_length=10), preserve_default=False),
        migrations.AddField(model_name='applicant', name='emergency_contact', field=models.CharField(default='', max_length=20), preserve_default=False),
        migrations.AddField(model_name='applicant', name='fayda_id', field=models.FileField(default='', upload_to='ids/'), preserve_default=False),
        migrations.AddField(model_name='applicant', name='cv', field=models.FileField(default='', upload_to='cvs/'), preserve_default=False),
        migrations.AddField(model_name='applicant', name='qualification', field=models.CharField(default='', max_length=100), preserve_default=False),
        migrations.AddField(model_name='applicant', name='field_of_study', field=models.CharField(default='', max_length=100), preserve_default=False),
        migrations.AddField(model_name='applicant', name='institution', field=models.CharField(default='', max_length=150), preserve_default=False),
        migrations.AddField(model_name='applicant', name='work_experience', field=models.TextField(blank=True, default='')),
        migrations.AlterField(model_name='applicant', name='email', field=models.EmailField(max_length=254, unique=True)),
        migrations.AddField(model_name='application', name='hr_notes', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='application', name='converted_employee', field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='source_application', to='hr.employee')),
        migrations.CreateModel(
            name='LeavePolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('allowed_gender', models.CharField(blank=True, choices=[('', 'All employees'), ('Male', 'Male'), ('Female', 'Female')], default='', max_length=10)),
                ('leave_type', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='policy', to='hr.leavetype')),
            ],
        ),
    ]
