import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'humanresource.settings')
django.setup()

from hr.models import Employee
from hr.services.attendance_service import get_employee_qr_token, process_qr_scan
from hr.utils import verify_daily_token

emp = Employee.objects.filter(first_name__iexact='kalkidan').first()
print('Employee:', emp, emp.department.name if emp and emp.department else None)
if not emp:
    emp = Employee.objects.filter(department__name='Computer Science').exclude(user=None).first()
    print('Fallback emp:', emp)

if emp:
    token_data = get_employee_qr_token(emp.user)
    print('Token length', len(token_data['token']))
    print('Batch verify', verify_daily_token(token_data['token']))
    class R:
        pass
    r = R()
    r.META = {}
    r.data = {'token': token_data['token']}
    print('Scan result', process_qr_scan(r))
else:
    print('No employee')
