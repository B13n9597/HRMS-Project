"""Public application and HR recruitment workflow."""
import logging
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from hr.forms import PublicApplicationForm
from hr.models import Application, Employee, EmployeeStatus, Role
from hr.views.attendance_views import is_hr


def careers(request):
    """Unauthenticated application endpoint; all validation happens in the form."""
    form = PublicApplicationForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save_application()
        messages.success(request, 'Your application was submitted successfully. We will contact you if shortlisted.')
        return redirect('careers')
    return render(request, 'hr/careers.html', {'form': form})


@login_required(login_url='/login/')
def recruitment_dashboard(request):
    if not is_hr(request.user):
        messages.error(request, 'Access denied.')
        return redirect('/')

    applications = Application.objects.select_related('applicant', 'job', 'converted_employee').order_by('-id')
    job_id, qualification, status = (request.GET.get(key, '').strip() for key in ('job', 'qualification', 'status'))
    if job_id:
        applications = applications.filter(job_id=job_id)
    if qualification:
        applications = applications.filter(applicant__qualification__icontains=qualification)
    if status:
        applications = applications.filter(status=status)

    # Automatically onboard any existing Selected/Hired applications that were not converted yet.
    pending_conversion = applications.filter(status__in=['Selected', 'Hired'], converted_employee__isnull=True)
    for app in pending_conversion:
        convert_application_to_employee(app)

    if request.method == 'POST':
        application = get_object_or_404(Application, pk=request.POST.get('application_id'))
        new_status = request.POST.get('status', '')
        notes = request.POST.get('hr_notes', '').strip()
        allowed_statuses = dict(Application.STATUS_CHOICES)
        if new_status not in allowed_statuses:
            messages.error(request, 'Invalid application status.')
        else:
            application.status = new_status
            application.hr_notes = notes
            application.save(update_fields=['status', 'hr_notes'])
            if new_status in {'Selected', 'Hired'}:
                employee, created = convert_application_to_employee(application)
                if created:
                    messages.success(request, f'{employee.get_full_name()} is now an employee and a password setup email has been sent.')
                else:
                    messages.success(request, 'Applicant was already converted to an employee.')
            else:
                messages.success(request, 'Application updated.')
        return redirect('recruitment_dashboard')


@transaction.atomic
def convert_application_to_employee(application):
    """Create an employee profile and login only after a complete submitted application is hired."""
    if application.converted_employee_id:
        emp = application.converted_employee
        # Ensure any missing identifiers/pins are populated for legacy records
        changed = False
        if emp and not emp.employee_id:
            emp.employee_id = f'EMP-{emp.pk:05d}'
            changed = True
        if emp and not emp.attendance_pin:
            emp.attendance_pin = f'{secrets.randbelow(1000000):06d}'
            emp.pin = emp.attendance_pin
            changed = True
        if changed:
            emp.save(update_fields=['employee_id', 'attendance_pin', 'pin'])
            from hr.services.employee_service import send_employee_credentials
            send_employee_credentials(emp, emp.user.email, emp.attendance_pin)
            return emp, True
        return emp, False

    applicant = application.applicant

    # Prefer reusing an existing user with the applicant email to avoid duplicates
    user = User.objects.filter(email=applicant.email).first()
    if user is None:
        username_base = applicant.email.split('@')[0][:130] or 'employee'
        username = username_base
        counter = 1
        while User.objects.filter(username=username).exists():
            counter += 1
            username = f'{username_base[:140]}{counter}'
        user = User.objects.create_user(
            username=username, email=applicant.email, first_name=applicant.first_name,
            last_name=applicant.last_name,
        )
        user.set_unusable_password()
        user.save(update_fields=['password'])

    # If an Employee already exists for this user, link and return
    existing_emp = Employee.objects.filter(user=user).first()
    if existing_emp:
        # Complete legacy details from the application when an account already
        # exists. Gender controls maternity/paternity leave eligibility.
        changed = False
        if not existing_emp.gender and applicant.gender:
            existing_emp.gender = applicant.gender
            changed = True
        if not existing_emp.employee_id:
            existing_emp.employee_id = f'EMP-{existing_emp.pk:05d}'
            changed = True
        if not existing_emp.attendance_pin:
            existing_emp.attendance_pin = f'{secrets.randbelow(1000000):06d}'
            existing_emp.pin = existing_emp.attendance_pin
            changed = True
        if changed:
            existing_emp.save()
            from hr.services.employee_service import send_employee_credentials
            send_employee_credentials(existing_emp, applicant.email, existing_emp.attendance_pin)
            application.converted_employee = existing_emp
            application.save(update_fields=['converted_employee'])
            return existing_emp, True

        application.converted_employee = existing_emp
        application.save(update_fields=['converted_employee'])
        return existing_emp, False

    role, _ = Role.objects.get_or_create(name='Employee')
    active_status, _ = EmployeeStatus.objects.get_or_create(name='Active')

    # Create employee, handling potential race/unique constraint gracefully
    from django.db import IntegrityError
    try:
        employee = Employee.objects.create(
            user=user, role=role, status=active_status, department=application.job.department,
            first_name=applicant.first_name, middle_name=applicant.middle_name, last_name=applicant.last_name,
            gender=applicant.gender, marital_status=applicant.marital_status, phone=applicant.phone,
            emergency_contact=applicant.emergency_contact, fayda_id=applicant.fayda_id,
            qualification=applicant.qualification, field_of_study=applicant.field_of_study,
            institution=applicant.institution,
        )
    except IntegrityError:
        # Another process likely created the employee concurrently; reuse it if present
        employee = Employee.objects.filter(user=user).first()
        if employee is None:
            raise

    employee.employee_id = f'EMP-{employee.pk:05d}'
    employee.attendance_pin = f'{secrets.randbelow(1000000):06d}'
    employee.pin = employee.attendance_pin
    employee.save(update_fields=['employee_id', 'attendance_pin', 'pin'])

    from hr.services.employee_service import send_employee_credentials
    send_employee_credentials(employee, applicant.email, employee.attendance_pin)

    application.converted_employee = employee
    application.save(update_fields=['converted_employee'])
    return employee, True
