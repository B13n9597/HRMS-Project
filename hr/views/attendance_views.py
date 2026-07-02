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
    if query:
        records = records.filter(employee__first_name__icontains=query) | records.filter(employee__last_name__icontains=query)

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


@login_required(login_url='/login/')
def manual_attendance(request):
    """
    Employee manually submits attendance (date, time in, time out, signature).
    Saves to DB and redirects to own attendance logs page.
    """
    from hr.forms import ManualAttendanceForm, EmployeeKioskForm

    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "No employee profile linked to your account.")
        return redirect('/')

    # HR users keep the full manual form (date/time). Employees get a simplified
    # kiosk-style form: enter PIN + signature (name shown/read-only), submit now.
    simple_mode = not is_hr(request.user)

    if request.method == 'POST':
        if simple_mode:
            form = EmployeeKioskForm(request.POST)
            if form.is_valid():
                pin_entered = form.cleaned_data['pin']
                if pin_entered != employee.attendance_pin:
                    messages.error(request, "Invalid Attendance PIN.")
                    context = {'form': form, 'employee': employee, 'active_page': 'manual_attendance', 'simple_mode': True}
                    return render(request, 'hr/manual_attendance.html', context)

                sig_text = form.cleaned_data.get('signature', '')
                from datetime import datetime
                now = timezone.now()
                today = timezone.localdate()

                # Create or update today's attendance: if no record → time_in, else set time_out
                obj, created = Attendance.objects.get_or_create(
                    employee=employee,
                    date=today,
                    defaults={'time_in': now, 'status': 'Present', 'signature_text': sig_text},
                )
                if not created:
                    if obj.time_out is None:
                        obj.time_out = now
                        if not obj.signature_text:
                            obj.signature_text = sig_text
                        obj.save()
                        messages.success(request, f"Clock-out recorded at {now.strftime('%H:%M')}.")
                    else:
                        messages.info(request, "Attendance already completed for today.")
                else:
                    messages.success(request, f"Clock-in recorded at {now.strftime('%H:%M')}.")
                return redirect('my_attendance_record')
        else:
            form = ManualAttendanceForm(request.POST)
            if form.is_valid():
                pin_entered = form.cleaned_data['pin']
                if pin_entered != employee.attendance_pin:
                    messages.error(request, "Invalid Attendance PIN.")
                    context = {
                        'form':        form,
                        'employee':    employee,
                        'active_page': 'manual_attendance',
                        'simple_mode': False,
                    }
                    return render(request, 'hr/manual_attendance.html', context)

                date     = form.cleaned_data['date']
                time_in  = form.cleaned_data['time_in']
                time_out = form.cleaned_data['time_out']
                sig_text = form.cleaned_data.get('signature', '')

                # Combine date + time into datetime objects (naive → aware)
                from datetime import datetime
                tz = timezone.get_current_timezone()
                dt_in  = tz.localize(datetime.combine(date, time_in))
                dt_out = tz.localize(datetime.combine(date, time_out))

                # update_or_create so an existing QR-scanned record is not duplicated
                obj, created = Attendance.objects.update_or_create(
                    employee=employee,
                    date=date,
                    defaults={
                        'time_in':        dt_in,
                        'time_out':       dt_out,
                        'status':         'Present',
                        'signature_text': sig_text,
                    },
                )
                action = 'submitted' if created else 'updated'
                messages.success(request, f"Attendance {action} for {date}.")
                return redirect('my_attendance_record')
    else:
        if simple_mode:
            form = EmployeeKioskForm(initial={'name': employee.get_full_name()})
        else:
            form = ManualAttendanceForm(initial={'date': timezone.localdate()})

    context = {
        'form':        form,
        'employee':    employee,
        'active_page': 'manual_attendance',
        'simple_mode': simple_mode,
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
    """Employee's own attendance history."""
    history = get_my_attendance(request.user)
    context = {
        'records':     history,
        'active_page': 'my_attendance',
    }
    return render(request, 'hr/my_attendance.html', context)


@login_required(login_url='/login/')
def employee_attendance_report(request, employee_id):
    """HR views one employee's monthly attendance."""
    if not is_hr(request.user):
        return redirect('/login/')
    history = get_employee_attendance_report(employee_id)
    return render(request, 'hr/employee_report.html', history)


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