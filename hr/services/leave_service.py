# hr/services/leave_service.py
#
# All leave business logic.
# Views call these — no DB queries in views.

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError

from hr.holiday_checker import is_day_off
from hr.models import LeaveRequest, LeaveBalance, LeaveType, Employee


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
        # Calculate allocated days (annual leave uses tenure-based formula)
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
                'last_updated':   today,
            }
        )
        if not created:
            # Refresh allocated_days for annual leave every year
            if lt.name.lower() == 'annual' and balance.allocated_days != allocated:
                extra = allocated - balance.allocated_days
                balance.allocated_days = allocated
                balance.remaining_days = max(0, balance.remaining_days + extra)
                balance.last_updated = today
                balance.save(update_fields=['allocated_days', 'remaining_days', 'last_updated'])


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
    return (
        LeaveRequest.objects
        .filter(status='Pending')
        .select_related('employee', 'leave_type', 'employee__department')
        .order_by('-id')
    )


def get_pending_requests_for_departments(department_ids):
    """Supervisor: pending requests scoped to their departments."""
    return (
        LeaveRequest.objects
        .filter(status='Pending', employee__department_id__in=department_ids)
        .select_related('employee', 'leave_type', 'employee__department')
        .order_by('-id')
    )


def get_all_requests():
    return (
        LeaveRequest.objects
        .select_related('employee', 'leave_type', 'employee__department')
        .order_by('-id')
    )


def get_requests_for_departments(department_ids):
    return (
        LeaveRequest.objects
        .filter(employee__department_id__in=department_ids)
        .select_related('employee', 'leave_type', 'employee__department')
        .order_by('-id')
    )


def get_employee_requests(employee_id: int):
    employee = get_object_or_404(Employee, pk=employee_id)
    return LeaveRequest.objects.filter(employee=employee).select_related('leave_type').order_by('-id')


def submit_leave_request(employee_id: int, data: dict) -> LeaveRequest:
    """
    Employee submits a leave request.
    Validates balance. Counts working days only.
    Accepts optional document file.
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

    # Ensure balance record exists
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
        employee       = employee,
        leave_type     = leave_type,
        start_date     = start,
        end_date       = end,
        requested_days = requested_days,
        comments       = data.get('reason', ''),
        status         = 'Pending',
    )

    # Attach document if provided
    doc = data.get('document')
    if doc:
        req.document = doc
        req.save(update_fields=['document'])

    return req


def approve_request(request_id: int, approver: Employee) -> LeaveRequest:
    """Approve and deduct from balance."""
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
        balance.last_updated   = timezone.localdate()
        balance.save()

    return req


def reject_request(request_id: int, approver: Employee, note: str = '') -> LeaveRequest:
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


def get_leave_balance(employee_id: int) -> list:
    employee = get_object_or_404(Employee, pk=employee_id)
    ensure_leave_balances(employee)
    return LeaveBalance.objects.filter(
        employee=employee,
    ).select_related('leave_type')
