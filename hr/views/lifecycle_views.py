# hr/views/lifecycle_views.py

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from hr.views.attendance_views import is_hr
from hr.models import Employee

@login_required(login_url='/login/')
def my_lifecycle(request):
    """
    Employee views their own journey/lifecycle.
    """
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "No employee profile found.")
        return redirect('/')

    context = {
        'employee': employee,
        'active_page': 'my_lifecycle',
    }
    return render(request, 'hr/my_lifecycle.html', context)


@login_required(login_url='/login/')
def hr_lifecycle(request):
    """
    HR views all employees' lifecycles with search functionality.
    """
    if not is_hr(request.user):
        return redirect('/login/')

    query = request.GET.get('q', '').strip()
    
    employees = Employee.objects.select_related('department', 'position', 'status').order_by('-hire_date')
    
    if query:
        employees = employees.filter(first_name__icontains=query) | employees.filter(last_name__icontains=query)

    context = {
        'employees': employees,
        'search_query': query,
        'active_page': 'dashboard_hr',  # Maps to Employee Lifecycle in sidebar
    }
    return render(request, 'hr/employee_lifecycle.html', context)


@login_required(login_url='/login/')
def employee_details(request, id):
    """
    HR views full details of a specific employee.
    """
    if not is_hr(request.user):
        return redirect('/login/')

    try:
        employee = Employee.objects.select_related('department', 'position', 'status').get(id=id)
    except Employee.DoesNotExist:
        messages.error(request, "Employee not found.")
        return redirect('dashboard_hr')

    context = {
        'employee': employee,
        'active_page': 'dashboard_hr',
    }
    return render(request, 'hr/employee_details.html', context)
