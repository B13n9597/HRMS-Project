import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'humanresource.settings')
django.setup()

from hr.models import Employee, Department, Position, Role, EmployeeStatus
from django.contrib.auth.models import User

name_filter = {'first_name__iexact': 'Natnael', 'last_name__iexact': 'Ashagre'}
existing = Employee.objects.filter(**name_filter)
print('existing count:', existing.count())

department = Department.objects.filter(name__iexact='computerscience').first()
if not department:
    department = Department.objects.create(name='ComputerScience', description='Computer Science department')
    print('created department', department.id)
else:
    print('found department', department.id)

position = Position.objects.filter(title__iexact='lecturer').first()
if not position:
    position = Position.objects.create(title='Lecturer', grade_level=1, base_salary=0)
    print('created position', position.id)
else:
    print('found position', position.id)

role = Role.objects.filter(name__iexact='employee').first()
if not role:
    role = Role.objects.create(name='employee')
    print('created role', role.id)
else:
    print('found role', role.id)

status = EmployeeStatus.objects.filter(name__iexact='active').first()
if not status:
    status = EmployeeStatus.objects.create(name='Active')
    print('created status', status.id)
else:
    print('found status', status.id)

if existing.exists():
    employee = existing.first()
    employee.phone = '0912345678'
    employee.department = department
    employee.position = position
    employee.role = role
    employee.status = status
    employee.save()
    print('updated employee', employee.id)
else:
    user = User.objects.create(username='natnael.ashagre', email='')
    user.set_unusable_password()
    user.save()
    employee = Employee.objects.create(
        user=user,
        first_name='Natnael',
        last_name='Ashagre',
        phone='0912345678',
        department=department,
        position=position,
        role=role,
        status=status,
        hire_date='2026-01-01',
        employee_id='NA001',
    )
    print('created employee', employee.id)
