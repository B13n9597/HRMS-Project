# hr/views/hr_modules_views.py

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from django.db.models import Q

from hr.views.attendance_views import is_hr
from hr.models import (
    Employee, Payroll, PayrollRecord, PerformanceEvaluation,
    Application, SystemSetting, BiannualKPIScore, EmployeeCertificate,
    TrainingRequest, DisciplinaryIncident, Grievance, Department, EmployeeHistory,
)
from hr.services import leave_service, employee_service
from hr.views.recruitment_views import convert_application_to_employee
from hr.services.setting_service import get_settings_grouped_list, save_settings, seed_defaults
from hr.forms import TrainingRequestForm, GrievanceForm, DisciplinaryIncidentForm, TrainingCompletionForm


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
    """Employee peer evaluation page: search & evaluate peers (left), view own received evaluations (right)."""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        from django.contrib import messages
        messages.error(request, "No employee profile found.")
        return redirect('dashboard_employee')

    from hr.services.kpi_service import submit_kpi_score, get_employee_kpi_summary

    # Handle peer evaluation submission
    if request.method == 'POST' and request.POST.get('action') == 'peer_evaluate':
        today = timezone.localdate()
        target_id = request.POST.get('target_employee_id')
        data = {
            'evaluation_type': 'peer',
            'year':            request.POST.get('year', today.year),
            'period':          request.POST.get('period', 'H1' if today.month <= 6 else 'H2'),
            'job_knowledge':   request.POST.get('job_knowledge', 3),
            'work_quality':    request.POST.get('work_quality', 3),
            'attendance':      request.POST.get('attendance', 3),
            'teamwork':        request.POST.get('teamwork', 3),
            'ethics':          request.POST.get('ethics', 3),
            'comments':        request.POST.get('comments', ''),
        }
        from django.contrib import messages
        try:
            submit_kpi_score(int(target_id), employee, data)
            messages.success(request, "Peer evaluation submitted successfully.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect('my_kpi')

    # Handle self-assessment submission (keep backward compatibility)
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

    # Fetch data for display
    from hr.models import BiannualKPIScore

    # All employees except self (for search / peer evaluation)
    all_employees = Employee.objects.filter(
        is_deleted=False
    ).exclude(pk=employee.pk).select_related('department', 'position').order_by('first_name', 'last_name')

    # Evaluations received by this employee (peer + supervisor + hr)
    received_evaluations = BiannualKPIScore.objects.filter(
        employee=employee
    ).exclude(evaluation_type='self').select_related('evaluator').order_by('-submitted_at')

    # Self-assessment scores
    summary = get_employee_kpi_summary(employee.pk)
    self_scores = summary['scores'].filter(evaluation_type='self')

    # Peer evaluations given by this employee
    given_evaluations = BiannualKPIScore.objects.filter(
        evaluator=employee, evaluation_type='peer'
    ).select_related('employee').order_by('-submitted_at')

    context = {
        'employee':              employee,
        'all_employees':         all_employees,
        'received_evaluations':  received_evaluations,
        'given_evaluations':     given_evaluations,
        'scores':                self_scores,
        'periods':               [('H1', 'Jan–Jun'), ('H2', 'Jul–Dec')],
        'years':                 [2024, 2025, 2026],
        'active_page':           'my_kpi',
        'base_template':         employee_service.get_base_template(request.user),
    }
    return render(request, 'hr/my_kpi.html', context)


@login_required(login_url='/login/')
def candidate_screen(request):
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    try:
        hr_emp = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'HR profile not found.')
        return redirect('/')

    if request.method == 'POST':
        action = request.POST.get('action')
        hr_comment = request.POST.get('hr_comment', '').strip()

        if action == 'approve_hiring_request':
            req_id = request.POST.get('hiring_request_id')
            try:
                from hr.models import HiringRequest
                h_req = HiringRequest.objects.get(pk=req_id)
                new_status = 'Approved'

                h_req.status = new_status
                h_req.hr_comment = hr_comment
                h_req.reviewed_by = hr_emp
                h_req.decision_date = timezone.now()
                h_req.save()

                messages.success(request, f"Hiring request for '{h_req.position_title}' approved.")
            except Exception as e:
                messages.error(request, f"Error updating hiring request: {e}")
            return redirect('candidate_screen')

        elif action == 'create_vacancy_from_request':
            req_id = request.POST.get('hiring_request_id')
            try:
                from hr.models import HiringRequest, JobPosting
                h_req = HiringRequest.objects.get(pk=req_id)
                if h_req.status == 'Approved' and not h_req.created_vacancy:
                    vacancy = JobPosting.objects.create(
                        title=h_req.position_title,
                        department=h_req.department,
                        description=f"Employment Type: {h_req.employment_type}\nReason: {h_req.reason}\nNumber Needed: {h_req.number_needed}",
                        posted_date=timezone.localdate(),
                        closing_date=h_req.preferred_start_date,
                        required_skills=h_req.required_skills,
                    )
                    h_req.created_vacancy = vacancy
                    h_req.save(update_fields=['created_vacancy'])
                    messages.success(request, f"Job Vacancy created for '{h_req.position_title}'.")
            except Exception as e:
                messages.error(request, f"Error creating vacancy: {e}")
            return redirect('candidate_screen')

        else:
            # Handle pipeline status change
            app_id = request.POST.get('application_id')
            new_status = request.POST.get('new_status')
            if app_id and new_status:
                try:
                    if new_status not in {'Selected', 'Hired', 'Rejected'}:
                        messages.error(request, "Applications can only be selected, hired, or rejected from this screen.")
                        return redirect('candidate_screen')
                    app = Application.objects.get(pk=app_id)
                    app.status = new_status
                    app.save(update_fields=['status'])
                    if new_status in {'Selected', 'Hired'}:
                        employee, created = convert_application_to_employee(app)
                        if created:
                            messages.success(request, f"{employee.get_full_name()} converted to employee and setup email sent.")
                            messages.success(request, "Employee conversion complete.", extra_tags='toast')
                        else:
                            messages.info(request, "Applicant was already converted to an employee.")
                            messages.info(request, "Employee already exists.", extra_tags='toast')
                        return redirect('staff_directory')
                    else:
                        messages.success(request, f"Application status updated to {new_status}.")
                except Application.DoesNotExist:
                    messages.error(request, "Application not found.")
                except Exception as e:
                    messages.error(request, str(e))
            return redirect('candidate_screen')

    # Retrieve search parameters
    query = request.GET.get('q', '').strip()
    status_f = request.GET.get('status', '')
    dept_id = request.GET.get('department_id', '')
    candidates = Application.objects.select_related('applicant', 'job', 'job__department').order_by('-applied_date')

    if query:
        candidates = candidates.filter(
            Q(applicant__first_name__icontains=query) |
            Q(applicant__last_name__icontains=query) |
            Q(applicant__email__icontains=query)
        )
    if status_f:
        candidates = candidates.filter(status=status_f)
    if dept_id:
        candidates = candidates.filter(job__department_id=dept_id)

    departments = Department.objects.all()
    hiring_requests = HiringRequest.objects.select_related('requested_by', 'department', 'reviewed_by', 'created_vacancy').order_by('-request_date')

    pipeline_counts = {
        'Applied': candidates.filter(status='Applied').count(),
        'Screening': candidates.filter(status__in=['Screening', 'Qualified', 'Rejected_Auto']).count(),
        'Interviewed': candidates.filter(status='Interviewed').count(),
        'Selected': candidates.filter(status='Selected').count(),
        'Rejected': candidates.filter(status='Rejected').count(),
    }

    context = {
        'candidates': candidates,
        'departments': departments,
        'hiring_requests': hiring_requests,
        'pipeline_counts': pipeline_counts,
        'search_query': query,
        'status_f': status_f,
        'dept_id': dept_id,
        'active_page': 'candidate_screen',
        'status_choices': [
            'Applied', 'Screening', 'Qualified', 'Interviewed', 'Selected', 'Rejected_Auto', 'Rejected',
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
        'base_template':   employee_service.get_base_template(request.user),
    }
    return render(request, 'hr/my_salary_slips.html', context)


@login_required(login_url='/login/')
def departments_view(request):
    """Departments management page."""
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')
    from hr.models import Department, Employee
    departments = Department.objects.select_related('manager').filter(is_deleted=False).order_by('name')
    context = {
        'departments': departments,
        'active_page': 'departments',
    }
    return render(request, 'hr/departments.html', context)


@login_required(login_url='/login/')
def my_training_view(request):
    """Employee training and CPD portal."""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return redirect('/dashboard/employee/')

    if request.method == 'POST' and request.POST.get('action') == 'request_training':
        form = TrainingRequestForm(request.POST, request.FILES)
        if form.is_valid():
            record = form.save(commit=False)
            record.employee = employee
            record.department = employee.department
            record.request_source = 'Employee'
            record.requested_by = employee
            record.status = 'Supervisor Review'
            record.save()
            messages.success(request, 'Training request submitted successfully and sent for supervisor review.')
            return redirect('my_training')
        messages.error(request, 'Please review the training request form and try again.')
    elif request.method == 'POST' and request.POST.get('action') == 'submit_completion':
        training = get_object_or_404(TrainingRequest, pk=request.POST.get('request_id'), employee=employee)
        completion_form = TrainingCompletionForm(request.POST, request.FILES, instance=training)
        if completion_form.is_valid():
            completion_form.save()
            training.status = 'Completed'
            training.save(update_fields=['status', 'completion_date', 'cpd_points', 'certificate', 'skills_learned', 'knowledge_transfer_method', 'feedback', 'satisfaction_rating'])
            messages.success(request, 'Training completion details submitted successfully.')
            return redirect('my_training')
        messages.error(request, 'Please complete the training feedback form correctly.')
    else:
        form = TrainingRequestForm()

    requests = TrainingRequest.objects.filter(employee=employee, is_deleted=False).select_related('department').order_by('-request_date')
    completed = requests.filter(status='Completed')
    total_cpd = sum(item.cpd_points for item in completed)
    academic_target = 60 if 'academic' in (employee.position.title if employee.position else '').lower() else None
    remaining_cpd = academic_target - total_cpd if academic_target else 0
    requests_with_forms = []
    for request_item in requests:
        requests_with_forms.append((request_item, TrainingCompletionForm(instance=request_item)))

    context = {
        'employee': employee,
        'form': form,
        'requests': requests,
        'requests_with_forms': requests_with_forms,
        'completed_requests': completed,
        'total_cpd': total_cpd,
        'academic_target': academic_target,
        'remaining_cpd': remaining_cpd,
        'active_page': 'my_training',
        'base_template': 'hr/employee_base.html',
    }
    return render(request, 'hr/my_training.html', context)


@login_required(login_url='/login/')
def my_grievances_view(request):
    """Employee grievance submission page with record history."""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return redirect('/dashboard/employee/')

    if request.method == 'POST' and request.POST.get('action') == 'submit_grievance':
        form = GrievanceForm(request.POST, request.FILES)
        if form.is_valid():
            grievance = form.save(commit=False)
            grievance.employee = employee
            grievance.department = employee.department
            grievance.save()
            messages.success(request, 'Grievance submitted successfully.')
            return redirect('my_grievances')
    else:
        form = GrievanceForm()

    grievances = Grievance.objects.filter(employee=employee, is_deleted=False).order_by('-submitted_at')
    context = {
        'employee': employee,
        'form': form,
        'grievances': grievances,
        'active_page': 'my_grievances',
        'base_template': 'hr/employee_base.html',
    }
    return render(request, 'hr/my_grievances.html', context)


@login_required(login_url='/login/')
def training_view(request):
    """HR training and CPD management page."""
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    if request.method == 'POST' and request.POST.get('action') == 'hr_decision':
        request_id = request.POST.get('request_id')
        action = request.POST.get('decision')
        hr_comment = request.POST.get('hr_comment', '').strip()
        if not request_id or not action:
            messages.error(request, 'Missing training request or decision.')
            return redirect('training')
        if not hr_comment:
            messages.error(request, 'A decision comment is required for HR approval or rejection.')
            return redirect('training')
        training = get_object_or_404(TrainingRequest, pk=request_id)
        training.hr_comment = hr_comment
        training.hr_decision_date = timezone.now()
        training.status = 'Approved' if action == 'approve' else 'HR Rejected'
        training.save()
        messages.success(request, 'HR decision recorded.')
        return redirect('training')

    if request.method == 'POST' and request.POST.get('action') == 'complete_training':
        form = TrainingCompletionForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, 'Please complete all required completion fields.')
        else:
            training = get_object_or_404(TrainingRequest, pk=request.POST.get('request_id'))
            training.completion_date = form.cleaned_data['completion_date'] or timezone.now()
            training.cpd_points = form.cleaned_data['cpd_points'] or 0
            training.certificate = form.cleaned_data['certificate']
            training.skills_learned = form.cleaned_data['skills_learned']
            training.knowledge_transfer_method = form.cleaned_data['knowledge_transfer_method']
            training.feedback = form.cleaned_data['feedback']
            training.satisfaction_rating = form.cleaned_data['satisfaction_rating']
            training.status = 'Completed'
            training.save()
            messages.success(request, 'Training completion recorded and CPD points updated.')
        return redirect('training')

    query = request.GET.get('q', '').strip()
    dept_id = request.GET.get('department_id', '')
    year = request.GET.get('year', str(timezone.localdate().year))

    requests = TrainingRequest.objects.select_related('employee', 'employee__department', 'department').filter(is_deleted=False).order_by('-request_date')
    if query:
        requests = requests.filter(
            Q(title__icontains=query) |
            Q(employee__first_name__icontains=query) |
            Q(employee__last_name__icontains=query)
        )
    if dept_id:
        requests = requests.filter(department_id=dept_id)
    if year:
        requests = requests.filter(start_date__year=year)

    departments = Department.objects.order_by('name')
    employees = Employee.objects.select_related('department').order_by('last_name', 'first_name')
    completed_requests = requests.filter(status='Completed')
    approved_count = requests.filter(status='Approved').count()
    completed_count = completed_requests.count()
    total_training_cost = sum((item.cost or 0) for item in requests)
    completed_satisfaction = [item.satisfaction_rating for item in completed_requests if item.satisfaction_rating not in (None, '')]
    average_satisfaction_rating = round(sum(completed_satisfaction) / len(completed_satisfaction), 2) if completed_satisfaction else 0
    below_cpd_target_count = requests.filter(cpd_points__lt=60).count()

    context = {
        'requests': requests,
        'departments': departments,
        'employees': employees,
        'search_query': query,
        'dept_id': dept_id,
        'year': year,
        'years': sorted({item.year for item in TrainingRequest.objects.filter(is_deleted=False, start_date__isnull=False).values_list('start_date', flat=True)}, reverse=True),
        'approved_count': approved_count,
        'completed_count': completed_count,
        'total_training_cost': total_training_cost,
        'average_satisfaction_rating': average_satisfaction_rating,
        'below_cpd_target_count': below_cpd_target_count,
        'active_page': 'training',
    }
    return render(request, 'hr/training.html', context)


@login_required(login_url='/login/')
def hr_discipline_cases(request):
    """HR discipline and incident case management."""
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    if request.method == 'POST' and request.POST.get('action') == 'create_incident':
        employee_id = request.POST.get('employee_id')
        if not employee_id:
            messages.error(request, 'Please select an employee before recording the incident.')
            return redirect('hr_discipline_cases')
        employee = get_object_or_404(Employee, pk=employee_id)
        form = DisciplinaryIncidentForm(request.POST, request.FILES)
        if form.is_valid():
            incident = form.save(commit=False)
            incident.employee = employee
            incident.department = employee.department
            incident.reporting_supervisor = get_object_or_404(Employee, pk=request.POST.get('reporting_supervisor_id')) if request.POST.get('reporting_supervisor_id') else None
            incident.save()
            messages.success(request, 'Disciplinary incident recorded.')
            return redirect('hr_discipline_cases')
        messages.error(request, 'Please review the incident form entries.')
    else:
        form = DisciplinaryIncidentForm()

    incidents = DisciplinaryIncident.objects.select_related('employee', 'employee__department', 'reporting_supervisor', 'decided_by').filter(is_deleted=False).order_by('-incident_date')
    employees = Employee.objects.select_related('department').order_by('last_name', 'first_name')
    context = {
        'form': form,
        'incidents': incidents,
        'employees': employees,
        'active_page': 'hr_discipline_cases',
    }
    return render(request, 'hr/hr_discipline_cases.html', context)


@login_required(login_url='/login/')
def hr_grievances(request):
    """HR grievance review and resolution page."""
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    if request.method == 'POST' and request.POST.get('action') == 'update_grievance':
        grievance = get_object_or_404(Grievance, pk=request.POST.get('grievance_id'))
        grievance.status = request.POST.get('status', grievance.status)
        grievance.assigned_investigator_id = request.POST.get('assigned_investigator_id') or None
        grievance.investigation_notes = request.POST.get('investigation_notes', '')
        grievance.findings = request.POST.get('findings', '')
        grievance.corrective_action = request.POST.get('corrective_action', '')
        grievance.response = request.POST.get('response', '')
        grievance.resolved_at = timezone.now() if grievance.status in {'Resolved', 'Closed'} else None
        grievance.save()
        messages.success(request, 'Grievance updated successfully.')
        return redirect('hr_grievances')

    grievances = Grievance.objects.select_related('employee', 'employee__department', 'assigned_investigator').filter(is_deleted=False).order_by('-submitted_at')
    employees = Employee.objects.select_related('department').order_by('last_name', 'first_name')
    context = {
        'grievances': grievances,
        'employees': employees,
        'active_page': 'hr_grievances',
    }
    return render(request, 'hr/hr_grievances.html', context)


@login_required(login_url='/login/')
def career_development_view(request):
    """HR career progression view based on recorded lifecycle and training data."""
    if not is_hr(request.user):
        return redirect('/dashboard/employee/')

    context = {
        'active_page': 'career_development',
        'recent_events': EmployeeHistory.objects.select_related('employee', 'department', 'position').filter(
            is_deleted=False, event_type__in=['hired', 'probation_passed', 'promoted', 'retired']
        ).order_by('-start_date')[:30],
        'promotion_count': EmployeeHistory.objects.filter(is_deleted=False, event_type='promoted').count(),
        'retirement_count': EmployeeHistory.objects.filter(is_deleted=False, event_type='retired').count(),
        'completed_training_count': TrainingRequest.objects.filter(is_deleted=False, status='Completed').count(),
    }
    return render(request, 'hr/career_development.html', context)


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
