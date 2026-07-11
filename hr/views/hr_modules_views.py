# hr/views/hr_modules_views.py

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from hr.views.attendance_views import is_hr
from hr.models import (
    Employee, Payroll, PayrollRecord, PerformanceEvaluation,
    Application, SystemSetting, BiannualKPIScore, EmployeeCertificate,
)
from hr.services import leave_service
from hr.services.setting_service import get_settings_grouped_list, save_settings, seed_defaults


@login_required(login_url='/login/')
def payroll_center(request):
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    # Handle generate payroll POST
    if request.method == 'POST' and request.POST.get('action') == 'generate':
        from datetime import date
        from hr.services.payroll_service import generate_payroll
        try:
            period_start = date.fromisoformat(request.POST.get('period_start', ''))
            period_end   = date.fromisoformat(request.POST.get('period_end', ''))
            result = generate_payroll(period_start, period_end)
            messages.success(
                request,
                f"Payroll generated: {result['created']} records created, "
                f"{result['skipped']} skipped."
            )
            if result['errors']:
                messages.warning(request, "Errors: " + "; ".join(result['errors'][:5]))
        except Exception as e:
            messages.error(request, f"Payroll generation failed: {e}")
        return redirect('payroll_center')

    # Handle mark-paid POST
    if request.method == 'POST' and request.POST.get('action') == 'mark_paid':
        from hr.services.payroll_service import mark_paid
        record_id = request.POST.get('record_id')
        if record_id:
            try:
                mark_paid(int(record_id))
                messages.success(request, "Payroll record marked as Paid.")
            except Exception as e:
                messages.error(request, str(e))
        return redirect('payroll_center')

    query    = request.GET.get('q', '').strip()
    month    = request.GET.get('month', '')
    year     = request.GET.get('year', '')
    status_f = request.GET.get('status', '')

    from hr.services.payroll_service import get_all_payroll_records
    records = get_all_payroll_records(query=query, month=month, year=year, status=status_f)

    total_gross = sum(r.gross_salary for r in records)
    total_net   = sum(r.net_salary   for r in records)

    context = {
        'records':      records,
        'search_query': query,
        'month':        month,
        'year':         year,
        'status_f':     status_f,
        'total_gross':  total_gross,
        'total_net':    total_net,
        'active_page':  'payroll_center',
        'today':        timezone.localdate().isoformat(),
        'months': [
            (1,'January'),(2,'February'),(3,'March'),(4,'April'),
            (5,'May'),(6,'June'),(7,'July'),(8,'August'),
            (9,'September'),(10,'October'),(11,'November'),(12,'December')
        ],
        'years':    [2024, 2025, 2026],
        'statuses': ['Pending', 'Paid', 'On Hold'],
    }
    return render(request, 'hr/payroll_center.html', context)


@login_required(login_url='/login/')
def performance_kpis(request):
    """HR KPI dashboard — biannual scores + stats."""
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    from django.db.models import Q, Avg
    from hr.services.kpi_service import get_hr_kpi_dashboard

    query   = request.GET.get('q', '').strip()
    dept_id = request.GET.get('department_id', '')
    year    = request.GET.get('year', str(timezone.localdate().year))
    period  = request.GET.get('period', '')

    scores = (
        BiannualKPIScore.objects
        .select_related('employee', 'employee__department', 'evaluator')
        .order_by('-year', 'period', 'employee__last_name')
    )
    if query:
        scores = scores.filter(
            Q(employee__first_name__icontains=query) |
            Q(employee__last_name__icontains=query)
        )
    if dept_id:
        scores = scores.filter(employee__department_id=dept_id)
    if year:
        scores = scores.filter(year=year)
    if period:
        scores = scores.filter(period=period)

    # All employees for the submit-evaluation dropdown
    all_employees = Employee.objects.select_related('department').order_by('last_name', 'first_name')

    from hr.models import Department
    departments = Department.objects.all()
    kpi_stats   = get_hr_kpi_dashboard()

    context = {
        'scores':         scores,
        'all_employees':  all_employees,
        'departments':    departments,
        'search_query':   query,
        'dept_id':        dept_id,
        'year':           year,
        'period':         period,
        'active_page':    'performance_kpis',
        'kpi_stats':      kpi_stats,
        'periods':        [('H1', 'Jan–Jun'), ('H2', 'Jul–Dec')],
        'years':          [2024, 2025, 2026],
    }
    return render(request, 'hr/performance_kpis.html', context)


@login_required(login_url='/login/')
def my_kpi(request):
    """Employee views their own KPI scores and submits self-assessment."""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        from django.contrib import messages
        messages.error(request, "No employee profile found.")
        return redirect('dashboard_employee')

    from hr.services.kpi_service import submit_kpi_score, get_employee_kpi_summary

    if request.method == 'POST' and request.POST.get('action') == 'self_assess':
        today  = timezone.localdate()
        data = {
            'evaluation_type': 'self',
            'year':            request.POST.get('year',   today.year),
            'period':          request.POST.get('period', 'H1' if today.month <= 6 else 'H2'),
            'job_knowledge':   request.POST.get('job_knowledge', 3),
            'work_quality':    request.POST.get('work_quality',  3),
            'attendance':      request.POST.get('attendance',    3),
            'teamwork':        request.POST.get('teamwork',      3),
            'ethics':          request.POST.get('ethics',        3),
            'comments':        request.POST.get('comments', ''),
        }
        from django.contrib import messages
        try:
            submit_kpi_score(employee.pk, employee, data)
            messages.success(request, "Self-assessment submitted successfully.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect('my_kpi')

    summary = get_employee_kpi_summary(employee.pk)

    context = {
        'employee':      employee,
        'scores':        summary['scores'],
        'periods':       [('H1', 'Jan–Jun'), ('H2', 'Jul–Dec')],
        'years':         [2024, 2025, 2026],
        'active_page':   'my_kpi',
        'base_template': 'hr/hr_base.html' if is_hr(request.user) else 'hr/employee_base.html',
    }
    return render(request, 'hr/my_kpi.html', context)


@login_required(login_url='/login/')
def candidate_screen(request):
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    # Handle pipeline status change
    if request.method == 'POST':
        app_id    = request.POST.get('application_id')
        new_status = request.POST.get('new_status')
        if app_id and new_status:
            try:
                app = Application.objects.get(pk=app_id)
                app.status = new_status
                app.save(update_fields=['status'])
                # Run auto-screening when moving to Screening stage
                if new_status == 'Screening':
                    app.run_auto_screening()
                messages.success(request, f"Application status updated to {new_status}.")
            except Application.DoesNotExist:
                messages.error(request, "Application not found.")
            except Exception as e:
                messages.error(request, str(e))
        return redirect('candidate_screen')

    query    = request.GET.get('q', '').strip()
    status_f = request.GET.get('status', '')
    dept_id  = request.GET.get('department_id', '')

    from django.db.models import Q
    candidates = Application.objects.select_related(
        'applicant', 'job', 'job__department'
    ).order_by('-applied_date')

    if query:
        candidates = candidates.filter(
            Q(applicant__first_name__icontains=query) |
            Q(applicant__last_name__icontains=query)  |
            Q(applicant__email__icontains=query)
        )
    if status_f:
        candidates = candidates.filter(status=status_f)
    if dept_id:
        candidates = candidates.filter(job__department_id=dept_id)

    from hr.models import Department
    departments = Department.objects.all()

    # Pipeline counts
    pipeline_counts = {
        'Applied':       candidates.filter(status='Applied').count(),
        'Screening':     candidates.filter(status__in=['Screening','Qualified','Rejected_Auto']).count(),
        'Interviewed':   candidates.filter(status='Interviewed').count(),
        'Selected':      candidates.filter(status='Selected').count(),
        'Rejected':      candidates.filter(status='Rejected').count(),
    }

    context = {
        'candidates':      candidates,
        'departments':     departments,
        'pipeline_counts': pipeline_counts,
        'search_query':    query,
        'status_f':        status_f,
        'dept_id':         dept_id,
        'active_page':     'candidate_screen',
        'status_choices': [
            'Applied', 'Screening', 'Qualified', 'Interviewed', 'Selected',
            'Rejected_Auto', 'Rejected',
        ],
    }
    return render(request, 'hr/candidate_screen.html', context)


@login_required(login_url='/login/')
def global_settings(request):
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    if request.method == 'POST':
        save_settings(request.POST, request.user)
        messages.success(request, 'Settings saved successfully.')
        return redirect('global_settings')

    seed_defaults()
    from hr.services.setting_service import get_holiday_list

    settings_grouped = get_settings_grouped_list()
    holidays = get_holiday_list()

    context = {
        'settings_grouped': settings_grouped,
        'holidays':         holidays,
        'active_page':      'global_settings',
    }
    return render(request, 'hr/global_settings.html', context)


@login_required(login_url='/login/')
def my_salary_slips(request):
    """Employee view for salary slips using new PayrollRecord model."""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return redirect('/')

    from hr.services.payroll_service import get_employee_payroll_records
    payroll_records = get_employee_payroll_records(employee)

    context = {
        'employee':        employee,
        'payroll_records': payroll_records,
        'active_page':     'my_salary_slips',
        'base_template':   'hr/hr_base.html' if is_hr(request.user) else 'hr/employee_base.html',
    }
    return render(request, 'hr/my_salary_slips.html', context)


@login_required(login_url='/login/')
def departments_view(request):
    """Departments management page."""
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')
    from hr.models import Department, Employee
    departments = Department.objects.all().order_by('name')
    context = {
        'departments': departments,
        'active_page': 'departments',
    }
    return render(request, 'hr/departments.html', context)


@login_required(login_url='/login/')
def training_view(request):
    """Training placeholder page."""
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')
    context = {'active_page': 'training'}
    return render(request, 'hr/training.html', context)


@login_required(login_url='/login/')
def hr_reports_view(request):
    """HR Reports — summary of key metrics."""
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')
    from hr.models import Employee, Attendance, LeaveRequest, PayrollRecord
    from django.utils import timezone
    today = timezone.localdate()
    context = {
        'total_employees':   Employee.objects.count(),
        'present_today':     Attendance.objects.filter(date=today, status__in=['Present', 'Late']).count(),
        'pending_leaves':    LeaveRequest.objects.filter(status='Pending').count(),
        'pending_payroll':   PayrollRecord.objects.filter(payment_status='Pending').count(),
        'active_employees':  Employee.objects.filter(status__name__iexact='Active').count(),
        'active_page':       'hr_reports',
    }
    return render(request, 'hr/hr_reports.html', context)


@login_required(login_url='/login/')
def roles_permissions_view(request):
    """Roles & Permissions management page."""
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')
    from hr.models import Role, Employee
    roles = Role.objects.all().order_by('name')
    context = {
        'roles':       roles,
        'active_page': 'roles_permissions',
    }
    return render(request, 'hr/roles_permissions.html', context)
