# hr/views/employee_views.py

import csv
import io
import json

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import render
from rest_framework.decorators import api_view

from hr.services import employee_service
from hr.models import Employee


# ─────────────────────────────────────────────
# RESPONSE HELPERS
# ─────────────────────────────────────────────

def ok(data, status=200):
    return JsonResponse({'success': True, 'data': data, 'error': None}, status=status)


def err(message, status=400):
    return JsonResponse({'success': False, 'data': None, 'error': message}, status=status)


def _is_hr(user):
    return user.is_staff or user.is_superuser


# ─────────────────────────────────────────────
# CREATE EMPLOYEE (HR ONLY)
# ─────────────────────────────────────────────

@api_view(['POST'])
@login_required
def create_employee(request):
    if not _is_hr(request.user):
        return err("Unauthorized", 403)

    try:
        employee = employee_service.create_employee(request.data)

        return ok({
            "id": employee.id,
            "name": employee.get_full_name(),
            "employee_id": employee.employee_id,
            "status": employee.status.name if employee.status else None,
        }, 201)

    except ValidationError as e:
        return err(str(e), 400)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return err(str(e), 500)


# ─────────────────────────────────────────────
# UPDATE EMPLOYEE
# ─────────────────────────────────────────────

@api_view(['PUT'])
@login_required
def update_employee(request, employee_id):
    if not _is_hr(request.user):
        return err("Unauthorized", 403)

    try:
        employee = employee_service.update_employee_details(employee_id, request.data)

        return ok({
            "id": employee.id,
            "name": employee.get_full_name(),
        })

    except ValidationError as e:
        return err(str(e), 400)

    except Exception:
        return err("Internal server error", 500)


# ─────────────────────────────────────────────
# CHANGE STATUS
# ─────────────────────────────────────────────

@api_view(['POST'])
@login_required
def change_employee_status(request, employee_id):
    if not _is_hr(request.user):
        return err("Unauthorized", 403)

    # Accept both 'status' (raw name) and 'action' (activate/terminate shorthand)
    action     = request.data.get("action", "")
    new_status = request.data.get("status", "")

    if action == "activate":
        new_status = "active"
    elif action == "terminate":
        new_status = "terminated"

    if not new_status:
        return err("Provide 'status' or 'action' field.", 400)

    try:
        employee = employee_service.transition_employee_status(employee_id, new_status)
        # Record lifecycle event
        recorder = employee_service.get_employee_for_user(request.user)
        employee_service.record_lifecycle_event(
            employee, action if action else "transferred",
            f"Status changed to {new_status}", recorder
        )
        return ok({
            "id": employee.id,
            "new_status": employee.status.name if employee.status else None
        })

    except ValidationError as e:
        return err(str(e), 400)

    except Exception:
        return err("Internal server error", 500)


# ─────────────────────────────────────────────
# GET EMPLOYEES
# ─────────────────────────────────────────────

@login_required
def list_active_employees(request):
    if not _is_hr(request.user):
        return err("Unauthorized", 403)

    try:
        employees = employee_service.get_all_active_employees()

        data = [
            {
                "id": e.id,
                "name": e.get_full_name(),
                "department": e.department.name if e.department else 'N/A',
                "position": e.position.title if e.position else 'N/A',
                "status": e.status.name if e.status else 'Active',
                "hire_date": e.hire_date.strftime('%Y-%m-%d') if e.hire_date else '',
            }
            for e in employees
        ]

        return ok(data)

    except Exception:
        return err("Internal server error", 500)
    
    
    
@api_view(['POST'])
@login_required
def promote_employee(request, employee_id):

    if not _is_hr(request.user):
        return err("Unauthorized", 403)

    try:
        recorder = employee_service.get_employee_for_user(
            request.user
        )

        employee = employee_service.promote_employee(
            employee_id,
            request.data.get("position_id"),
            recorder
        )

        return ok({
            "id": employee.id,
            "name": employee.get_full_name()
        })

    except Exception as e:
        return err(str(e))
    
@api_view(['POST'])
@login_required
def transfer_employee(request, employee_id):

    if not _is_hr(request.user):
        return err("Unauthorized", 403)

    try:
        recorder = employee_service.get_employee_for_user(
            request.user
        )

        employee = employee_service.transfer_employee(
            employee_id,
            request.data.get("department_id"),
            recorder
        )

        return ok({
            "id": employee.id,
            "name": employee.get_full_name()
        })

    except Exception as e:
        return err(str(e))


# ─────────────────────────────────────────────
# BULK IMPORT EMPLOYEES  (CSV / XLSX)
# POST /attendance/api/employees/import-bulk/
# ─────────────────────────────────────────────

@login_required
def import_employees_bulk(request):
    """
    Accepts a multipart POST with a file field named 'csv_file'.
    Supported formats: .csv, .xlsx

    Required columns : username, email, first_name, last_name
    Optional columns : phone, department, position, role, hire_date,
                       base_salary, attendance_pin

    For each row the function:
      1. Parses employee attributes.
      2. Looks up or defaults Department / Position / Role instances.
      3. Creates a Django User account.
      4. Saves a new Employee record.
      5. Optionally saves an initial Salary record if base_salary is provided.
      6. Returns a JSON success / error report.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed.'}, status=405)

    if not (_is_hr(request.user) or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    uploaded_file = request.FILES.get('csv_file')
    if not uploaded_file:
        return JsonResponse({'success': False, 'error': 'No file uploaded. Use field name "csv_file".'}, status=400)

    from django.core.exceptions import ValidationError as DjangoValidationError
    from hr.services.employee_service import bulk_create_employees_from_file

    try:
        result = bulk_create_employees_from_file(uploaded_file)
    except DjangoValidationError as exc:
        return JsonResponse(
            {'success': False, 'error': str(exc.message if hasattr(exc, 'message') else exc)},
            status=400,
        )
    except Exception as exc:
        return JsonResponse(
            {'success': False, 'error': f'Failed to process file: {str(exc)}'},
            status=500,
        )

    return JsonResponse({
        'success': True,
        'message': f"Successfully onboarded {result['created_count']} employee(s).",
        'created_count': result['created_count'],
        'created': result['created'],
        'errors': result['errors'],
    })
    


@login_required
def staff_directory_view(request):
    """Render staff directory page — all employees, full DB dataset."""
    from hr.models import Department
    query   = request.GET.get('q', '').strip()
    dept_id = request.GET.get('department_id', '')
    status  = request.GET.get('status', '')

    employees = Employee.objects.select_related(
        'department', 'position', 'status', 'role'
    ).order_by('last_name', 'first_name')

    if query:
        from django.db.models import Q
        employees = employees.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) |
            Q(employee_id__icontains=query) | Q(user__email__icontains=query)
        )
    if dept_id:
        employees = employees.filter(department_id=dept_id)
    if status:
        employees = employees.filter(status__name__iexact=status)

    departments = Department.objects.all().order_by('name')
    context = {
        'employees':    employees,
        'departments':  departments,
        'search_query': query,
        'dept_id':      dept_id,
        'status_f':     status,
        'statuses':     ['Active', 'On Leave', 'Terminated'],
        'active_page':  'staff_directory',
    }
    return render(request, 'hr/staff_directory.html', context)


