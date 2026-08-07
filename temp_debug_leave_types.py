from hr.models import LeaveType, Employee
from hr.services.leave_service import get_leave_types_for_employee, get_leave_balance

print('LeaveType names:')
for lt in LeaveType.objects.order_by('name'):
    print('-', lt.name)

emp = Employee.objects.filter(first_name__iexact='Alem', last_name__iexact='Ashenafi').first()
print('\nEmployee:', emp and emp.id, emp and emp.gender)
if emp:
    print('Allowed types for Alem:')
    for lt in get_leave_types_for_employee(emp):
        print('-', lt.name)
    print('Balances for Alem:')
    for b in get_leave_balance(emp.id):
        print('-', b.leave_type.name, 'allocated=', b.allocated_days, 'remaining=', b.remaining_days)
