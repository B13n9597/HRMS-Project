# hr/views/supervisor_views.py
#
# Supervisor dashboard — fully separate role-based portal.
# Supervisors see ONLY employees in their assigned department(s).

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q

from hr.forms import SupervisorTrainingRequestForm
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

    from django.db.models import Q
    
    employees = get_department_employees(request.user)
    today     = timezone.localdate()

    # Apply search filter
    query = request.GET.get('q', '').strip()
    if query:
        employees = employees.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query)
        )

    # Apply status filter
    status = request.GET.get('status', '')
    if status:
        employees = employees.filter(status__name__iexact=status)

    from hr.models import Attendance, LeaveRequest
    # Get all unfiltered for stats
    all_employees = get_department_employees(request.user)
    present_today  = Attendance.objects.filter(
        employee__in=all_employees, date=today, status__in=['Present', 'Late']
    ).count()
    pending_leaves = LeaveRequest.objects.filter(
        employee__in=all_employees, status='Pending'
    ).count()

    ctx = _supervisor_context(request.user, {
        'employees':      employees,
        'present_today':  present_today,
        'pending_leaves': pending_leaves,
        'employee_count': all_employees.count(),
        'search_query':   query,
        'status_f':       status,
        'statuses':       ['Active', 'On Leave', 'Terminated'],
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


# ── Training Requests ─────────────────────────────────────────────────────

@login_required(login_url='/login/')
def supervisor_training_requests(request):
    if not _require_supervisor(request.user):
        return redirect('/dashboard/employee/')

    from hr.models import TrainingRequest

    employees = get_department_employees(request.user)
    requests = (
        TrainingRequest.objects
        .filter(employee__in=employees, is_deleted=False)
        .select_related('employee', 'employee__department', 'department', 'supervisor')
        .order_by('-request_date')
    )

    status_f = request.GET.get('status', '')
    query = request.GET.get('q', '').strip()
    if status_f:
        requests = requests.filter(status=status_f)
    if query:
        requests = requests.filter(
            Q(employee__first_name__icontains=query) |
            Q(employee__last_name__icontains=query) |
            Q(title__icontains=query)
        )

    supervisor_emp = get_employee_for_user(request.user)
    request_form = SupervisorTrainingRequestForm(supervised_employees=employees)

    if request.method == 'POST' and request.POST.get('action') == 'request_training_for_employee':
        request_form = SupervisorTrainingRequestForm(request.POST, request.FILES, supervised_employees=employees)
        if request_form.is_valid():
            selected_employee = request_form.cleaned_data['employee']
            if selected_employee not in employees:
                messages.error(request, 'You can only request training for employees you supervise.')
                return redirect('supervisor_training_requests')
            training = request_form.save(commit=False)
            training.employee = selected_employee
            training.department = selected_employee.department
            training.request_source = 'Supervisor'
            training.requested_by = supervisor_emp
            training.supervisor = supervisor_emp
            training.status = 'HR Review'
            training.save()
            messages.success(request, 'Training request created and sent to HR for review.')
            return redirect('supervisor_training_requests')
        messages.error(request, 'Please review the supervisory training request form and try again.')
        return redirect('supervisor_training_requests')

    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        comment = request.POST.get('comment', '').strip()
        if not request_id or not action:
            messages.error(request, 'Missing request or action.')
            return redirect('supervisor_training_requests')
        if not comment:
            messages.error(request, 'A comment is required when approving or rejecting a training request.')
            return redirect('supervisor_training_requests')

        training = get_object_or_404(TrainingRequest, pk=request_id, employee__in=employees)
        training.supervisor = supervisor_emp
        training.supervisor_comment = comment
        training.supervisor_decision_date = timezone.now()
        training.status = 'HR Review' if action == 'approve' else 'Supervisor Rejected'
        training.save()
        messages.success(request, 'Training request decision recorded.')
        return redirect('supervisor_training_requests')

    ctx = _supervisor_context(request.user, {
        'requests': requests,
        'request_form': request_form,
        'search_query': query,
        'status_f': status_f,
        'statuses': ['Submitted', 'Supervisor Review', 'Supervisor Rejected', 'HR Review', 'HR Rejected', 'Approved', 'Completed'],
        'active_page': 'supervisor_training_requests',
    })
    return render(request, 'hr/supervisor_training_requests.html', ctx)


@login_required(login_url='/login/')
def supervisor_discipline_reports(request):
    if not _require_supervisor(request.user):
        return redirect('/dashboard/employee/')

    from hr.models import DisciplinaryIncident

    employees = get_department_employees(request.user)
    incidents = (
        DisciplinaryIncident.objects
        .filter(employee__in=employees, is_deleted=False)
        .select_related('employee', 'employee__department', 'reporting_supervisor', 'decided_by')
        .order_by('-incident_date')
    )

    query = request.GET.get('q', '').strip()
    if query:
        incidents = incidents.filter(
            Q(employee__first_name__icontains=query) |
            Q(employee__last_name__icontains=query) |
            Q(category__icontains=query)
        )

    ctx = _supervisor_context(request.user, {
        'incidents': incidents,
        'search_query': query,
        'active_page': 'supervisor_discipline_reports',
    })
    return render(request, 'hr/supervisor_discipline_reports.html', ctx)


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


# ── Hiring Request ─────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def supervisor_hiring_request(request):
    if not _require_supervisor(request.user):
        return redirect('/dashboard/employee/')

    supervisor_emp   = get_employee_for_user(request.user)
    supervised_depts = get_supervised_departments(request.user)
    
    dept = supervised_depts.first() if supervised_depts.exists() else (supervisor_emp.department if supervisor_emp else None)

    if request.method == 'POST':
        position_title       = request.POST.get('position_title', '').strip()
        number_needed        = request.POST.get('number_needed', 1)
        employment_type      = request.POST.get('employment_type', 'Full-Time')
        reason               = request.POST.get('reason', '').strip()
        qualification        = request.POST.get('qualification', '').strip()
        preferred_start_date = request.POST.get('preferred_start_date', '')
        selected_dept_id     = request.POST.get('department_id', '')

        if selected_dept_id and supervised_depts.filter(id=selected_dept_id).exists():
            dept = supervised_depts.get(id=selected_dept_id)

        if not supervisor_emp or not dept:
            messages.error(request, "Unable to determine your department.")
            return redirect('supervisor_hiring_request')

        if not position_title or not reason or not preferred_start_date:
            messages.error(request, "Please fill in all required fields (Position, Reason, Preferred Start Date).")
        else:
            try:
                from hr.models import HiringRequest
                HiringRequest.objects.create(
                    requested_by=supervisor_emp,
                    department=dept,
                    position_title=position_title,
                    number_needed=int(number_needed),
                    employment_type=employment_type,
                    reason=reason,
                    # Retain the existing database field while treating it as a qualification requirement.
                    required_skills=qualification,
                    preferred_start_date=preferred_start_date,
                    status='Pending',
                )
                messages.success(request, "Employee hiring request submitted to HR successfully.")
                return redirect('supervisor_hiring_request')
            except Exception as e:
                messages.error(request, f"Error submitting hiring request: {e}")

    from hr.models import HiringRequest, Position
    dept_ids = list(supervised_depts.values_list('id', flat=True))
    if supervisor_emp and supervisor_emp.department_id and supervisor_emp.department_id not in dept_ids:
        dept_ids.append(supervisor_emp.department_id)

    hiring_requests = HiringRequest.objects.filter(
        department_id__in=dept_ids
    ).select_related('requested_by', 'department', 'reviewed_by').order_by('-request_date')

    positions = Position.objects.filter(is_deleted=False)

    ctx = _supervisor_context(request.user, {
        'hiring_requests':  hiring_requests,
        'supervisor_dept':  dept,
        'positions':        positions,
        'employment_types': ['Full-Time', 'Part-Time', 'Contract', 'Internship', 'Temporary'],
        'active_page':      'supervisor_hiring_request',
    })
    return render(request, 'hr/supervisor_hiring_request.html', ctx)
