# hrms/views/attendance_views.py
#
# Attendance Logs + Live Attendance dashboard views + Manual Attendance.
# All logic delegated to attendance_service where applicable.

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from hr.services.attendance_service import (
    get_todays_attendance,
    get_employee_attendance_report,
    get_my_attendance,
    process_qr_scan,
    log_scan,
    get_employee_qr_token,
)
from hr.models import Employee, Attendance


def is_hr(user):
    """Check if user is HR manager or admin."""
    if user.is_superuser or user.is_staff:
        return True
    try:
        employee = Employee.objects.get(user=user)
        if employee.role and 'hr' in employee.role.name.lower():
            return True
    except Employee.DoesNotExist:
        pass
    return False


@login_required(login_url='/login/')
def attendance_logs(request):
    """
    HR sees filterable attendance logs for all employees.
    Filters: department, status, month, year via GET params.
    """
    if not is_hr(request.user):
        return redirect('/login/')

    from hr.models import Department

    month    = int(request.GET.get('month', timezone.localdate().month))
    year     = int(request.GET.get('year',  timezone.localdate().year))
    dept_id  = request.GET.get('department_id')
    status_f = request.GET.get('status', '')
    query    = request.GET.get('q', '').strip()

    records = (
        Attendance.objects
        .filter(date__month=month, date__year=year)
        .select_related('employee', 'employee__department')
        .order_by('-date', 'employee__last_name')
    )

    if dept_id:
        records = records.filter(employee__department_id=dept_id)
    if status_f:
        records = records.filter(status=status_f)
    from django.db.models import Q
    if query:
        records = records.filter(Q(employee__first_name__icontains=query) | Q(employee__last_name__icontains=query))

    departments = Department.objects.all()

    context = {
        'records':     records,
        'departments': departments,
        'month':       month,
        'year':        year,
        'dept_id':     dept_id or '',
        'status_f':    status_f,
        'search_query': query,
        'months': [
            (1,'January'),(2,'February'),(3,'March'),(4,'April'),
            (5,'May'),(6,'June'),(7,'July'),(8,'August'),
            (9,'September'),(10,'October'),(11,'November'),(12,'December')
        ],
        'years':    [2024, 2025, 2026],
        'statuses': ['Present','Late','Absent','On Leave'],
        'active_page': 'attendance_logs',
    }
    return render(request, 'hr/attendance_logs.html', context)


def manual_attendance(request):
    """
    Employee manually submits attendance (PIN + canvas signature).
    - First submission = clock-in
    - Second submission (same day) = clock-out
    Saves to DB and redirects. Supports unauthenticated kiosk access.
    """
    # If logged in, find employee profile
    employee = None
    if request.user.is_authenticated:
        try:
            employee = Employee.objects.get(user=request.user)
        except Employee.DoesNotExist:
            pass

    simple_mode = True
    if request.user.is_authenticated and is_hr(request.user):
        simple_mode = False

    if request.method == 'POST':
        pin_entered   = request.POST.get('pin', '').strip()
        sig_data      = request.POST.get('signature_data', '').strip()
        sig_text_only = request.POST.get('signature', '').strip()

        # If public kiosk access, find employee by form parameter
        if not employee:
            emp_id = request.POST.get('employee_id')
            if emp_id:
                try:
                    employee = Employee.objects.get(id=emp_id)
                except Employee.DoesNotExist:
                    pass

        if not employee:
            messages.error(request, "Please select/provide a valid employee name.")
        # Validate PIN (both attendance_pin and legacy pin fields)
        elif pin_entered != (employee.attendance_pin or employee.pin or ''):
            messages.error(request, "Invalid Attendance PIN. Please try again.")
        else:
            now   = timezone.now()
            today = timezone.localdate()

            # Decode canvas base64 signature
            sig_file = None
            if sig_data and sig_data.startswith('data:image/'):
                import base64, uuid as _uuid
                from django.core.files.base import ContentFile
                try:
                    fmt, imgstr = sig_data.split(';base64,')
                    ext = fmt.split('/')[-1]
                    decoded = base64.b64decode(imgstr)
                    sig_file = ContentFile(
                        decoded,
                        name=f"sig_{employee.employee_id}_{_uuid.uuid4().hex[:8]}.{ext}"
                    )
                except Exception:
                    pass

            if simple_mode:
                # Simple kiosk mode: check-in then check-out today
                obj, created = Attendance.objects.get_or_create(
                    employee=employee,
                    date=today,
                    defaults={
                        'time_in':       now,
                        'status':        'Present',
                        'signature_text': sig_text_only or employee.get_full_name(),
                    },
                )
                if created:
                    obj.calculate_status()
                    if sig_file:
                        obj.signature = sig_file
                    obj.save()
                    messages.success(request, f"Clock-in recorded for {employee.get_full_name()} at {timezone.localtime(now).strftime('%H:%M')}.")
                elif obj.time_out is None:
                    obj.time_out = now
                    if not obj.signature_text:
                        obj.signature_text = sig_text_only or employee.get_full_name()
                    if sig_file:
                        obj.signature = sig_file
                    obj.save()
                    messages.success(request, f"Clock-out recorded for {employee.get_full_name()} at {timezone.localtime(now).strftime('%H:%M')}.")
                else:
                    messages.info(request, f"Attendance already completed for {employee.get_full_name()} today.")
            else:
                # Full HR mode: allow specifying date and times
                from hr.forms import ManualAttendanceForm
                form = ManualAttendanceForm(request.POST)
                if form.is_valid():
                    date     = form.cleaned_data['date']
                    time_in  = form.cleaned_data['time_in']
                    time_out = form.cleaned_data.get('time_out')
                    from datetime import datetime
                    tz_local = timezone.get_current_timezone()
                    dt_in  = tz_local.localize(datetime.combine(date, time_in))
                    dt_out = tz_local.localize(datetime.combine(date, time_out)) if time_out else None

                    defaults = {
                        'time_in':        dt_in,
                        'status':         'Present',
                        'signature_text': sig_text_only or employee.get_full_name(),
                    }
                    if dt_out:
                        defaults['time_out'] = dt_out

                    obj, created = Attendance.objects.update_or_create(
                        employee=employee,
                        date=date,
                        defaults=defaults,
                    )
                    obj.calculate_status()
                    if sig_file:
                        obj.signature = sig_file
                    obj.save()
                    action = 'submitted' if created else 'updated'
                    messages.success(request, f"Attendance {action} for {employee.get_full_name()} on {date}.")
                else:
                    active_employees = Employee.objects.filter(status__name='Active').order_by('first_name', 'last_name')
                    context = {
                        'form':        form,
                        'employee':    employee,
                        'active_page': 'manual_attendance',
                        'simple_mode': False,
                        'active_employees': active_employees,
                    }
                    return render(request, 'hr/manual_attendance.html', context)

            if request.user.is_authenticated:
                return redirect('my_attendance_record')
            else:
                return redirect('tablet_kiosk')

    # GET — show empty form
    from hr.forms import ManualAttendanceForm, EmployeeKioskForm
    active_employees = Employee.objects.filter(status__name='Active').order_by('first_name', 'last_name')

    if simple_mode:
        initial_name = employee.get_full_name() if employee else ""
        form = EmployeeKioskForm(initial={'name': initial_name})
    else:
        form = ManualAttendanceForm(initial={'date': timezone.localdate()})

    context = {
        'form':        form,
        'employee':    employee,
        'active_page': 'manual_attendance',
        'simple_mode': simple_mode,
        'active_employees': active_employees,
    }
    return render(request, 'hr/manual_attendance.html', context)


@login_required(login_url='/login/')
def live_attendance(request):
    """Live attendance page — today's summary + kiosk simulator."""
    if not is_hr(request.user):
        return redirect('/login/')
    from hr.models import Employee as Emp
    today_data = get_todays_attendance()
    employees  = Emp.objects.select_related('department').order_by('first_name')
    context = {
        'today':       today_data,
        'employees':   employees,
        'active_page': 'live_attendance',
    }
    return render(request, 'hr/live_attendance.html', context)


@csrf_exempt
def api_scan(request):
    """
    POST /api/scan/  { "token": "<uuid>" }
    Called by the kiosk simulator on the frontend.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    import json
    try:
        body  = json.loads(request.body)
        token = body.get('token', '')
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    class MockRequest:
        def __init__(self):
            self.META = request.META
            self.data = {'token': token}

    try:
        result = process_qr_scan(MockRequest())
        return JsonResponse(result, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required(login_url='/login/')
def my_attendance(request):
    """Employee's own attendance history with optional month/year/status filters."""
    month    = request.GET.get('month', '')
    year     = request.GET.get('year', '')
    status_f = request.GET.get('status', '')
    query    = request.GET.get('q', '').strip()

    from hr.models import Employee as Emp
    employee = None
    try:
        employee = Emp.objects.get(user=request.user)
    except Emp.DoesNotExist:
        pass

    history = []
    if employee:
        history = get_my_attendance(
            request.user,
            month=int(month) if month else None,
            year=int(year) if year else None,
            status_filter=status_f or None,
        )

    from django.utils import timezone as tz
    context = {
        'records':      history,
        'employee':     employee,
        'month':        month or tz.localdate().month,
        'year':         year  or tz.localdate().year,
        'status_f':     status_f,
        'search_query': query,
        'months': [
            (1,'January'),(2,'February'),(3,'March'),(4,'April'),
            (5,'May'),(6,'June'),(7,'July'),(8,'August'),
            (9,'September'),(10,'October'),(11,'November'),(12,'December')
        ],
        'years':    [2024, 2025, 2026],
        'active_page': 'my_attendance',
    }
    return render(request, 'hr/my_attendance.html', context)


@login_required(login_url='/login/')
def employee_attendance_report(request, employee_id):
    """HR views one employee's monthly attendance."""
    if not is_hr(request.user):
        return redirect('/login/')
    history = get_employee_attendance_report(employee_id)
    # Reuse attendance_logs template scoped to one employee
    return render(request, 'hr/attendance_logs.html', {
        **history,
        'single_employee_mode': True,
        'active_page': 'attendance_logs',
        'months': [
            (1,'January'),(2,'February'),(3,'March'),(4,'April'),
            (5,'May'),(6,'June'),(7,'July'),(8,'August'),
            (9,'September'),(10,'October'),(11,'November'),(12,'December')
        ],
        'years': [2024, 2025, 2026],
        'statuses': ['Present', 'Late', 'Absent', 'On Leave'],
        'departments': [],
    })


# ─────────────────────────────────────────────
# JSON API ENDPOINTS FOR FRONTEND SPA
# ─────────────────────────────────────────────

@login_required(login_url='/login/')
def my_qr_code(request):
    """Get the rotating QR token for the logged-in employee."""
    try:
        data = get_employee_qr_token(request.user)
        return JsonResponse({'success': True, 'data': data}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required(login_url='/login/')
def today_attendance(request):
    """Get today's attendance for HR dashboard live tracker."""
    if not is_hr(request.user):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    try:
        data = get_todays_attendance()
        return JsonResponse({'success': True, 'data': data}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
def scan_qr_secure(request):
    """QR scan endpoint for kiosk or frontend scanner."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    import json
    try:
        body  = json.loads(request.body)
        token = body.get('token', '')
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    class MockRequest:
        def __init__(self, http_request):
            self.META = http_request.META
            self.data = {'token': token}

    try:
        result = process_qr_scan(MockRequest(request))
        return JsonResponse({'success': True, 'data': result}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)