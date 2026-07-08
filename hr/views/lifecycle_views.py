# hr/views/lifecycle_views.py

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q

from hr.views.attendance_views import is_hr
from hr.models import Employee, EmployeeHistory, EmployeeCertificate


@login_required(login_url='/login/')
def my_lifecycle(request):
    """Employee views their own lifecycle and can upload certificates."""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "No employee profile found.")
        return redirect('/')

    # Handle certificate upload
    if request.method == 'POST' and request.POST.get('action') == 'upload_cert':
        title      = request.POST.get('title', '').strip()
        cert_type  = request.POST.get('cert_type', 'other')
        issued_by  = request.POST.get('issued_by', '').strip()
        issued_date = request.POST.get('issued_date') or None
        expiry_date = request.POST.get('expiry_date') or None
        doc_file   = request.FILES.get('document')

        if not title:
            messages.error(request, "Certificate title is required.")
        else:
            EmployeeCertificate.objects.create(
                employee    = employee,
                title       = title,
                cert_type   = cert_type,
                issued_by   = issued_by,
                issued_date = issued_date or None,
                expiry_date = expiry_date or None,
                document    = doc_file,
            )
            messages.success(request, "Certificate uploaded successfully.")
        return redirect('my_lifecycle')

    history      = EmployeeHistory.objects.filter(employee=employee).order_by('-start_date')
    certificates = EmployeeCertificate.objects.filter(employee=employee).order_by('-uploaded_at')

    context = {
        'employee':     employee,
        'history':      history,
        'certificates': certificates,
        'cert_types':   EmployeeCertificate.CERT_TYPES,
        'active_page':  'my_lifecycle',
    }
    return render(request, 'hr/my_lifecycle.html', context)


@login_required(login_url='/login/')
def hr_lifecycle(request):
    """HR views all employees' lifecycles with search functionality."""
    if not is_hr(request.user):
        return redirect('my_lifecycle')

    query = request.GET.get('q', '').strip()
    dept_id = request.GET.get('department_id', '')

    employees = Employee.objects.select_related(
        'department', 'position', 'status', 'role'
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

    history      = EmployeeHistory.objects.filter(employee=employee).order_by('-start_date')
    certificates = EmployeeCertificate.objects.filter(employee=employee).order_by('-uploaded_at')

    # Attendance summary (last 30 days)
    from hr.models import Attendance
    from django.utils import timezone
    today      = timezone.localdate()
    month_ago  = today.replace(day=1)
    attendance = Attendance.objects.filter(
        employee=employee, date__gte=month_ago
    ).order_by('-date')

    # KPI scores
    from hr.models import BiannualKPIScore
    kpi_scores = BiannualKPIScore.objects.filter(
        employee=employee
    ).order_by('-year', 'period')

    context = {
        'employee':     employee,
        'history':      history,
        'certificates': certificates,
        'attendance':   attendance,
        'kpi_scores':   kpi_scores,
        'active_page':  'dashboard_hr',
    }
    return render(request, 'hr/employee_details.html', context)
