from hr.models import Employee, LeaveBalance, LeaveType
from hr.services.leave_service import sabbatical_eligibility, get_sabbatical_days_for_employee

e = Employee.objects.first()
if not e:
    print('No employee found')
else:
    print('Employee:', e.get_full_name(), 'id:', e.id)
    print('hire_date:', e.hire_date)
    print('years_completed:', sabbatical_eligibility(e)['years_completed'])
    print('sabbatical_eligible:', sabbatical_eligibility(e)['eligible'])
    lt = LeaveType.objects.filter(name__iexact='Sabbatical').first()
    print('Sabbatical LeaveType max_days:', lt.max_days if lt else None)
    lb = LeaveBalance.objects.filter(employee=e, leave_type=lt).first()
    if not lb:
        print('No sabbatical LeaveBalance')
    else:
        print('LeaveBalance allocated:', lb.allocated_days, 'remaining:', lb.remaining_days, 'used:', lb.used_days)
        print('get_sabbatical_days_for_employee:', get_sabbatical_days_for_employee(e))
