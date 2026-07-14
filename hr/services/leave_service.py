# hr/services/leave_service.py
#
# All leave business logic.
# Views call these — no DB queries in views.

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError

from hr.holiday_checker import is_day_off
from hr.models import LeaveRequest, LeaveBalance, LeaveType, Employee, SystemSetting


# ── Policy leave types ──────────────────────────────────────────────────────
POLICY_LEAVE_TYPES = [
    {'name': 'Annual',      'max_days': 18, 'description': 'Annual leave. Starts at 18 days/year and increases yearly.'},
    {'name': 'Sick',        'max_days': 30, 'description': 'Sick leave with medical certificate.'},
    {'name': 'Maternity',   'max_days': 90, 'description': 'Maternity leave (3 months).'},
    {'name': 'Paternity',   'max_days': 5,  'description': 'Paternity leave (5 days).'},
    {'name': 'Mourning',    'max_days': 3,  'description': 'Bereavement/mourning leave (3 days).'},
    {'name': 'Unpaid',      'max_days': 30, 'description': 'Unpaid leave approved by HR.'},
    {'name': 'Educational', 'max_days': 14, 'description': 'Study/exam leave.'},
]


def seed_leave_types():
    """Ensure all 7 policy leave types exist in the DB."""
    for lt in POLICY_LEAVE_TYPES:
        LeaveType.objects.get_or_create(
            name=lt['name'],
            defaults={'max_days': lt['max_days'], 'description': lt['description']}
        )


def get_annual_leave_days_for_employee(employee: Employee) -> int:
    """
    Annual leave starts at 18 days and increases by 1 day per completed year of service.
    Max is capped at 30 days.
    """
    if not employee.hire_date:
        return 18
    today = timezone.localdate()
    years = (today - employee.hire_date).days // 365
    return min(18 + years, 30)


def ensure_leave_balances(employee: Employee):
    """
    Create or refresh leave balances for an employee.
    Called on first login, leave submission, and by the annual reset management command.
    """
    seed_leave_types()
    today = timezone.localdate()
    for lt in LeaveType.objects.all():
        if lt.name.lower() == 'annual':
            allocated = get_annual_leave_days_for_employee(employee)
        else:
            allocated = lt.max_days

        balance, created = LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=lt,
            defaults={
                'allocated_days': allocated,
                'used_days':      0,
                'remaining_days': allocated,
            }
        )
        if not created:
            if lt.name.lower() == 'annual' and balance.allocated_days != allocated:
                extra = allocated - balance.allocated_days
                balance.allocated_days = allocated
                balance.remaining_days = max(0, balance.remaining_days + extra)
                balance.save(update_fields=['allocated_days', 'remaining_days'])


def is_working_day(date) -> bool:
    """Returns True if date is a working day (not weekend or holiday)."""
    return not is_day_off(date)


def count_working_days(start_date, end_date) -> int:
    """Count working days (Mon–Fri, excluding public holidays) between dates inclusive."""
    from datetime import timedelta
    count = 0
    current = start_date
    while current <= end_date:
        if is_working_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def get_all_leave_types():
    seed_leave_types()
    return LeaveType.objects.all().order_by('name')


def get_pending_requests():
    """
    Pending requests where supervisor has already reviewed (recommended or not),
    waiting for HR final decision. Also includes requests with no supervisor yet
    so HR can always see all pending leaves.
    """
    return (
        LeaveRequest.objects
        .filter(status='Pending')
        .select_related('employee', 'leave_type', 'employee__department',
                        'supervisor_reviewed_by')
        .order_by('-id')
    )


def get_pending_requests_for_departments(department_ids):
    """Supervisor: pending requests scoped to their departments, not yet reviewed by supervisor."""
    return (
        LeaveRequest.objects
        .filter(
            status='Pending',
            employee__department_id__in=department_ids,
            supervisor_recommendation='',  # not yet reviewed
        )
        .select_related('employee', 'leave_type', 'employee__department')
        .order_by('-id')
    )


def get_all_requests():
    return (
        LeaveRequest.objects
        .select_related('employee', 'leave_type', 'employee__department',
                        'supervisor_reviewed_by', 'approved_by')
        .order_by('-id')
    )


def get_requests_for_departments(department_ids):
    return (
        LeaveRequest.objects
        .filter(employee__department_id__in=department_ids)
        .select_related('employee', 'leave_type', 'employee__department',
                        'supervisor_reviewed_by')
        .order_by('-id')
    )


def get_employee_requests(employee_id: int):
    employee = get_object_or_404(Employee, pk=employee_id)
    return (
        LeaveRequest.objects
        .filter(employee=employee)
        .select_related('leave_type', 'approved_by', 'supervisor_reviewed_by')
        .order_by('-id')
    )


def submit_leave_request(employee_id: int, data: dict) -> LeaveRequest:
    """
    Employee submits a leave request.
    Validates balance. Counts working days only.
    Accepts optional document file and contact info.
    """
    employee   = get_object_or_404(Employee, pk=employee_id)
    leave_type = get_object_or_404(LeaveType, pk=data.get('leave_type_id'))

    start = data.get('start_date')
    end   = data.get('end_date')

    if end < start:
        raise ValidationError("End date cannot be before start date.")

    requested_days = count_working_days(start, end)
    if requested_days == 0:
        raise ValidationError("Selected dates contain no working days.")

    ensure_leave_balances(employee)

    balance = LeaveBalance.objects.filter(
        employee=employee, leave_type=leave_type
    ).first()

    if balance and balance.remaining_days < requested_days:
        raise ValidationError(
            f"Insufficient balance. You have {balance.remaining_days} "
            f"{leave_type.name} days remaining."
        )

    req = LeaveRequest.objects.create(
        employee                  = employee,
        leave_type                = leave_type,
        start_date                = start,
        end_date                  = end,
        requested_days            = requested_days,
        comments                  = data.get('reason', ''),
        contact_info_during_leave = data.get('contact_info_during_leave', ''),
        status                    = 'Pending',
    )

    doc = data.get('document')
    if doc:
        req.document = doc
        req.save(update_fields=['document'])

    return req


def supervisor_recommend(request_id: int, supervisor: Employee, note: str = '') -> LeaveRequest:
    """
    Supervisor marks a leave request as Recommended.
    Does NOT change status — HR still needs to make the final decision.
    """
    req = get_object_or_404(LeaveRequest, pk=request_id)
    if req.status != 'Pending':
        raise ValidationError("Only pending requests can be reviewed by supervisor.")
    if req.supervisor_recommendation != '':
        raise ValidationError("This request has already been reviewed by a supervisor.")

    req.supervisor_recommendation = 'recommended'
    req.supervisor_reviewed_by    = supervisor
    req.supervisor_reviewed_date  = timezone.localdate()
    req.supervisor_note           = note
    req.save(update_fields=[
        'supervisor_recommendation', 'supervisor_reviewed_by',
        'supervisor_reviewed_date', 'supervisor_note'
    ])
    return req


def supervisor_not_recommend(request_id: int, supervisor: Employee, note: str = '') -> LeaveRequest:
    """
    Supervisor marks a leave request as Not Recommended.
    Does NOT reject it — HR still makes the final decision.
    """
    req = get_object_or_404(LeaveRequest, pk=request_id)
    if req.status != 'Pending':
        raise ValidationError("Only pending requests can be reviewed by supervisor.")
    if req.supervisor_recommendation != '':
        raise ValidationError("This request has already been reviewed by a supervisor.")

    req.supervisor_recommendation = 'not_recommended'
    req.supervisor_reviewed_by    = supervisor
    req.supervisor_reviewed_date  = timezone.localdate()
    req.supervisor_note           = note
    req.save(update_fields=[
        'supervisor_recommendation', 'supervisor_reviewed_by',
        'supervisor_reviewed_date', 'supervisor_note'
    ])
    return req


def approve_request(request_id: int, approver: Employee) -> LeaveRequest:
    """HR approves and deducts from balance."""
    req = get_object_or_404(LeaveRequest, pk=request_id)
    if req.status != 'Pending':
        raise ValidationError("Only pending requests can be approved.")

    req.status        = 'Approved'
    req.approved_by   = approver
    req.approved_date = timezone.localdate()
    req.save()

    balance = LeaveBalance.objects.filter(
        employee=req.employee,
        leave_type=req.leave_type,
    ).first()
    if balance and req.requested_days:
        balance.used_days      = (balance.used_days or 0) + req.requested_days
        balance.remaining_days = max(0, balance.remaining_days - req.requested_days)
        balance.save()

    return req


def reject_request(request_id: int, approver: Employee, note: str = '') -> LeaveRequest:
    """HR rejects a pending leave request."""
    req = get_object_or_404(LeaveRequest, pk=request_id)
    if req.status != 'Pending':
        raise ValidationError("Only pending requests can be rejected.")

    req.status        = 'Rejected'
    req.approved_by   = approver
    req.approved_date = timezone.localdate()
    if note:
        req.comments = note
    req.save()
    return req


def cancel_request(request_id: int, employee: Employee) -> LeaveRequest:
    """
    Employee cancels their own pending leave request.
    Only Pending requests can be cancelled. Approved/Rejected cannot be cancelled.
    """
    req = get_object_or_404(LeaveRequest, pk=request_id, employee=employee)
    if req.status != 'Pending':
        raise ValidationError("Only pending requests can be cancelled.")

    req.status = 'Cancelled'
    req.save(update_fields=['status'])
    return req


def get_leave_balance(employee_id: int) -> list:
    employee = get_object_or_404(Employee, pk=employee_id)
    ensure_leave_balances(employee)
    return LeaveBalance.objects.filter(
        employee=employee,
    ).select_related('leave_type')


def process_year_end_unused_leave():
    """
    Called by a management command or scheduled task at year end.
    Reads the 'leave.unused_leave_policy' setting:
      - 'carry_forward': unused annual leave is kept for next year
      - 'expire': unused annual leave balance is reset to zero
    """
    policy = SystemSetting.get('leave', 'unused_leave_policy', 'carry_forward')
    annual_type = LeaveType.objects.filter(name__iexact='Annual').first()
    if not annual_type:
        return {'policy': policy, 'processed': 0}

    balances = LeaveBalance.objects.filter(leave_type=annual_type)
    processed = 0

    for balance in balances:
        employee = balance.employee
        new_allocated = get_annual_leave_days_for_employee(employee)

        if policy == 'carry_forward':
            # Keep remaining days and add the new year's allocation (capped at max 30)
            carried = balance.remaining_days
            total   = min(carried + new_allocated, 30)
            balance.allocated_days = total
            balance.remaining_days = total
        else:
            # expire: reset to fresh allocation for new year
            balance.allocated_days = new_allocated
            balance.remaining_days = new_allocated

        balance.used_days    = 0
        balance.save()
        processed += 1

    return {'policy': policy, 'processed': processed}
