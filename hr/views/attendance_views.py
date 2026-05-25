from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required

# Security tools for Rate Limiting
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.throttling import AnonRateThrottle

# Import your models and your 30-second QR utilities
from hr.models import Employee, Attendance, QRScanLog, SystemSetting
from hr.utils import generate_daily_token, verify_daily_token

# ============================================================
#  1. STANDARDIZED JSON RESPONSES (Fix 7)
#  Ensures your React frontend always gets the exact same format.
# ============================================================
def ok(data: dict, status: int = 200):
    return JsonResponse({'success': True,  'data': data,  'error': None}, status=status)

def err(message: str, status: int = 400):
    return JsonResponse({'success': False, 'data': None,  'error': message}, status=status)

# ============================================================
#  2. SECURITY LOGGING HELPERS (Fix 4)
#  Catches IP addresses of anyone trying to scan fake codes.
# ============================================================
def get_client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

def log_failed_scan(request, employee=None, reason=''):
    QRScanLog.objects.create(
        employee=employee,
        scan_type='failed',
        is_successful=False,
        ip_address=get_client_ip(request),
        failure_reason=reason,
    )

# ============================================================
#  3. THE HARDENED SCANNER ENDPOINT (Fix 1 & Fix 5)
#  Limits to 10 scans per minute to prevent brute-force attacks.
# ============================================================
class QRScanThrottle(AnonRateThrottle):
    scope = 'qr_scan'

@api_view(['POST'])
@throttle_classes([QRScanThrottle])
def scan_qr_secure(request):
    """
    POST /api/attendance/scan/
    The office tablet sends the scanned QR token here.
    """
    signed_token = request.data.get('token', '')

    if not signed_token:
        log_failed_scan(request, reason='No token in request body')
        return err('Token is required.', status=400)

    # 1. Verify the 30-second signed token using your utils.py
    employee, token_error = verify_daily_token(signed_token)

    if not employee:
        log_failed_scan(request, reason=token_error)
        return err(token_error, status=403)

    now = timezone.now()
    now_local = timezone.localtime(now)
    today = timezone.localdate()

    # 2. Core logic: Check them in or check them out
    attendance, created = Attendance.objects.get_or_create(
        employee=employee,
        date=today,
        defaults={'time_in': now, 'status': 'Present'},
    )

    if created:
        # First scan of the day -> Clock In
        attendance.calculate_status() # Assuming you have this method to check 'Late' vs 'Present'
        attendance.save()
        QRScanLog.objects.create(
            employee=employee, scan_type='time_in', is_successful=True, ip_address=get_client_ip(request)
        )
        return ok({
            'result':   'time_in',
            'employee': employee.get_full_name(),
            'time':     now_local.strftime('%H:%M:%S'),
            'message':  f"Welcome, {employee.first_name}! Clocked in successfully."
        })

    elif attendance.time_out is None:
        # Second scan of the day -> Clock Out
        attendance.time_out = now
        attendance.save()
        hours = round((now - attendance.time_in).total_seconds() / 3600, 2)
        QRScanLog.objects.create(
            employee=employee, scan_type='time_out', is_successful=True, ip_address=get_client_ip(request)
        )
        return ok({
            'result':       'time_out',
            'employee':     employee.get_full_name(),
            'time':         now_local.strftime('%H:%M:%S'),
            'hours_worked': hours,
            'message':      f"Goodbye, {employee.first_name}! You worked {hours} hours."
        })

    else:
        # Third scan of the day -> Already clocked out
        QRScanLog.objects.create(
            employee=employee, scan_type='duplicate', is_successful=False, ip_address=get_client_ip(request)
        )
        return ok({
            'result':   'already_complete',
            'employee': employee.get_full_name(),
            'message':  'Attendance already fully recorded for today.'
        })


# ============================================================
#  4. EMPLOYEE & HR VIEWS
#  The rest of the endpoints mapped in your urls.py
# ============================================================

@login_required
def my_qr_code(request):
    """
    GET /api/attendance/my-qr/
    Returns the rotating 30-second token for the React app to render as a QR code.
    """
    employee = get_object_or_404(Employee, user=request.user)
    token = generate_daily_token(employee)
    return ok({'qr_token': token, 'expires_in_seconds': 30})

@login_required
def today_attendance(request):
    """
    GET /api/attendance/today/
    For HR: Returns a list of everyone who checked in today.
    """
    # Verify user has HR/Admin role here
    today = timezone.localdate()
    records = Attendance.objects.filter(date=today).values(
        'employee__first_name', 'employee__last_name', 'time_in', 'time_out', 'status'
    )
    return ok(list(records))

@login_required
def my_attendance(request):
    """
    GET /api/attendance/my-record/
    For Employee: See their own attendance history.
    """
    employee = get_object_or_404(Employee, user=request.user)
    records = Attendance.objects.filter(employee=employee).order_by('-date')[:30] # Last 30 days
    
    data = []
    for r in records:
        data.append({
            'date': r.date,
            'time_in': r.time_in.strftime('%H:%M') if r.time_in else None,
            'time_out': r.time_out.strftime('%H:%M') if r.time_out else None,
            'status': r.status
        })
    return ok(data)

@login_required
def employee_attendance_report(request, employee_id):
    """
    GET /api/attendance/report/<employee_id>/
    For HR: Look up a specific employee's history.
    """
    # Verify user has HR/Admin role here
    employee = get_object_or_404(Employee, id=employee_id)
    records = Attendance.objects.filter(employee=employee).order_by('-date')[:30]
    
    data = [{'date': r.date, 'status': r.status} for r in records]
    return ok({'employee': employee.get_full_name(), 'history': data})