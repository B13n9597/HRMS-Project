from hr.models import LeaveBalance, LeaveType, Employee

lt = LeaveType.objects.filter(name__icontains='sabbat').first()
if not lt:
    print('No sabbatical leave type found')
else:
    rows = LeaveBalance.objects.filter(leave_type=lt, remaining_days__gt=0)
    print('Found', rows.count(), 'non-zero sabbatical balances')
    for r in rows:
        e = r.employee
        print('Employee id', e.id, e.get_full_name(), 'hire:', e.hire_date, 'allocated:', r.allocated_days, 'remaining:', r.remaining_days, 'used:', r.used_days)
