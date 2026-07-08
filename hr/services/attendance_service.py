# hr/services/attendance_service.py

from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.cache import cache

from hr.models import Employee, Attendance, QRScanLog
from hr.utils import generate_daily_token, verify_daily_token


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

TOKEN_TTL_SECONDS = 30


# ─────────────────────────────────────────────
# IP + DEVICE INFO
# ─────────────────────────────────────────────

def get_client_ip(request) -> str:
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def get_user_agent(request) -> str:
    return request.META.get('HTTP_USER_AGENT', '')


# ─────────────────────────────────────────────
# SCAN LOGGING
# ─────────────────────────────────────────────

def log_scan(request, employee=None, scan_type='failed', is_successful=False, failure_reason=''):
    QRScanLog.objects.create(
        employee=employee,
        scan_type=scan_type,
        is_successful=is_successful,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        failure_reason=failure_reason,
    )


# ─────────────────────────────────────────────
# TOKEN GENERATION
# ─────────────────────────────────────────────

def get_employee_qr_token(user) -> dict:
    from django.shortcuts import get_object_or_404

    employee = get_object_or_404(Employee, user=user)
    token = generate_daily_token(employee)

    return {
        'token': token,
        'expires_in_seconds': TOKEN_TTL_SECONDS,
    }


# ─────────────────────────────────────────────
# TOKEN REPLAY PROTECTION
# ─────────────────────────────────────────────

def _is_token_used(token: str) -> bool:
    return cache.get(f"used_qr:{token}") is not None


def _mark_token_used(token: str):
    cache.set(f"used_qr:{token}", True, timeout=TOKEN_TTL_SECONDS)


# ─────────────────────────────────────────────
# CORE SCAN LOGIC
# ─────────────────────────────────────────────

def process_qr_scan(request) -> dict:
    signed_token = request.data.get('token', '')

    if not signed_token:
        log_scan(request, failure_reason='No token provided')
        raise ValidationError('Token is required.')

    # 🔐 Prevent replay attack
    if _is_token_used(signed_token):
        log_scan(request, failure_reason='Token already used')
        raise ValidationError('Token already used.')

    employee, token_error = verify_daily_token(signed_token)

    if not employee:
        log_scan(request, failure_reason=token_error)
        raise ValidationError(token_error)

    # Mark token as used AFTER verification
    _mark_token_used(signed_token)

    now = timezone.now()
    now_local = timezone.localtime(now)
    today = timezone.localdate()

    attendance, created = Attendance.objects.get_or_create(
        employee=employee,
        date=today,
        defaults={'time_in': now, 'status': 'Present'},
    )

    # ───────── CLOCK IN ─────────
    if created:
        attendance.calculate_status()
        attendance.save()

        log_scan(request, employee=employee, scan_type='time_in', is_successful=True)

        return {
            'result': 'time_in',
            'employee': employee.get_full_name(),
            'time': now_local.strftime('%H:%M:%S'),
            'message': f"Welcome, {employee.first_name}! Clocked in.",
        }

    # ───────── CLOCK OUT ─────────
    elif attendance.time_out is None:
        attendance.time_out = now
        attendance.save()

        hours = _calculate_hours_worked(attendance.time_in, now)

        log_scan(request, employee=employee, scan_type='time_out', is_successful=True)

        return {
            'result': 'time_out',
            'employee': employee.get_full_name(),
            'time': now_local.strftime('%H:%M:%S'),
            'hours_worked': hours,
            'message': f"Goodbye, {employee.first_name}! Worked {hours} hrs.",
        }

    # ───────── DUPLICATE ─────────
    else:
        log_scan(request, employee=employee, scan_type='duplicate', is_successful=False)

        return {
            'result': 'already_complete',
            'employee': employee.get_full_name(),
            'message': 'Attendance already recorded today.',
        }


# ─────────────────────────────────────────────
# REPORTING
# ─────────────────────────────────────────────

def get_todays_attendance() -> dict:
    """Return today's attendance records with summary counts for the Live Attendance page."""
    from hr.models import Department
    today = timezone.localdate()
    total_employees = Employee.objects.count()

    records_qs = (
        Attendance.objects
        .filter(date=today)
        .select_related('employee', 'employee__department')
        .order_by('time_in')
    )

    records = []
    for r in records_qs:
        records.append({
            'employee_name': r.employee.get_full_name(),
            'employee_id':   r.employee.employee_id or '',
            'department':    r.employee.department.name if r.employee.department else '',
            'time_in':       r.time_in.isoformat() if r.time_in else None,
            'time_out':      r.time_out.isoformat() if r.time_out else None,
            'status':        r.status,
        })

    present_count = sum(1 for r in records if r['status'] == 'Present')
    late_count    = sum(1 for r in records if r['status'] == 'Late')
    absent_count  = max(0, total_employees - len(records))

    return {
        'records':         records,
        'total_employees': total_employees,
        'present_count':   present_count,
        'late_count':      late_count,
        'absent_count':    absent_count,
    }


def get_my_attendance(user, month=None, year=None, status_filter=None):
    """Return the employee's own Attendance queryset (not dicts) for template rendering."""
    from django.shortcuts import get_object_or_404
    employee = get_object_or_404(Employee, user=user)

    qs = Attendance.objects.filter(employee=employee).order_by('-date')
    if month:
        qs = qs.filter(date__month=month)
    if year:
        qs = qs.filter(date__year=year)
    if status_filter:
        qs = qs.filter(status=status_filter)
    return qs[:60]


def get_employee_attendance_report(employee_id: int) -> dict:
    from django.shortcuts import get_object_or_404

    employee = get_object_or_404(Employee, id=employee_id)

    records = Attendance.objects.filter(employee=employee).order_by('-date')[:30]

    return {
        'employee': employee.get_full_name(),
        'history': [
            {
                'date': r.date,
                'status': r.status,
            }
            for r in records
        ],
    }


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _calculate_hours_worked(time_in, time_out) -> float:
    return round((time_out - time_in).total_seconds() / 3600, 2)