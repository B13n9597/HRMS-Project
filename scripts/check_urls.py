import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'humanresource.settings')
django.setup()
from django.urls import reverse

urls = [
    'supervisor_dashboard', 'supervisor_employees', 'supervisor_leave_approvals',
    'supervisor_attendance', 'supervisor_kpi', 'supervisor_certificates',
    'dashboard_employee', 'dashboard_hr', 'dashboard_dean',
    'attendance_logs', 'live_attendance', 'my_attendance_record',
    'employee_leave_manager', 'hr_leave_manager', 'hr_leave_approvals',
    'staff_directory', 'payroll_center', 'my_salary_slips',
    'performance_kpis', 'candidate_screen', 'global_settings',
    'my_lifecycle', 'tablet_kiosk_attendance',
]
failed = []
for u in urls:
    try:
        reverse(u)
    except Exception as e:
        failed.append(f'{u}: {e}')
if failed:
    print('FAILED:')
    for f in failed:
        print(' ', f)
else:
    print('ALL URLs OK')
