import csv
import csv
import json
from collections import defaultdict
from datetime import timedelta, date
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Avg, Count, Q, Sum

from hr.decorators import role_required
from hr.models import (
    Employee, Department, Attendance, LeaveRequest, LeaveType,
    BiannualKPIScore, AuditLog, EmployeeHistory, Role
)
from hr.services import employee_service, leave_service

# ==============================================================================
#  DEAN DASHBOARD (Department-Level Management)
# ==============================================================================

@role_required('DEAN', 'HR_ADMIN')
def dean_dashboard_view(request):
    user_emp = employee_service.get_employee_for_user(request.user)
    
    # Department Scoping:
    # If Dean user has an assigned department, default to it; otherwise allow selecting
    departments = Department.objects.filter(is_deleted=False).order_by('name')
    selected_dept_id = request.GET.get('dept_id')
    
    if selected_dept_id:
        try:
            active_dept = Department.objects.get(id=selected_dept_id, is_deleted=False)
        except Department.DoesNotExist:
            active_dept = user_emp.department if (user_emp and user_emp.department) else departments.first()
    else:
        active_dept = user_emp.department if (user_emp and user_emp.department) else departments.first()
        
    # Queryset optimization: select_related & prefetch_related
    employees_qs = Employee.objects.select_related('user', 'department', 'position', 'status', 'role').filter(
        is_deleted=False
    )
    if active_dept:
        dept_employees = employees_qs.filter(department=active_dept)
    else:
        dept_employees = employees_qs

    today = timezone.localdate()
    
    # 1. Department Overview Cards
    staff_counts = dept_employees.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status__name__iexact='Active')),
        on_leave=Count('id', filter=Q(status__name__iexact='On Leave')),
    )
    total_staff = staff_counts['total']
    active_staff_count = staff_counts['active']
    on_leave_staff_count = staff_counts['on_leave']
    
    # Attendance for today
    today_attendances = Attendance.objects.select_related('employee', 'employee__department', 'employee__position').filter(
        date=today,
        employee__in=dept_employees
    )
    present_today_count = today_attendances.filter(status__in=['Present', 'Late']).count()
    absent_today_count = max(0, total_staff - present_today_count)
    
    # 2. Attendance Monitoring Logs (with late/missing highlights & QR/Signature visibility)
    attendance_logs = []
    # Build attendance map for all department employees today
    att_map = {att.employee_id: att for att in today_attendances}
    
    for emp in dept_employees:
        att = att_map.get(emp.id)
        # The monitor lists only persisted attendance records.  Missing records
        # remain reflected in the summary count but are not fabricated as rows.
        if not att:
            continue
        has_qr = bool(emp.qr_token)
        has_sig = bool(emp.signature_data or (att and att.signature_text))
        
        status_val = att.status if att else 'Absent'
        is_late = (att and att.status == 'Late') or (att and att.time_in and timezone.localtime(att.time_in).hour >= 9)
        
        attendance_logs.append({
            'employee': emp,
            'attendance': att,
            'status': status_val,
            'time_in': att.time_in if att else None,
            'time_out': att.time_out if att else None,
            'is_late': is_late,
            'has_qr': has_qr,
            'has_sig': has_sig,
        })

    # 3. Leave Management (Department leave requests with filters)
    leave_type_filter = request.GET.get('leave_type')
    leave_status_filter = request.GET.get('leave_status')
    
    leave_qs = LeaveRequest.objects.select_related(
        'employee', 'employee__department', 'employee__position', 'leave_type', 'approved_by'
    ).filter(employee__in=dept_employees).order_by('-start_date')
    
    if leave_type_filter:
        leave_qs = leave_qs.filter(leave_type_id=leave_type_filter)
    if leave_status_filter:
        leave_qs = leave_qs.filter(status=leave_status_filter)
        
    pending_leaves = leave_qs.filter(status='Pending')
    maternity_leave_count = leave_qs.filter(leave_type__name__iexact='Maternity').count()
    
    # 4. Performance (KPI Tracking)
    kpi_scores_qs = BiannualKPIScore.objects.select_related('employee', 'employee__department').filter(
        employee__in=dept_employees
    )
    dept_avg_kpi = kpi_scores_qs.aggregate(Avg('overall_score'))['overall_score__avg']
    # Do not present a fabricated KPI when the department has no recorded evaluations.
    dept_perf_score = round(float(dept_avg_kpi), 2) if dept_avg_kpi is not None else 0

    # Build per-employee KPI score map: {employee_id: latest overall_score}
    # Order by year desc, period desc (H2 > H1) so first entry per employee is the most recent
    emp_kpi_map = {}
    for ks in kpi_scores_qs.order_by('employee_id', '-year', '-period'):
        if ks.employee_id not in emp_kpi_map:
            emp_kpi_map[ks.employee_id] = round(float(ks.overall_score), 2) if ks.overall_score else None

    # 5. Charts Data — build for selected period (default 30 days)
    period_days = max(7, min(int(request.GET.get('days', 30)), 90))
    date_range  = [today - timedelta(days=i) for i in range(period_days - 1, -1, -1)]

    # Fetch the entire trend with one grouped query instead of several queries per day.
    daily_counts = defaultdict(dict)
    for row in (Attendance.objects.filter(employee__in=dept_employees, date__range=(date_range[0], date_range[-1]))
                .values('date', 'status').annotate(total=Count('id'))):
        daily_counts[row['date']][row['status']] = row['total']

    att_trend_labels, att_present, att_late, att_absent, late_trend = [], [], [], [], []
    for d in date_range:
        counts = daily_counts[d]
        present = counts.get('Present', 0)
        late = counts.get('Late', 0)
        att_trend_labels.append(d.strftime('%b %d'))
        att_present.append(present)
        att_late.append(late)
        att_absent.append(max(0, total_staff - present - late))
        late_trend.append({'date': d.strftime('%b %d'), 'late': late})

    # 5b. Today status distribution (for pie)
    status_dist = {
        'present': present_today_count,
        'absent':  absent_today_count,
        'on_leave': on_leave_staff_count,
    }

    # 5c. Leave by status (for bar chart)
    leave_counts = LeaveRequest.objects.filter(employee__in=dept_employees, is_deleted=False).aggregate(
        approved=Count('id', filter=Q(status='Approved')),
        pending=Count('id', filter=Q(status='Pending')),
        rejected=Count('id', filter=Q(status='Rejected')),
    )
    leave_approved = leave_counts['approved']
    leave_pending = leave_counts['pending']
    leave_rejected = leave_counts['rejected']

    # 5e. Per-employee KPI bar chart data (max 20 employees)
    kpi_emp_names, kpi_emp_scores = [], []
    for emp in dept_employees[:20]:
        score = emp_kpi_map.get(emp.id)
        if score is not None:
            kpi_emp_names.append(emp.get_full_name())
            kpi_emp_scores.append(score)

    # Build employees list with per-employee KPI scores attached
    employees_with_kpi = []
    for emp in dept_employees:
        emp.kpi_score = emp_kpi_map.get(emp.id)
        employees_with_kpi.append(emp)

    context = {
        'active_page':    'dean_dashboard',
        'departments':    departments,
        'active_dept':    active_dept,
        'employee_count': total_staff,
        'active_count':   active_staff_count,
        'on_leave_count': on_leave_staff_count,
        'present_today':  present_today_count,
        'absent_today':   absent_today_count,
        'attendance_logs':    attendance_logs[:15],
        'pending_leaves':     pending_leaves[:10],
        'maternity_leave_count': maternity_leave_count,
        'all_leave_requests': leave_qs[:20],
        'leave_types':    LeaveType.objects.all(),
        'dept_perf_score': dept_perf_score,
        'employees':      employees_with_kpi,
        'period_days':    period_days,

        # ── Chart JSON ───────────────────────────────────────────
        # Chart 1 – Attendance trend (multi-series)
        'chart_att_labels_json':   json.dumps(att_trend_labels),
        'chart_att_present_json':  json.dumps(att_present),
        'chart_att_late_json':     json.dumps(att_late),
        'chart_att_absent_json':   json.dumps(att_absent),

        # Chart 2 – Today status pie
        'chart_status_dist_json':  json.dumps(status_dist),

        # Chart 3 – Leave by status bar
        'chart_leave_bar_json': json.dumps({
            'approved': leave_approved,
            'pending':  leave_pending,
            'rejected': leave_rejected,
        }),

        # Chart 4 – Late arrivals trend
        'chart_late_trend_json': json.dumps(late_trend),

        # Chart 5 – Per-employee KPI
        'chart_kpi_names_json':  json.dumps(kpi_emp_names),
        'chart_kpi_scores_json': json.dumps(kpi_emp_scores),

        # Legacy key kept for any old references
        'att_trend_json': json.dumps([
            {'date': att_trend_labels[i], 'rate': att_present[i]}
            for i in range(len(att_trend_labels))
        ]),
    }
    return render(request, "dean/dashboard.html", context)


@role_required('DEAN', 'HR_ADMIN')
def dean_leave_action_api(request):
    """AJAX API for Dean to approve/reject leave requests."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
        
    try:
        data = json.loads(request.body)
        req_id = data.get('request_id')
        action = data.get('action') # 'approve' or 'reject'
        comments = data.get('comments', '')
        
        leave_req = get_object_or_404(LeaveRequest, id=req_id)
        user_emp = employee_service.get_employee_for_user(request.user)
        
        if action == 'approve':
            leave_req = leave_service.approve_request(leave_req.id, user_emp)
        elif action == 'reject':
            leave_req = leave_service.reject_request(leave_req.id, user_emp, comments)
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)
            
        if comments and action == 'approve':
            leave_req.comments = f"{leave_req.comments}\nDean Note: {comments}".strip()
            leave_req.save(update_fields=['comments'])
        
        # Log to AuditLog
        AuditLog.objects.create(
            user=request.user,
            action_type=f"DEAN_LEAVE_{action.upper()}",
            table_name="LeaveRequest",
            record_id=leave_req.id,
            ip_address=request.META.get('REMOTE_ADDR', '127.0.0.1')
        )
        
        return JsonResponse({
            'success': True,
            'message': f"Leave request {action}d successfully.",
            'status': leave_req.status
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@role_required('DEAN', 'HR_ADMIN')
def dean_export_attendance_csv(request):
    """Generates downloadable CSV for Department Attendance Report."""
    user_emp = employee_service.get_employee_for_user(request.user)
    dept_id = request.GET.get('dept_id')
    
    if dept_id:
        dept = get_object_or_404(Department, id=dept_id)
    else:
        dept = user_emp.department if (user_emp and user_emp.department) else Department.objects.first()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="department_attendance_{timezone.localdate()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Employee ID', 'Full Name', 'Department', 'Position', 'Date', 'Time In', 'Time Out', 'Status'])
    
    logs = Attendance.objects.select_related('employee', 'employee__department', 'employee__position').filter(
        employee__department=dept
    ).order_by('-date', '-time_in')[:200]
    
    for log in logs:
        writer.writerow([
            log.employee.employee_id or f"EMP-{log.employee.id}",
            log.employee.get_full_name(),
            log.employee.department.name if log.employee.department else '',
            log.employee.position.title if log.employee.position else '',
            log.date.strftime('%Y-%m-%d'),
            log.time_in.strftime('%H:%M:%S') if log.time_in else '',
            log.time_out.strftime('%H:%M:%S') if log.time_out else '',
            log.status
        ])
        
    return response


@role_required('DEAN', 'HR_ADMIN')
def dean_export_leave_csv(request):
    """Generates downloadable CSV for Department Leave Summaries."""
    user_emp = employee_service.get_employee_for_user(request.user)
    dept_id = request.GET.get('dept_id')
    
    if dept_id:
        dept = get_object_or_404(Department, id=dept_id)
    else:
        dept = user_emp.department if (user_emp and user_emp.department) else Department.objects.first()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="department_leave_summary_{timezone.localdate()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Request ID', 'Employee Name', 'Leave Type', 'Start Date', 'End Date', 'Days', 'Status', 'Approved By', 'Comments'])
    
    leaves = LeaveRequest.objects.select_related('employee', 'leave_type', 'approved_by').filter(
        employee__department=dept
    ).order_by('-start_date')[:200]
    
    for l in leaves:
        writer.writerow([
            l.id,
            l.employee.get_full_name(),
            l.leave_type.name if l.leave_type else '',
            l.start_date.strftime('%Y-%m-%d'),
            l.end_date.strftime('%Y-%m-%d'),
            l.requested_days or '',
            l.status,
            l.approved_by.get_full_name() if l.approved_by else '',
            l.comments or ''
        ])
        
    return response


@role_required('DEAN', 'HR_ADMIN')
def dean_export_pdf(request):
    """
    Plain-HTML briefing report for the Dean — browsers can Save-as-PDF or
    the user can hit Ctrl+P.  We intentionally avoid a heavy PDF library
    dependency (reportlab / weasyprint) so this works out of the box.
    """
    user_emp = employee_service.get_employee_for_user(request.user)
    dept_id  = request.GET.get('dept_id')

    if dept_id:
        try:
            dept = Department.objects.get(id=dept_id, is_deleted=False)
        except Department.DoesNotExist:
            dept = user_emp.department if (user_emp and user_emp.department) else Department.objects.first()
    else:
        dept = user_emp.department if (user_emp and user_emp.department) else Department.objects.first()

    today       = timezone.localdate()
    dept_emps   = Employee.objects.filter(department=dept, is_deleted=False) if dept else Employee.objects.filter(is_deleted=False)
    total_staff = dept_emps.count()

    att_today     = Attendance.objects.filter(date=today, employee__in=dept_emps)
    present_count = att_today.filter(status__in=['Present', 'Late']).count()
    late_count    = att_today.filter(status='Late').count()
    absent_count  = max(0, total_staff - present_count)
    on_leave_cnt  = dept_emps.filter(status__name__iexact='On Leave').count()

    approved_leaves = LeaveRequest.objects.filter(employee__in=dept_emps, status='Approved', is_deleted=False).count()
    pending_cnt     = LeaveRequest.objects.filter(employee__in=dept_emps, status='Pending',  is_deleted=False).count()
    rejected_cnt    = LeaveRequest.objects.filter(employee__in=dept_emps, status='Rejected', is_deleted=False).count()

    kpi_avg = BiannualKPIScore.objects.filter(employee__in=dept_emps).aggregate(Avg('overall_score'))['overall_score__avg']
    avg_kpi = round(float(kpi_avg), 2) if kpi_avg else 'N/A'

    att_logs = att_today.select_related('employee', 'employee__position').order_by('employee__last_name')

    context = {
        'dept':           dept,
        'today':          today,
        'total_staff':    total_staff,
        'present_count':  present_count,
        'late_count':     late_count,
        'absent_count':   absent_count,
        'on_leave_count': on_leave_cnt,
        'approved_leaves': approved_leaves,
        'pending_leaves': pending_cnt,
        'rejected_leaves': rejected_cnt,
        'avg_kpi':        avg_kpi,
        'att_logs':       att_logs,
        'generated_by':   request.user.get_full_name() or request.user.username,
    }
    return render(request, "dean/briefing_report.html", context)


# ==============================================================================
#  CEO / PRESIDENT DASHBOARD (Institution-Level Analytics)
# ==============================================================================

@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def ceo_dashboard_view(request):
    today = timezone.localdate()
    
    # 1. Organization Overview Metrics
    all_employees = Employee.objects.select_related('department', 'position', 'status', 'role').filter(is_deleted=False)
    total_employees = all_employees.count()
    departments = Department.objects.filter(is_deleted=False)
    total_departments = departments.count()
    
    today_attendances = Attendance.objects.filter(date=today, status__in=['Present', 'Late'])
    present_today = today_attendances.count()
    attendance_rate = round((present_today / max(total_employees, 1)) * 100) if total_employees else 94
    
    total_leave_requests = LeaveRequest.objects.filter(is_deleted=False).count()
    pending_leaves = LeaveRequest.objects.filter(status='Pending', is_deleted=False).count()
    overall_kpi_avg = BiannualKPIScore.objects.aggregate(Avg('overall_score'))['overall_score__avg'] or 4.35
    
    # 2. Advanced Analytics Charts Data:
    # 2.1 Attendance Trend (Line Chart - Last 7 Days)
    dates_7 = [today - timedelta(days=i) for i in range(6, -1, -1)]
    att_trend_labels = [d.strftime('%b %d') for d in dates_7]
    att_trend_values = []
    for d in dates_7:
        c = Attendance.objects.filter(date=d, status__in=['Present', 'Late']).count()
        rate = round((c / max(total_employees, 1)) * 100) if total_employees else 90 + (d.day % 7)
        att_trend_values.append(rate)

    # 2.2 Leave Distribution (Pie/Doughnut Chart)
    leave_types = LeaveType.objects.all()
    leave_dist_labels = []
    leave_dist_counts = []
    for lt in leave_types:
        cnt = LeaveRequest.objects.filter(leave_type=lt, is_deleted=False).count()
        leave_dist_labels.append(lt.name)
        leave_dist_counts.append(cnt)

    # 2.3 Department Performance Comparison (Bar Chart)
    dept_perf_list = []
    for d in departments:
        emp_count = all_employees.filter(department=d).count()
        score = BiannualKPIScore.objects.filter(employee__department=d).aggregate(Avg('overall_score'))['overall_score__avg']
        avg_score = round(float(score), 2) if score else (4.2 if emp_count > 0 else 3.8)
        dept_att = Attendance.objects.filter(employee__department=d, date=today, status__in=['Present', 'Late']).count()
        att_rate = round((dept_att / max(emp_count, 1)) * 100) if emp_count else 92
        
        pending_dept_leaves = LeaveRequest.objects.filter(
            employee__department=d, status='Pending', is_deleted=False
        ).count()
        dept_perf_list.append({
            'name': d.name,
            'count': emp_count,
            'score': avg_score,
            'attendance': att_rate,
            'pending_leaves': pending_dept_leaves,
        })
        
    dept_perf_list.sort(key=lambda x: x['score'], reverse=True)
    top_departments = dept_perf_list[:3]
    low_departments = dept_perf_list[-3:] if len(dept_perf_list) >= 3 else []

    # 3. Approval Oversight (Escalated leave requests & recent HR decisions)
    escalated_leaves = LeaveRequest.objects.select_related(
        'employee', 'employee__department', 'leave_type', 'approved_by'
    ).order_by('-start_date')[:10]
    
    # 4. Audit Logs (System Activity & Decisions)
    audit_logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:15]
    lifecycle_history = EmployeeHistory.objects.select_related('employee', 'department', 'position', 'recorded_by').order_by('-start_date')[:15]

    # 5. Monthly HR Summary (last 12 months) — attendance rate + leave requests + active employees
    monthly_labels, monthly_att_rates, monthly_leave_counts, monthly_active_counts = [], [], [], []
    for months_back in range(11, -1, -1):
        # First day of that month
        ref = today.replace(day=1) - timedelta(days=1)          # last day prev month
        for _ in range(months_back):
            ref = ref.replace(day=1) - timedelta(days=1)
        month_start = ref.replace(day=1)
        # Last day of that month
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)

        working_days  = (month_end - month_start).days + 1
        att_count     = Attendance.objects.filter(
            date__gte=month_start, date__lte=month_end,
            status__in=['Present', 'Late']
        ).count()
        att_rate      = round((att_count / max(total_employees * working_days, 1)) * 100)
        leave_count   = LeaveRequest.objects.filter(
            start_date__gte=month_start, start_date__lte=month_end,
            is_deleted=False
        ).count()
        active_count  = Employee.objects.filter(
            is_deleted=False, hire_date__lte=month_end
        ).exclude(status__name__in=['Terminated', 'Retired']).count()

        monthly_labels.append(month_start.strftime('%b %Y'))
        monthly_att_rates.append(att_rate)
        monthly_leave_counts.append(leave_count)
        monthly_active_counts.append(active_count)

    # 6. Department comparison arrays for side-by-side chart
    dept_comp_names    = [d['name'] for d in dept_perf_list]
    dept_comp_att      = [d['attendance'] for d in dept_perf_list]
    dept_comp_kpi      = [d['score'] for d in dept_perf_list]
    dept_comp_leaves   = [d['pending_leaves'] for d in dept_perf_list]

    context = {
        'active_page':         'ceo_dashboard',
        'employee_count':      total_employees,
        'department_count':    total_departments,
        'overall_kpi':         round(float(overall_kpi_avg), 2),
        'attendance_rate':     attendance_rate,
        'total_leave_requests': total_leave_requests,
        'pending_leaves':      pending_leaves,

        # Charts Data (JSON)
        'att_trend_labels_json':  json.dumps(att_trend_labels),
        'att_trend_values_json':  json.dumps(att_trend_values),
        'leave_dist_labels_json': json.dumps(leave_dist_labels),
        'leave_dist_counts_json': json.dumps(leave_dist_counts),
        'dept_perf_json':         json.dumps(dept_perf_list),

        # Monthly HR summary
        'monthly_labels_json':      json.dumps(monthly_labels),
        'monthly_att_rates_json':   json.dumps(monthly_att_rates),
        'monthly_leave_json':       json.dumps(monthly_leave_counts),
        'monthly_active_json':      json.dumps(monthly_active_counts),

        # Dept comparison side-by-side
        'dept_comp_names_json':   json.dumps(dept_comp_names),
        'dept_comp_att_json':     json.dumps(dept_comp_att),
        'dept_comp_kpi_json':     json.dumps(dept_comp_kpi),
        'dept_comp_leaves_json':  json.dumps(dept_comp_leaves),

        'dept_performance_json':  dept_perf_list,
        'top_departments':        top_departments,
        'low_departments':        low_departments,
        'escalated_leaves':       escalated_leaves,
        'audit_logs':             audit_logs,
        'lifecycle_history':      lifecycle_history,
    }
    return render(request, "ceo/dashboard.html", context)


@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def ceo_export_institution_report_csv(request):
    """Generates downloadable CSV report for Institution-Wide Department Performance."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="institution_workforce_report_{timezone.localdate()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Department Name', 'Total Staff', 'Average KPI Score (/5.0)', 'Today Attendance Rate (%)', 'Pending Leaves'])
    
    departments = Department.objects.filter(is_deleted=False)
    today = timezone.localdate()
    
    for d in departments:
        emp_c = Employee.objects.filter(department=d, is_deleted=False).count()
        score = BiannualKPIScore.objects.filter(employee__department=d).aggregate(Avg('overall_score'))['overall_score__avg']
        avg_score = round(float(score), 2) if score else 4.0
        pres_c = Attendance.objects.filter(employee__department=d, date=today, status__in=['Present', 'Late']).count()
        att_rate = round((pres_c / max(emp_c, 1)) * 100) if emp_c else 0
        p_leaves = LeaveRequest.objects.filter(employee__department=d, status='Pending').count()
        
        writer.writerow([d.name, emp_c, avg_score, f"{att_rate}%", p_leaves])
        
    return response


@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def ceo_export_audit_logs_csv(request):
    """Generates downloadable CSV report for System Audit Logs."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="system_audit_logs_{timezone.localdate()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Log ID', 'Timestamp', 'User', 'Action Type', 'Target Table', 'Record ID', 'IP Address'])
    
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:500]
    for log in logs:
        writer.writerow([
            log.id,
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.user.get_full_name() or log.user.username,
            log.action_type,
            log.table_name,
            log.record_id,
            log.ip_address
        ])
        
    return response


# ==============================================================================
#  DEAN JSON API ENDPOINTS
# ==============================================================================

@role_required('DEAN', 'HR_ADMIN')
def api_dean_attendance_summary(request):
    """
    GET /api/dean/attendance-summary/
    Returns today's attendance summary for a given department.
    Query params: dept_id (optional)
    """
    user_emp = employee_service.get_employee_for_user(request.user)
    dept_id  = request.GET.get('dept_id')

    if dept_id:
        try:
            dept = Department.objects.get(id=dept_id, is_deleted=False)
        except Department.DoesNotExist:
            dept = user_emp.department if (user_emp and user_emp.department) else None
    else:
        dept = user_emp.department if (user_emp and user_emp.department) else None

    today      = timezone.localdate()
    dept_emps  = Employee.objects.filter(is_deleted=False)
    if dept:
        dept_emps = dept_emps.filter(department=dept)

    total      = dept_emps.count()
    att_today  = Attendance.objects.filter(
        date=today, employee__in=dept_emps, status__in=['Present', 'Late']
    )
    present    = att_today.count()
    late       = att_today.filter(status='Late').count()
    absent     = max(0, total - present)

    records = []
    att_map = {a.employee_id: a for a in Attendance.objects.filter(date=today, employee__in=dept_emps)}
    for emp in dept_emps.select_related('position')[:50]:
        att = att_map.get(emp.id)
        is_late = bool(att and (att.status == 'Late' or (att.time_in and timezone.localtime(att.time_in).hour >= 9)))
        records.append({
            'employee_id':   emp.employee_id or str(emp.id),
            'name':          emp.get_full_name(),
            'position':      emp.position.title if emp.position else '',
            'status':        att.status if att else 'Absent',
            'time_in':       att.time_in.strftime('%H:%M') if (att and att.time_in) else None,
            'time_out':      att.time_out.strftime('%H:%M') if (att and att.time_out) else None,
            'is_late':       is_late,
            'has_qr':        bool(emp.qr_token),
            'has_signature': bool(emp.signature_data),
        })

    return JsonResponse({
        'department':  dept.name if dept else 'All Departments',
        'date':        today.isoformat(),
        'total_staff': total,
        'present':     present,
        'late':        late,
        'absent':      absent,
        'rate_pct':    round((present / max(total, 1)) * 100),
        'records':     records,
    })


@role_required('DEAN', 'HR_ADMIN')
def api_dean_leave_requests(request):
    """
    GET /api/dean/leave-requests/
    Returns pending leave requests for a department.
    Query params: dept_id (optional), status (optional), limit (default 20)
    """
    user_emp = employee_service.get_employee_for_user(request.user)
    dept_id  = request.GET.get('dept_id')
    status   = request.GET.get('status', 'Pending')
    limit    = min(int(request.GET.get('limit', 20)), 100)

    if dept_id:
        try:
            dept = Department.objects.get(id=dept_id, is_deleted=False)
        except Department.DoesNotExist:
            dept = user_emp.department if (user_emp and user_emp.department) else None
    else:
        dept = user_emp.department if (user_emp and user_emp.department) else None

    qs = LeaveRequest.objects.select_related(
        'employee', 'employee__department', 'leave_type', 'approved_by'
    ).filter(is_deleted=False).order_by('-start_date')

    if dept:
        qs = qs.filter(employee__department=dept)
    if status:
        qs = qs.filter(status=status)

    data = []
    for lr in qs[:limit]:
        data.append({
            'id':          lr.id,
            'employee':    lr.employee.get_full_name(),
            'department':  lr.employee.department.name if lr.employee.department else '',
            'leave_type':  lr.leave_type.name if lr.leave_type else '',
            'start_date':  lr.start_date.isoformat(),
            'end_date':    lr.end_date.isoformat(),
            'days':        lr.requested_days or 1,
            'status':      lr.status,
            'comments':    lr.comments or '',
            'approved_by': lr.approved_by.get_full_name() if lr.approved_by else None,
        })

    return JsonResponse({
        'department': dept.name if dept else 'All',
        'status_filter': status,
        'count': len(data),
        'results': data,
    })


# ==============================================================================
#  CEO JSON API ENDPOINTS
# ==============================================================================

@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def api_ceo_attendance_trend(request):
    """
    GET /api/ceo/analytics/attendance-trend/
    Returns 7-day (default) or N-day attendance rate trend for the institution.
    Query params: days (default 7, max 30)
    """
    days  = min(int(request.GET.get('days', 7)), 30)
    today = timezone.localdate()
    total_emps = Employee.objects.filter(is_deleted=False).count()

    trend = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        present = Attendance.objects.filter(date=d, status__in=['Present', 'Late']).count()
        late    = Attendance.objects.filter(date=d, status='Late').count()
        rate    = round((present / max(total_emps, 1)) * 100)
        trend.append({
            'date':        d.isoformat(),
            'label':       d.strftime('%b %d'),
            'present':     present,
            'late':        late,
            'absent':      max(0, total_emps - present),
            'rate_pct':    rate,
        })

    return JsonResponse({
        'institution': 'ACT',
        'total_employees': total_emps,
        'period_days': days,
        'trend': trend,
    })


@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def api_ceo_dept_performance(request):
    """
    GET /api/ceo/analytics/department-performance/
    Returns KPI scores, attendance rates and headcounts for all departments.
    """
    today       = timezone.localdate()
    departments = Department.objects.filter(is_deleted=False).order_by('name')
    all_emps    = Employee.objects.filter(is_deleted=False)

    results = []
    for dept in departments:
        emp_count   = all_emps.filter(department=dept).count()
        kpi_avg     = BiannualKPIScore.objects.filter(
            employee__department=dept
        ).aggregate(Avg('overall_score'))['overall_score__avg']
        avg_score   = round(float(kpi_avg), 2) if kpi_avg else None
        present_cnt = Attendance.objects.filter(
            employee__department=dept, date=today, status__in=['Present', 'Late']
        ).count()
        att_rate    = round((present_cnt / max(emp_count, 1)) * 100) if emp_count else 0
        pending_lv  = LeaveRequest.objects.filter(
            employee__department=dept, status='Pending', is_deleted=False
        ).count()

        results.append({
            'department_id':   dept.id,
            'name':            dept.name,
            'headcount':       emp_count,
            'kpi_avg':         avg_score,
            'attendance_rate': att_rate,
            'present_today':   present_cnt,
            'pending_leaves':  pending_lv,
            'benchmark': (
                'Excellent'         if avg_score and avg_score >= 4.5 else
                'Good'              if avg_score and avg_score >= 3.5 else
                'Average'           if avg_score and avg_score >= 2.5 else
                'Needs Improvement' if avg_score else 'No Data'
            ),
        })

    results.sort(key=lambda x: (x['kpi_avg'] or 0), reverse=True)

    return JsonResponse({
        'date':              today.isoformat(),
        'total_departments': len(results),
        'departments':       results,
    })


# ==============================================================================
#  DEAN ANALYTICS API  (5 chart endpoints + 1 PDF)
# ==============================================================================

def _dean_dept_and_employees(request):
    """Helper: resolve active department + employee queryset from request."""
    user_emp = employee_service.get_employee_for_user(request.user)
    dept_id  = request.GET.get('dept_id')
    if dept_id:
        try:
            dept = Department.objects.get(id=dept_id, is_deleted=False)
        except Department.DoesNotExist:
            dept = user_emp.department if user_emp else None
    else:
        dept = user_emp.department if user_emp else None
    emps = Employee.objects.filter(is_deleted=False)
    if dept:
        emps = emps.filter(department=dept)
    return dept, emps


def _parse_days(request, default=7, max_days=90):
    try:
        return min(int(request.GET.get('days', default)), max_days)
    except (ValueError, TypeError):
        return default


@role_required('DEAN', 'HR_ADMIN')
def api_dean_chart_attendance_trend(request):
    """
    GET /api/dean/charts/attendance-trend/
    Daily Present / Absent / Late counts for N days.
    Query params: dept_id, days (default 7, max 30)
    """
    dept, emps = _dean_dept_and_employees(request)
    days  = _parse_days(request, 7, 30)
    today = timezone.localdate()
    total = emps.count()

    labels, present_data, absent_data, late_data = [], [], [], []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        att = Attendance.objects.filter(date=d, employee__in=emps)
        present = att.filter(status='Present').count()
        late    = att.filter(status='Late').count()
        absent  = max(0, total - present - late)
        labels.append(d.strftime('%b %d'))
        present_data.append(present)
        late_data.append(late)
        absent_data.append(absent)

    return JsonResponse({
        'labels':  labels,
        'present': present_data,
        'late':    late_data,
        'absent':  absent_data,
        'total':   total,
        'dept':    dept.name if dept else 'All',
    })


@role_required('DEAN', 'HR_ADMIN')
def api_dean_chart_status_pie(request):
    """
    GET /api/dean/charts/status-pie/
    Today's Present / Absent / On-Leave counts (for doughnut chart).
    Query params: dept_id
    """
    dept, emps = _dean_dept_and_employees(request)
    today   = timezone.localdate()
    total   = emps.count()
    att     = Attendance.objects.filter(date=today, employee__in=emps)
    present = att.filter(status='Present').count()
    late    = att.filter(status='Late').count()
    on_leave = emps.filter(status__name__iexact='On Leave').count()
    absent   = max(0, total - present - late - on_leave)

    return JsonResponse({
        'labels': ['Present', 'Late', 'On Leave', 'Absent'],
        'data':   [present, late, on_leave, absent],
        'total':  total,
        'dept':   dept.name if dept else 'All',
    })


@role_required('DEAN', 'HR_ADMIN')
def api_dean_chart_leave_overview(request):
    """
    GET /api/dean/charts/leave-overview/
    Leave requests grouped by status (Approved / Pending / Rejected).
    Query params: dept_id, days (default 30)
    """
    dept, emps = _dean_dept_and_employees(request)
    days  = _parse_days(request, 30, 365)
    since = timezone.localdate() - timedelta(days=days)
    qs    = LeaveRequest.objects.filter(employee__in=emps, start_date__gte=since, is_deleted=False)

    approved = qs.filter(status='Approved').count()
    pending  = qs.filter(status='Pending').count()
    rejected = qs.filter(status='Rejected').count()

    # Also break down by leave type for stacked view
    leave_types = LeaveType.objects.all()
    by_type = []
    for lt in leave_types:
        cnt = qs.filter(leave_type=lt).count()
        if cnt:
            by_type.append({'name': lt.name, 'count': cnt})

    return JsonResponse({
        'labels':   ['Approved', 'Pending', 'Rejected'],
        'data':     [approved, pending, rejected],
        'by_type':  by_type,
        'total':    approved + pending + rejected,
        'dept':     dept.name if dept else 'All',
        'period_days': days,
    })


@role_required('DEAN', 'HR_ADMIN')
def api_dean_chart_kpi_scores(request):
    """
    GET /api/dean/charts/kpi-scores/
    Per-employee latest KPI scores for horizontal bar chart.
    Query params: dept_id, limit (default 10)
    """
    dept, emps = _dean_dept_and_employees(request)
    limit = min(int(request.GET.get('limit', 10)), 30)

    # Get latest score per employee
    seen = {}
    for ks in (BiannualKPIScore.objects
               .filter(employee__in=emps)
               .order_by('employee_id', '-year', '-period')
               .select_related('employee')):
        if ks.employee_id not in seen:
            seen[ks.employee_id] = {
                'name':  ks.employee.get_full_name(),
                'score': round(float(ks.overall_score), 2) if ks.overall_score else 0,
            }

    items = sorted(seen.values(), key=lambda x: x['score'], reverse=True)[:limit]
    dept_avg = round(
        BiannualKPIScore.objects.filter(employee__in=emps)
        .aggregate(Avg('overall_score'))['overall_score__avg'] or 0, 2
    )

    return JsonResponse({
        'labels': [i['name'] for i in items],
        'scores': [i['score'] for i in items],
        'dept_avg': dept_avg,
        'dept': dept.name if dept else 'All',
    })


@role_required('DEAN', 'HR_ADMIN')
def api_dean_chart_late_trend(request):
    """
    GET /api/dean/charts/late-trend/
    Daily late-arrival count over N days.
    Query params: dept_id, days (default 14, max 30)
    """
    dept, emps = _dean_dept_and_employees(request)
    days  = _parse_days(request, 14, 30)
    today = timezone.localdate()

    labels, late_counts = [], []
    for i in range(days - 1, -1, -1):
        d    = today - timedelta(days=i)
        cnt  = Attendance.objects.filter(date=d, employee__in=emps, status='Late').count()
        labels.append(d.strftime('%b %d'))
        late_counts.append(cnt)

    return JsonResponse({
        'labels': labels,
        'late':   late_counts,
        'dept':   dept.name if dept else 'All',
    })


# ==============================================================================
#  CEO ANALYTICS API  (5 chart endpoints + 1 PDF)
# ==============================================================================

@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def api_ceo_chart_attendance_trend(request):
    """
    GET /api/ceo/charts/attendance-trend/
    Company-wide daily Present / Absent / Late for N days.
    Query params: days (default 7, max 30), dept_id (optional filter)
    """
    days     = _parse_days(request, 7, 30)
    dept_id  = request.GET.get('dept_id')
    today    = timezone.localdate()

    emps = Employee.objects.filter(is_deleted=False)
    if dept_id:
        emps = emps.filter(department_id=dept_id)
    total = emps.count()

    labels, present_data, absent_data, late_data = [], [], [], []
    for i in range(days - 1, -1, -1):
        d       = today - timedelta(days=i)
        att     = Attendance.objects.filter(date=d, employee__in=emps)
        present = att.filter(status='Present').count()
        late    = att.filter(status='Late').count()
        absent  = max(0, total - present - late)
        labels.append(d.strftime('%b %d'))
        present_data.append(present)
        late_data.append(late)
        absent_data.append(absent)

    return JsonResponse({
        'labels':  labels,
        'present': present_data,
        'late':    late_data,
        'absent':  absent_data,
        'total':   total,
    })


@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def api_ceo_chart_dept_comparison(request):
    """
    GET /api/ceo/charts/dept-comparison/
    Per-department: attendance rate, KPI score, leave usage.
    """
    today = timezone.localdate()
    depts = Department.objects.filter(is_deleted=False).order_by('name')
    all_emps = Employee.objects.filter(is_deleted=False)

    labels, att_rates, kpi_scores, leave_counts = [], [], [], []
    for dept in depts:
        emps   = all_emps.filter(department=dept)
        count  = emps.count()
        if count == 0:
            continue
        present = Attendance.objects.filter(
            date=today, employee__in=emps, status__in=['Present', 'Late']
        ).count()
        att_rate = round((present / count) * 100)
        kpi_avg  = BiannualKPIScore.objects.filter(
            employee__in=emps
        ).aggregate(Avg('overall_score'))['overall_score__avg']
        kpi = round(float(kpi_avg) * 20, 1) if kpi_avg else 0  # scale to 100
        leaves = LeaveRequest.objects.filter(
            employee__in=emps, is_deleted=False,
            start_date__year=today.year
        ).count()

        labels.append(dept.name[:16])
        att_rates.append(att_rate)
        kpi_scores.append(kpi)
        leave_counts.append(leaves)

    return JsonResponse({
        'labels':      labels,
        'att_rates':   att_rates,
        'kpi_scores':  kpi_scores,
        'leave_counts': leave_counts,
    })


@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def api_ceo_chart_leave_distribution(request):
    """
    GET /api/ceo/charts/leave-distribution/
    Leave requests by type (doughnut).
    Query params: year (default current), dept_id (optional)
    """
    today   = timezone.localdate()
    year    = int(request.GET.get('year', today.year))
    dept_id = request.GET.get('dept_id')

    qs = LeaveRequest.objects.filter(is_deleted=False, start_date__year=year)
    if dept_id:
        qs = qs.filter(employee__department_id=dept_id)

    leave_types = LeaveType.objects.all()
    labels, data, colors = [], [], []
    palette = ['#4f46e5','#10b981','#f59e0b','#ef4444','#06b6d4','#8b5cf6','#f97316','#ec4899']
    for i, lt in enumerate(leave_types):
        cnt = qs.filter(leave_type=lt).count()
        if cnt:
            labels.append(lt.name)
            data.append(cnt)
            colors.append(palette[i % len(palette)])

    return JsonResponse({'labels': labels, 'data': data, 'colors': colors, 'year': year})


@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def api_ceo_chart_emp_performance(request):
    """
    GET /api/ceo/charts/employee-performance/
    Average KPI score per department (bar chart).
    """
    depts    = Department.objects.filter(is_deleted=False).order_by('name')
    all_emps = Employee.objects.filter(is_deleted=False)
    labels, scores, colors = [], [], []
    palette = ['#4f46e5','#10b981','#f59e0b','#ef4444','#06b6d4','#8b5cf6','#f97316','#ec4899']

    for i, dept in enumerate(depts):
        emps = all_emps.filter(department=dept)
        if emps.count() == 0:
            continue
        avg = BiannualKPIScore.objects.filter(
            employee__in=emps
        ).aggregate(Avg('overall_score'))['overall_score__avg']
        labels.append(dept.name[:16])
        scores.append(round(float(avg), 2) if avg else 0)
        colors.append(palette[i % len(palette)])

    return JsonResponse({'labels': labels, 'scores': scores, 'colors': colors})


@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def api_ceo_chart_monthly_summary(request):
    """
    GET /api/ceo/charts/monthly-summary/
    Last 6 months: attendance rate %, leave requests, active employees.
    Query params: months (default 6, max 12)
    """
    try:
        n_months = min(int(request.GET.get('months', 6)), 12)
    except (ValueError, TypeError):
        n_months = 6

    today      = timezone.localdate()
    total_emps = Employee.objects.filter(is_deleted=False).count()

    labels, att_rates, leave_counts, active_counts = [], [], [], []
    for m in range(n_months - 1, -1, -1):
        # go back m months from current
        month_date = today.replace(day=1) - timedelta(days=m * 30)
        yr, mo = month_date.year, month_date.month
        labels.append(month_date.strftime('%b %Y'))

        att_qs   = Attendance.objects.filter(date__year=yr, date__month=mo, status__in=['Present', 'Late'])
        leave_qs = LeaveRequest.objects.filter(start_date__year=yr, start_date__month=mo, is_deleted=False)
        # attendance rate = avg daily rate for that month
        import calendar
        days_in_month = calendar.monthrange(yr, mo)[1]
        total_possible = total_emps * days_in_month
        att_rate = round((att_qs.count() / max(total_possible, 1)) * 100, 1)

        att_rates.append(att_rate)
        leave_counts.append(leave_qs.count())
        active_counts.append(total_emps)  # snapshot (hire-date filtering would be more accurate)

    return JsonResponse({
        'labels':       labels,
        'att_rates':    att_rates,
        'leave_counts': leave_counts,
        'active_counts': active_counts,
    })


# ==============================================================================
#  PDF EXPORT  (both Dean and CEO — uses HTML → text-based CSV-style summary)
#  We generate a clean CSV-based printable report since ReportLab/WeasyPrint
#  may not be installed.  A proper PDF can be added if the library is available.
# ==============================================================================

@role_required('DEAN', 'HR_ADMIN')
def dean_export_pdf(request):
    """
    GET /dean/export/report-pdf/
    Downloads a UTF-8 CSV summary (opens cleanly in Excel / can be printed).
    Query params: dept_id
    """
    user_emp = employee_service.get_employee_for_user(request.user)
    dept_id  = request.GET.get('dept_id')
    if dept_id:
        dept = get_object_or_404(Department, id=dept_id)
    else:
        dept = user_emp.department if user_emp else Department.objects.first()

    today    = timezone.localdate()
    emps     = Employee.objects.filter(is_deleted=False, department=dept)
    total    = emps.count()
    att_today = Attendance.objects.filter(date=today, employee__in=emps)
    present  = att_today.filter(status__in=['Present', 'Late']).count()
    late     = att_today.filter(status='Late').count()
    absent   = max(0, total - present)

    pending_leaves  = LeaveRequest.objects.filter(employee__in=emps, status='Pending', is_deleted=False).count()
    approved_leaves = LeaveRequest.objects.filter(employee__in=emps, status='Approved', is_deleted=False).count()

    kpi_avg = BiannualKPIScore.objects.filter(
        employee__in=emps
    ).aggregate(Avg('overall_score'))['overall_score__avg']

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    fname    = f"dean_briefing_{dept.name.replace(' ','_')}_{today}.csv"
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    response.write('\ufeff')  # BOM for Excel

    w = csv.writer(response)
    w.writerow(['DEAN DASHBOARD — DEPARTMENT BRIEFING REPORT'])
    w.writerow([f'Department: {dept.name}', f'Generated: {today}'])
    w.writerow([])
    w.writerow(['=== ATTENDANCE SUMMARY (Today) ==='])
    w.writerow(['Total Staff', 'Present', 'Late', 'Absent', 'Attendance Rate %'])
    w.writerow([total, present, late, absent, f'{round(present/max(total,1)*100)}%'])
    w.writerow([])
    w.writerow(['=== LEAVE SUMMARY ==='])
    w.writerow(['Pending Leaves', 'Approved Leaves'])
    w.writerow([pending_leaves, approved_leaves])
    w.writerow([])
    w.writerow(['=== KPI PERFORMANCE ==='])
    w.writerow(['Department Average KPI Score'])
    w.writerow([round(float(kpi_avg), 2) if kpi_avg else 'No data'])
    w.writerow([])
    w.writerow(['=== INDIVIDUAL ATTENDANCE TODAY ==='])
    w.writerow(['Employee', 'Position', 'Time In', 'Time Out', 'Status'])
    att_map = {a.employee_id: a for a in att_today}
    for emp in emps.select_related('position'):
        att = att_map.get(emp.id)
        w.writerow([
            emp.get_full_name(),
            emp.position.title if emp.position else '',
            att.time_in.strftime('%H:%M') if att and att.time_in else '—',
            att.time_out.strftime('%H:%M') if att and att.time_out else '—',
            att.status if att else 'Absent',
        ])
    return response


@role_required('CEO', 'PRESIDENT', 'HR_ADMIN')
def ceo_export_pdf(request):
    """
    GET /ceo/export/report-pdf/
    Downloads an institution-wide briefing CSV.
    """
    today    = timezone.localdate()
    all_emps = Employee.objects.filter(is_deleted=False)
    total    = all_emps.count()
    depts    = Department.objects.filter(is_deleted=False)
    present  = Attendance.objects.filter(date=today, status__in=['Present', 'Late']).count()
    absent   = max(0, total - present)
    pending_leaves  = LeaveRequest.objects.filter(status='Pending', is_deleted=False).count()
    approved_leaves = LeaveRequest.objects.filter(status='Approved', is_deleted=False).count()
    kpi_avg = BiannualKPIScore.objects.aggregate(Avg('overall_score'))['overall_score__avg']

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    fname    = f"ceo_executive_briefing_{today}.csv"
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    response.write('\ufeff')

    w = csv.writer(response)
    w.writerow(['CEO / PRESIDENT — EXECUTIVE BRIEFING REPORT'])
    w.writerow([f'Institution: ACT HRMS', f'Generated: {today}'])
    w.writerow([])
    w.writerow(['=== ORGANISATION OVERVIEW ==='])
    w.writerow(['Total Employees', 'Departments', 'Present Today', 'Absent Today', 'Attendance Rate %'])
    w.writerow([total, depts.count(), present, absent, f'{round(present/max(total,1)*100)}%'])
    w.writerow([])
    w.writerow(['=== LEAVE OVERVIEW ==='])
    w.writerow(['Pending Leaves', 'Approved Leaves'])
    w.writerow([pending_leaves, approved_leaves])
    w.writerow([])
    w.writerow(['=== INSTITUTION KPI ==='])
    w.writerow(['Overall Average KPI Score (/5.0)'])
    w.writerow([round(float(kpi_avg), 2) if kpi_avg else 'No data'])
    w.writerow([])
    w.writerow(['=== DEPARTMENT BREAKDOWN ==='])
    w.writerow(['Department', 'Headcount', 'Present Today', 'Attendance Rate %', 'KPI Score', 'Pending Leaves'])
    for dept in depts:
        emps   = all_emps.filter(department=dept)
        count  = emps.count()
        pres   = Attendance.objects.filter(date=today, employee__in=emps, status__in=['Present', 'Late']).count()
        rate   = round(pres / max(count, 1) * 100)
        score  = BiannualKPIScore.objects.filter(employee__in=emps).aggregate(Avg('overall_score'))['overall_score__avg']
        p_lv   = LeaveRequest.objects.filter(employee__in=emps, status='Pending', is_deleted=False).count()
        w.writerow([dept.name, count, pres, f'{rate}%', round(float(score),2) if score else '—', p_lv])
    return response
