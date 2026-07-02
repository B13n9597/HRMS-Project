# hr/views/hr_modules_views.py

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from hr.views.attendance_views import is_hr
from hr.models import Employee

@login_required(login_url='/login/')
def payroll_center(request):
    if not is_hr(request.user):
        return redirect('/login/')
        
    query = request.GET.get('q', '').strip()
    employees = Employee.objects.select_related('department', 'position').all()
    
    if query:
        employees = employees.filter(first_name__icontains=query) | employees.filter(last_name__icontains=query)

    context = {
        'employees': employees,
        'search_query': query,
        'active_page': 'payroll_center',
    }
    return render(request, 'hr/payroll_center.html', context)

@login_required(login_url='/login/')
def performance_kpis(request):
    if not is_hr(request.user):
        return redirect('/login/')
        
    query = request.GET.get('q', '').strip()
    employees = Employee.objects.select_related('department').all()
    
    if query:
        employees = employees.filter(first_name__icontains=query) | employees.filter(last_name__icontains=query)

    context = {
        'employees': employees,
        'search_query': query,
        'active_page': 'performance_kpis',
    }
    return render(request, 'hr/performance_kpis.html', context)

@login_required(login_url='/login/')
def candidate_screen(request):
    if not is_hr(request.user):
        return redirect('/login/')
        
    # Using Employee model as a stand-in for candidates to fulfill the UI requirement
    # Or an empty list if there are no candidates
    context = {
        'active_page': 'candidate_screen',
    }
    return render(request, 'hr/candidate_screen.html', context)

@login_required(login_url='/login/')
def global_settings(request):
    if not is_hr(request.user):
        return redirect('/login/')
        
    context = {
        'active_page': 'global_settings',
    }
    return render(request, 'hr/global_settings.html', context)

@login_required(login_url='/login/')
def my_salary_slips(request):
    """Employee view for salary slips"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return redirect('/')
        
    context = {
        'employee': employee,
        'active_page': 'my_salary_slips',
    }
    return render(request, 'hr/my_salary_slips.html', context)
