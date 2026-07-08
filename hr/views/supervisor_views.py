# hr/views/supervisor_views.py
#
# Supervisor dashboard — fully separate role-based portal.
# Supervisors see ONLY employees in their assigned department(s).

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone

from hr.services.employee_service import (
    can_supervise, get_supervised_departments, get_department_employees,
    get_employee_for_user, get_role_key, ROLE_SUPERVISOR,
)
from hr.services import leave_service


def _require_supervisor(user):
    """Return True only for pure supervisor role (not HR/Dean)."""
    return can_supervise(user)


def _supervisor_context(user, extra: dict = None) -> dict:
    """
    Build the base context every supervisor template needs so the
    sidebar can show the user name, role and department(s).
    """
    emp   = get_employee_for_user(user)
    depts = get_supervised_departments(user)
    base  = {
        'supervisor_employee':    emp,
        'supervisor_departments': depts,
    }
    if extra:
        base.update(extra)
    return base


# ── Main dashboard ─────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def supervisor_dashboard(request):
    if not _require_supervisor(request.user):
        return redirect('/dashboard/employee/')

    employees = get_department_employees(request.user)
    today     = timezone.localdate()

    from hr.models import Attendance, LeaveRequest
    present_today  = Attendance.objects.filter(
        employee__in=employees, date=today, status__in=['Present', 'Late']
    ).count()
    pending_leaves = LeaveRequest.objects.filter(
        employee__in=employees, status='Pending'
    ).count()

    ctx = _supervisor_context(request.user, {
        'employees':      employees,
        'present_today':  present_today,
        'pending_leaves': pending_leaves,
        'employee_count': employees.count(),
        'active_page':    'supervisor_dashboard',
    })
    return render(request, 'hr/dashboard_supervisor.html', ctx)


# ── Employees list ─────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def supervisor_employees(request):
    if not _require_supervisor(request.user):
        return redirect('/dashboard/employee/')

    from django.db.models import Q
    query    = request.GET.get('q', '').strip()
    status   = request.GET.get('status', '')
    employees = get_department_employees(request.user)

    if query:
        employees = employees.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query)
        )
    if status:
        employees = employees.filter(status__name__iexact=status)

    ctx = _supervisor_context(request.user, {
        'employees':    employees,
        'search_query': query,
        'status_f':     status,
        'statuses':     ['Active', 'On Leave', 'Terminated'],
        'active_page':  'supervisor_employees',
    })
    return render(request, 'hr/supervisor_employees.html', ctx)


# ── Leave approvals ────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def supervisor_leave_approvals(request):
    if not _require_supervisor(request.user):
        return redirect('/dashboard/employee/')

    supervisor_emp = get_employee_for_user(request.user)
    dept_ids = list(get_supervised_departments(request.user).values_list('id', flat=True))

    if request.method == 'POST':
        action     = request.POST.get('action')
        request_id = request.POST.get('request_id')
        note       = request.POST.get('note', '')
        if supervisor_emp and request_id:
            try:
                if action == 'recommend':
                    leave_service.supervisor_recommend(int(request_id), supervisor_emp, note)
                    messages.success(request, "Leave request marked as Recommended. HR will make the final decision.")
                elif action == 'not_recommend':
                    leave_service.supervisor_not_recommend(int(request_id), supervisor_emp, note)
                    messages.warning(request, "Leave request marked as Not Recommended. HR will make the final decision.")
            except Exception as exc:
                messages.error(request, str(exc))
        return redirect('supervisor_leave_approvals')

    pending      = leave_service.get_pending_requests_for_departments(dept_ids)
    all_requests = leave_service.get_requests_for_departments(dept_ids)

    status_f = request.GET.get('status', '')
    lt_f     = request.GET.get('leave_type_id', '')
    if status_f:
        all_requests = all_requests.filter(status=status_f)
    if lt_f:
        all_requests = all_requests.filter(leave_type_id=lt_f)

    ctx = _supervisor_context(request.user, {
        'pending_requests': pending,
        'all_requests':     all_requests,
        'leave_types':      leave_service.get_all_leave_types(),
        'status_f':         status_f,
        'lt_f':             lt_f,
        'supervisor_emp':   supervisor_emp,
        'active_page':      'supervisor_leave_approvals',
        'recommendation_labels': {
            '':                'Pending Review',
            'recommended':     'Recommended',
            'not_recommended': 'Not Recommended',
        },
    })
    return render(request, 'hr/supervisor_leave_approvals.html', ctx)


# ── Attendance ─────────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def supervisor_attendance(request):
    if not _require_supervisor(request.user):
        return redirect('/dashboard/employee/')

    from hr.models import Attendance
    employees = get_department_employees(request.user)

    month = int(request.GET.get('month', timezone.localdate().month))
    year  = int(request.GET.get('year',  timezone.localdate().year))
    query = request.GET.get('q', '').strip()

    records = Attendance.objects.filter(
        employee__in=employees,
        date__month=month,
        date__year=year,
    ).select_related('employee', 'employee__department').order_by('-date')

    if query:
        from django.db.models import Q
        records = records.filter(
            Q(employee__first_name__icontains=query) |
            Q(employee__last_name__icontains=query)
        )

    ctx = _supervisor_context(request.user, {
        'records':      records,
        'month':        month,
        'year':         year,
        'search_query': query,
        'months': [
            (1,'January'),(2,'February'),(3,'March'),(4,'April'),
            (5,'May'),(6,'June'),(7,'July'),(8,'August'),
            (9,'September'),(10,'October'),(11,'November'),(12,'December'),
        ],
        'years':       [2024, 2025, 2026],
        'active_page': 'supervisor_attendance',
    })
    return render(request, 'hr/supervisor_attendance.html', ctx)


# ── KPI evaluation ─────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def supervisor_kpi(request):
    if not _require_supervisor(request.user):
        return redirect('/dashboard/employee/')

    supervisor_emp = get_employee_for_user(request.user)
    employees      = get_department_employees(request.user)

    # Handle KPI score submission
    if request.method == 'POST' and request.POST.get('action') == 'submit_kpi':
        from hr.services.kpi_service import submit_kpi_score
        emp_id = request.POST.get('employee_id')
        today  = timezone.localdate()
        data = {
            'evaluation_type': 'supervisor',
            'year':            int(request.POST.get('year',   today.year)),
            'period':          request.POST.get('period', 'H1' if today.month <= 6 else 'H2'),
            'job_knowledge':   int(request.POST.get('job_knowledge', 3)),
            'work_quality':    int(request.POST.get('work_quality',  3)),
            'attendance':      int(request.POST.get('attendance',    3)),
            'teamwork':        int(request.POST.get('teamwork',      3)),
            'ethics':          int(request.POST.get('ethics',        3)),
            'comments':        request.POST.get('comments', ''),
        }
        try:
            submit_kpi_score(int(emp_id), supervisor_emp, data)
            messages.success(request, "KPI evaluation submitted.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect('supervisor_kpi')

    from hr.models import BiannualKPIScore
    year_f   = request.GET.get('year',   str(timezone.localdate().year))
    period_f = request.GET.get('period', '')

    kpi_scores = BiannualKPIScore.objects.filter(
        employee__in=employees
    ).select_related('employee', 'evaluator').order_by('-year', 'period')

    if year_f:
        kpi_scores = kpi_scores.filter(year=year_f)
    if period_f:
        kpi_scores = kpi_scores.filter(period=period_f)

    ctx = _supervisor_context(request.user, {
        'employees':    employees,
        'kpi_scores':   kpi_scores,
        'year':         year_f,
        'period':       period_f,
        'periods':      [('H1', 'Jan–Jun'), ('H2', 'Jul–Dec')],
        'years':        [2024, 2025, 2026],
        'active_page':  'supervisor_kpi',
    })
    return render(request, 'hr/supervisor_kpi.html', ctx)


# ── Certificates ───────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def supervisor_certificates(request):
    if not _require_supervisor(request.user):
        return redirect('/dashboard/employee/')

    from hr.models import EmployeeCertificate
    from django.db.models import Q

    employees    = get_department_employees(request.user)
    certificates = (
        EmployeeCertificate.objects
        .filter(employee__in=employees)
        .select_related('employee', 'employee__department')
        .order_by('-uploaded_at')
    )

    query = request.GET.get('q', '').strip()
    if query:
        certificates = certificates.filter(
            Q(employee__first_name__icontains=query) |
            Q(employee__last_name__icontains=query)  |
            Q(title__icontains=query)
        )

    ctx = _supervisor_context(request.user, {
        'certificates': certificates,
        'search_query': query,
        'active_page':  'supervisor_certificates',
    })
    return render(request, 'hr/supervisor_certificates.html', ctx)
