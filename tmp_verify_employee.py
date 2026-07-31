import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'humanresource.settings')
import django
django.setup()
from unittest.mock import patch
import ssl
from hr.services import employee_service
from hr.models import Department, Role

User = __import__('django.contrib.auth.models', fromlist=['User']).User
User.objects.filter(username='verifyuser').delete()
User.objects.filter(email='verify@example.com').delete()
dept, _ = Department.objects.get_or_create(name='Verification Dept')
role, _ = Role.objects.get_or_create(name='HR Manager')
with patch('hr.services.employee_service.send_mail', side_effect=ssl.SSLError('certificate verify failed')):
    emp = employee_service.create_employee({
        'first_name': 'Verify',
        'last_name': 'User',
        'email': 'verify@example.com',
        'username': 'verifyuser',
        'department_id': dept.id,
        'role_id': role.id,
        'send_email': True,
    })
    print(emp.user.username, emp.user.email, emp.id)
