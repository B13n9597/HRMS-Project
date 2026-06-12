# hrms/services/leave_service.py
#
# All leave business logic.
# Views call these — no DB queries in views.

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError

from hrms.models import LeaveRequest, LeaveBalance, LeaveType, Employee


def get_all_leave_types():
    return LeaveType.objects.all().order_by('name')


def get_pending_requests():
    return (
        LeaveRequest.objects
        .filter(status='Pending')
        .select_related('employee', 'leave_type', 'employee__department')
        .order_by('-id')
    )


def get_all_requests():
    return (
        LeaveRequest.objects
        .select_related('employee', 'leave_type', 'employee__department')
        .order_by('-id')
    )


def get_employee_requests(employee_id: int):
    employee = get_object_or_404(Employee, pk=employee_id)
    return LeaveRequest.objects.filter(employee=employee).select_related('leave_type').order_by('-id')


def submit_leave_request(employee_id: int, data: dict) -> LeaveRequest:
    """
    Employee submits a leave request.
    Validates that they have enough balance remaining.
    """
    employee   = get_object_or_404(Employee, pk=employee_id)
    leave_type = get_object_or_404(LeaveType, pk=data.get('leave_type_id'))

    start = data.get('start_date')
    end   = data.get('end_date')

    if end < start:
        raise ValidationError("End date cannot be before start date.")

    requested_days = (end - start).days + 1

    # Check balance
    year    = start.year
    balance = LeaveBalance.objects.filter(
        employee=employee, leave_type=leave_type, year=year
    ).first()

    if balance and balance.remaining_days < requested_days:
        raise ValidationError(
            f"Insufficient balance. You have {balance.remaining_days} "
            f"{leave_type.name} days remaining."
        )

    return LeaveRequest.objects.create(
        employee       = employee,
        leave_type     = leave_type,
        start_date     = start,
        end_date       = end,
        requested_days = requested_days,
        reason         = data.get('reason', ''),
        status         = 'Pending',
    )


def approve_request(request_id: int, approver: Employee) -> LeaveRequest:
    """
    Approve a leave request and deduct from balance.
    """
    req = get_object_or_404(LeaveRequest, pk=request_id)
    if req.status != 'Pending':
        raise ValidationError("Only pending requests can be approved.")

    req.status        = 'Approved'
    req.approved_by   = approver
    req.approved_date = timezone.localdate()
    req.save()

    # Deduct from balance
    balance, _ = LeaveBalance.objects.get_or_create(
        employee   = req.employee,
        leave_type = req.leave_type,
        year       = req.start_date.year,
        defaults   = {'total_days': req.leave_type.max_days, 'used_days': 0},
    )
    balance.used_days += req.requested_days
    balance.save()

    return req


def reject_request(request_id: int, approver: Employee, note: str = '') -> LeaveRequest:
    req = get_object_or_404(LeaveRequest, pk=request_id)
    if req.status != 'Pending':
        raise ValidationError("Only pending requests can be rejected.")

    req.status         = 'Rejected'
    req.approved_by    = approver
    req.approved_date  = timezone.localdate()
    req.rejection_note = note
    req.save()
    return req


def get_leave_balance(employee_id: int) -> list:
    employee = get_object_or_404(Employee, pk=employee_id)
    return LeaveBalance.objects.filter(
        employee=employee,
        year=timezone.localdate().year,
    ).select_related('leave_type')