from hr.models import Employee, LeaveBalance, LeaveType
from hr.services.leave_service import sabbatical_eligibility, get_sabbatical_days_for_employee, ensure_leave_balances

lt = LeaveType.objects.filter(name__iexact='Sabbatical').first()
print('Sabbatical leave type max_days:', lt.max_days if lt else None)

for e in Employee.objects.all()[:20]:
    elig = sabbatical_eligibility(e)
    lb = LeaveBalance.objects.filter(employee=e, leave_type=lt).first()
    if not lb:
        # ensure it exists
        ensure_leave_balances(e)
        lb = LeaveBalance.objects.filter(employee=e, leave_type=lt).first()
    rem = lb.remaining_days if lb else None
    alloc = lb.allocated_days if lb else None
    print(e.id, e.get_full_name(), 'hire:', e.hire_date, 'years:', elig['years_completed'], 'eligible:', elig['eligible'], 'allocated:', alloc, 'remaining:', rem)
