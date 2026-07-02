# hrms/services/leave_service.py
#
# All leave business logic.
# Views call these — no DB queries in views.

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError

from hr.models import LeaveRequest, LeaveBalance, LeaveType, Employee


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

    # Check balance if a record exists
    balance = LeaveBalance.objects.filter(
        employee=employee, leave_type=leave_type
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
        comments       = data.get('reason', ''),
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

    # Deduct from balance if a balance record exists
    balance = LeaveBalance.objects.filter(
        employee=req.employee,
        leave_type=req.leave_type,
    ).first()
    if balance and req.requested_days:
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
    return LeaveBalance.objects.filter(
        employee=employee,
    ).select_related('leave_type')