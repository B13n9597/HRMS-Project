# hr/views/lifecycle_views.py

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Exists, OuterRef

from hr.views.attendance_views import is_hr
from hr.models import Employee, EmployeeHistory, EmployeeCertificate
from hr.forms import EmployeeCertificateForm
from hr.services import employee_service


def csrf_failure(request, reason=""):
    """Graceful fallback for CSRF verification failures."""
    context = {
        'reason': reason,
    }
    return render(request, 'hr/csrf_failure.html', context, status=403)


@login_required(login_url='/login/')
def my_lifecycle(request):
    """Employee views their own career lifecycle and can upload certificates."""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "No employee profile found.")
        return redirect('/')

    # Handle certificate upload
    form = EmployeeCertificateForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and request.POST.get('action') == 'upload_cert':
        if form.is_valid():
            certificate = form.save(commit=False)
            certificate.employee = employee
            certificate.save()
            messages.success(request, "Certificate uploaded successfully.")
            return redirect('my_lifecycle')
        else:
            messages.error(request, "Please fix the errors below before uploading.")

    # Career events only — leave requests and operational records are
    # handled by their own modules and must not appear in this timeline.
    career_types = list(EmployeeHistory.CAREER_EVENT_TYPES)
    history = (
        EmployeeHistory.objects
        .filter(employee=employee, event_type__in=career_types)
        .select_related('department', 'position', 'recorded_by')
        .order_by('-start_date')
    )

    # Auto-create the initial "Employee Created" event if none exist yet
    # (backfill for employees created before the signal was added)
    if not history.exists():
        EmployeeHistory.objects.get_or_create(
            employee   = employee,
            event_type = 'hired',
            defaults={
                'department': employee.department,
                'position':   employee.position,
                'new_value':  employee.status.name if employee.status else 'Active',
                'notes':      'Employee record created.',
                'start_date': employee.hire_date,
            }
        )
        history = (
            EmployeeHistory.objects
            .filter(employee=employee, event_type__in=career_types)
            .select_related('department', 'position', 'recorded_by')
            .order_by('-start_date')
        )

    certificates = EmployeeCertificate.objects.filter(employee=employee).order_by('-uploaded_at')

    context = {
        'employee':      employee,
        'history':       history,
        'certificates':  certificates,
        'form':          form,
        'cert_types':    EmployeeCertificate.CERT_TYPES,
        'active_page':   'my_lifecycle',
        'base_template': employee_service.get_base_template(request.user),
    }
    return render(request, 'hr/my_lifecycle.html', context)


@login_required(login_url='/login/')
def hr_lifecycle(request):
    """HR views all employees' lifecycles with search functionality."""
    if not is_hr(request.user):
        return redirect('my_lifecycle')

    query   = request.GET.get('q', '').strip()
    dept_id = request.GET.get('department_id', '')

    ev = EmployeeHistory.objects.filter(employee_id=OuterRef('pk'), is_deleted=False)

    employees = Employee.objects.select_related(
        'department', 'position', 'status', 'role'
    ).annotate(
        # Stage 1: hired — everyone has been hired
        has_hired=Exists(ev.filter(event_type='hired')),
        # Stage 2: onboarding complete or probation passed
        has_onboarding=Exists(ev.filter(
            event_type__in=['onboarding_completed', 'recruitment_completed',
                            'probation_passed', 'probation_started']
        )),
        # Stage 3: active employment (annotated for completeness)
        has_employment=Exists(ev.filter(event_type__in=['hired', 'probation_passed'])),
        # Stage 4: career progression
        has_progression=Exists(ev.filter(
            event_type__in=['promoted', 'transferred', 'position_change',
                            'salary_change', 'contract_renewed', 'salary_raise']
        )),
        # Stage 5: development events
        has_development=Exists(ev.filter(
            event_type__in=['training_completed', 'performance_review']
        )),
        # Stage 6: exit events
        has_exit=Exists(ev.filter(
            event_type__in=['terminated', 'resigned', 'retired']
        )),
        # Used in the old template — keep for backward compat
        has_promotion=Exists(ev.filter(event_type='promoted')),
        has_retirement=Exists(ev.filter(event_type='retired')),
    ).order_by('first_name', 'last_name')

    if query:
        employees = employees.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query)
        )
    if dept_id:
        employees = employees.filter(department_id=dept_id)

    from hr.models import Department
    departments = Department.objects.all()

    context = {
        'employees':    employees,
        'departments':  departments,
        'search_query': query,
        'dept_id':      dept_id,
        'active_page':  'hr_lifecycle',
    }
    return render(request, 'hr/employee_lifecycle.html', context)


@login_required(login_url='/login/')
def employee_details(request, id):
    """HR/Supervisor views full details of a specific employee."""
    from hr.services.employee_service import can_supervise, get_supervised_departments, get_role_key, ROLE_HR, ROLE_DEAN, ROLE_SUPERVISOR

    role_key = get_role_key(request.user)
    can_view = role_key in {ROLE_HR, ROLE_DEAN, ROLE_SUPERVISOR}

    if not can_view:
        return redirect('/login/')

    try:
        employee = Employee.objects.select_related(
            'department', 'position', 'status', 'role', 'user'
        ).get(id=id)
    except Employee.DoesNotExist:
        messages.error(request, "Employee not found.")
        return redirect('dashboard_hr')

    # Supervisors may only view employees in their departments
    if role_key == ROLE_SUPERVISOR:
        supervised_depts = get_supervised_departments(request.user)
        if employee.department not in supervised_depts:
            messages.error(request, "Access denied.")
            return redirect('supervisor_dashboard')

    career_types = list(EmployeeHistory.CAREER_EVENT_TYPES)
    history = (
        EmployeeHistory.objects
        .filter(employee=employee, event_type__in=career_types)
        .select_related('department', 'position', 'recorded_by')
        .order_by('-start_date')
    )

    # Auto-create the initial hired event for legacy employees
    if not history.exists():
        EmployeeHistory.objects.get_or_create(
            employee   = employee,
            event_type = 'hired',
            defaults={
                'department': employee.department,
                'position':   employee.position,
                'new_value':  employee.status.name if employee.status else 'Active',
                'notes':      'Employee record created.',
                'start_date': employee.hire_date,
            }
        )
        history = (
            EmployeeHistory.objects
            .filter(employee=employee, event_type__in=career_types)
            .select_related('department', 'position', 'recorded_by')
            .order_by('-start_date')
        )

    certificates = EmployeeCertificate.objects.filter(employee=employee).order_by('-uploaded_at')

    # KPI scores
    from hr.models import BiannualKPIScore
    kpi_scores = BiannualKPIScore.objects.filter(
        employee=employee
    ).order_by('-year', 'period')

    # Payroll records
    from hr.models import PayrollRecord
    payroll_records = PayrollRecord.objects.filter(employee=employee).order_by('-period_start')

    context = {
        'employee':      employee,
        'history':       history,
        'certificates':  certificates,
        'kpi_scores':    kpi_scores,
        'payroll_records': payroll_records,
        'active_page':   'dashboard_hr',
    }
    return render(request, 'hr/employee_details.html', context)
