# hr/views/hr_modules_views.py

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from hr.views.attendance_views import is_hr
from hr.models import Employee, Payroll, PerformanceEvaluation, Application, SystemSetting


@login_required(login_url='/login/')
def payroll_center(request):
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    query    = request.GET.get('q', '').strip()
    month    = request.GET.get('month', '')
    year     = request.GET.get('year', '')
    status_f = request.GET.get('status', '')

    records = (
        Payroll.objects
        .select_related('employee', 'employee__department', 'employee__position')
        .order_by('-period_start', 'employee__last_name')
    )

    if query:
        records = records.filter(
            employee__first_name__icontains=query
        ) | records.filter(employee__last_name__icontains=query)
    if month:
        records = records.filter(period_start__month=month)
    if year:
        records = records.filter(period_start__year=year)
    if status_f:
        records = records.filter(payment_status=status_f)

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
        'months': [
            (1,'January'),(2,'February'),(3,'March'),(4,'April'),
            (5,'May'),(6,'June'),(7,'July'),(8,'August'),
            (9,'September'),(10,'October'),(11,'November'),(12,'December')
        ],
        'years':   [2024, 2025, 2026],
        'statuses': ['Pending', 'Paid', 'On Hold'],
    }
    return render(request, 'hr/payroll_center.html', context)


@login_required(login_url='/login/')
def performance_kpis(request):
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    query    = request.GET.get('q', '').strip()
    dept_id  = request.GET.get('department_id', '')
    type_f   = request.GET.get('eval_type', '')

    evals = (
        PerformanceEvaluation.objects
        .select_related('employee', 'employee__department', 'evaluator')
        .order_by('-evaluation_date')
    )

    if query:
        evals = evals.filter(
            employee__first_name__icontains=query
        ) | evals.filter(employee__last_name__icontains=query)
    if dept_id:
        evals = evals.filter(employee__department_id=dept_id)
    if type_f:
        evals = evals.filter(evaluation_type=type_f)

    from hr.models import Department
    departments = Department.objects.all()

    context = {
        'evaluations':  evals,
        'departments':  departments,
        'search_query': query,
        'dept_id':      dept_id,
        'type_f':       type_f,
        'active_page':  'performance_kpis',
        'eval_types': [
            ('probation_review', 'Probation Review'),
            ('annual',           'Annual Review'),
            ('peer',             'Peer Review'),
            ('self',             'Self Review'),
        ],
    }
    return render(request, 'hr/performance_kpis.html', context)


@login_required(login_url='/login/')
def candidate_screen(request):
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    query    = request.GET.get('q', '').strip()
    status_f = request.GET.get('status', '')

    candidates = Application.objects.select_related('job_posting').order_by('-created_at')

    if query:
        candidates = candidates.filter(
            applicant_name__icontains=query
        ) | candidates.filter(applicant_email__icontains=query)
    if status_f:
        candidates = candidates.filter(status=status_f)

    context = {
        'candidates':   candidates,
        'search_query': query,
        'status_f':     status_f,
        'active_page':  'candidate_screen',
    }
    return render(request, 'hr/candidate_screen.html', context)


@login_required(login_url='/login/')
def global_settings(request):
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    if request.method == 'POST':
        for key, value in request.POST.items():
            if key.startswith('setting_'):
                parts = key.replace('setting_', '').split('__')
                if len(parts) == 2:
                    category, name = parts
                    SystemSetting.objects.update_or_create(
                        category=category,
                        name=name,
                        defaults={'value': value}
                    )
        from django.contrib import messages
        messages.success(request, 'Settings saved successfully.')

    settings_qs = SystemSetting.objects.all().order_by('category', 'name')
    settings_grouped = {}
    for s in settings_qs:
        settings_grouped.setdefault(s.category, []).append(s)

    context = {
        'settings_grouped': settings_grouped,
        'active_page':      'global_settings',
    }
    return render(request, 'hr/global_settings.html', context)


@login_required(login_url='/login/')
def my_salary_slips(request):
    """Employee view for salary slips"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return redirect('/')

    payroll_records = (
        Payroll.objects
        .filter(employee=employee)
        .order_by('-period_start')[:24]
    )

    context = {
        'employee':        employee,
        'payroll_records': payroll_records,
        'active_page':     'my_salary_slips',
    }
    return render(request, 'hr/my_salary_slips.html', context)
