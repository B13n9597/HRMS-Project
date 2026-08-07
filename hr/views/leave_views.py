# hrms/views/leave_views.py
#
# EMPLOYEE:  employee_leave_manager  — request leave, view own history & balances
# HR:        hr_leave_manager        — read-only view of ALL employees' leaves
#            hr_leave_approvals      — approve / reject PENDING leaves only

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from hr.views.attendance_views import is_hr
from hr.services import leave_service
from hr.services.leave_service import sabbatical_eligibility
from hr.services import employee_service
from hr.models import Employee, LeaveRequest, LeaveType, LeaveBalance


# ─────────────────────────────────────────────────────────────
# EMPLOYEE SIDE
# ─────────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def employee_leave_manager(request):
    """
    Employee-only page:
     - Submit a leave request
     - View own leave history with status (Pending / Approved / Rejected)
     - View own leave balances (unused days per type)
    """
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        # If the logged-in user does not have an Employee profile, show
        # a friendly message but render the page so the employee portal
        # remains usable (prevents hard redirects from the dashboard).
        messages.error(request, "No employee profile found for your account. Contact HR to create one.")
        employee = None

    error_msg = None

    if request.method == 'POST':
        action = request.POST.get('action', 'submit')

        # Cancel a pending leave request
        if action == 'cancel' and employee:
            request_id = request.POST.get('request_id')
            if request_id:
                try:
                    leave_service.cancel_request(int(request_id), employee)
                    messages.success(request, "Leave request cancelled.")
                except ValidationError as exc:
                    messages.error(request, exc.message)
                except Exception as exc:
                    messages.error(request, str(exc))
            return redirect('employee_leave_manager')

        # Submit a new leave request
        leave_type_id             = request.POST.get('leave_type_id')
        start_date                = request.POST.get('start_date')
        end_date                  = request.POST.get('end_date')
        comments                  = request.POST.get('comments', '')
        contact_info_during_leave = request.POST.get('contact_info_during_leave', '').strip()

        if not leave_type_id or not start_date or not end_date:
            error_msg = "All fields are required."
        else:
            from datetime import date as date_cls
            try:
                s = date_cls.fromisoformat(start_date)
                e = date_cls.fromisoformat(end_date)
                if e < s:
                    error_msg = "End date cannot be before start date."
                else:
                    doc_file = request.FILES.get('document')
                    leave_service.submit_leave_request(employee.pk, {
                        'leave_type_id':             int(leave_type_id),
                        'start_date':                s,
                        'end_date':                  e,
                        'reason':                    comments,
                        'document':                  doc_file,
                        'contact_info_during_leave': contact_info_during_leave,
                    })
                    messages.success(request, "Leave request submitted successfully.")
                    return redirect('employee_leave_manager')
            except ValidationError as exc:
                error_msg = exc.message
            except Exception as exc:
                error_msg = str(exc)

    leave_types  = leave_service.get_all_leave_types() if employee else []
    my_requests = []
    my_balances  = []
    leave_type_options = []
    if employee:
        my_requests = leave_service.get_employee_requests(employee.pk)
        # Enrich balances with sabbatical eligibility info for UI
        balances_qs = leave_service.get_leave_balance(employee.pk)
        allowed_leave_ids = {lt.id for lt in leave_service.get_leave_types_for_employee(employee)}
        for lt in leave_types:
            name_key = lt.name.lower()
            gender_note = ''
            if 'maternity' in name_key:
                gender_note = 'Female only'
            elif 'paternity' in name_key:
                gender_note = 'Male only'
            leave_type_options.append({
                'id': lt.id,
                'name': lt.name,
                'max_days': lt.max_days,
                'description': lt.description,
                'eligible': lt.id in allowed_leave_ids,
                'gender_note': gender_note,
            })
        enriched = []
        seen_sabbatical = False  # track whether we have already added a sabbatical card
        for b in balances_qs:
            type_key = b.leave_type.name.lower().strip()
            is_sabbatical = 'sabbatical' in type_key

            # Deduplicate: if this is any sabbatical-type entry and we already
            # have one enriched with eligibility info, skip this one.
            if is_sabbatical and seen_sabbatical:
                continue

            info = {
                'leave_type_name': b.leave_type.name,
                'remaining_days': b.remaining_days,
                'allocated_days': getattr(b, 'allocated_days', None),
                'description': b.leave_type.description,
            }
            if is_sabbatical:
                elig = sabbatical_eligibility(employee)
                info['sabbatical_info'] = {
                    'eligible': elig['eligible'],
                    'years_completed': elig['years_completed'],
                    'years_until': elig['years_until'],
                    'eligible_date': elig['eligible_date'].isoformat() if elig['eligible_date'] else None,
                }
                seen_sabbatical = True
            enriched.append(info)
        my_balances = enriched

    # Build status-coloured badge map
    status_badge = {
        'Pending':  'badge-warning',
        'Approved': 'badge-success',
        'Rejected': 'badge-danger',
    }

    context = {
        'employee':        employee,
        'leave_types':     leave_types,
        'leave_type_options': leave_type_options,
        'my_requests':     my_requests,
        'my_balances':     my_balances,
        'status_badge':    status_badge,
        'error_msg':       error_msg,
        'active_page':     'employee_leave_manager',
        'today':           timezone.localdate().isoformat(),
        'base_template':   employee_service.get_base_template(request.user),
    }
    return render(request, 'hr/employee_leave_manager.html', context)


# ─────────────────────────────────────────────────────────────
# HR SIDE — Leave Manager (read-only overview)
# ─────────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def hr_leave_manager(request):
    """
    HR-only page: read-only summary of ALL employee leave records.
    Filter by status, department, leave type.
    """
    if not is_hr(request.user):
        messages.error(request, "Access denied.")
        return redirect('/')

    from hr.models import Department

    status_f    = request.GET.get('status', '')
    dept_id     = request.GET.get('department_id', '')
    leave_type_f = request.GET.get('leave_type_id', '')
    query       = request.GET.get('q', '').strip()

    records = leave_service.get_all_requests()
    if status_f:
        records = records.filter(status=status_f)
    if dept_id:
        records = records.filter(employee__department_id=dept_id)
    if leave_type_f:
        records = records.filter(leave_type_id=leave_type_f)
    from django.db.models import Q
    if query:
        records = records.filter(Q(employee__first_name__icontains=query) | Q(employee__last_name__icontains=query))

    departments = Department.objects.all()
    leave_types = leave_service.get_all_leave_types()

    # Summary counts
    total    = records.count()
    pending  = records.filter(status='Pending').count()
    approved = records.filter(status='Approved').count()
    rejected = records.filter(status='Rejected').count()

    context = {
        'records':      records,
        'departments':  departments,
        'leave_types':  leave_types,
        'status_f':     status_f,
        'dept_id':      dept_id,
        'leave_type_f': leave_type_f,
        'search_query': query,
        'total':        total,
        'pending':      pending,
        'approved':     approved,
        'rejected':     rejected,
        'active_page':  'hr_leave_manager',
    }
    return render(request, 'hr/hr_leave_manager.html', context)


# ─────────────────────────────────────────────────────────────
# HR SIDE — Leave Approvals (pending only + approve/reject)
# ─────────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def hr_leave_approvals(request):
    """
    HR-only page: shows ONLY pending leave requests.
    HR can approve or reject each with an optional note.
    """
    if not is_hr(request.user):
        messages.error(request, "Access denied.")
        return redirect('/')

    try:
        hr_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        hr_employee = None

    if request.method == 'POST':
        action     = request.POST.get('action')   # 'approve' | 'reject'
        request_id = request.POST.get('request_id')
        note       = request.POST.get('note', '')

        if hr_employee and request_id:
            try:
                if action == 'approve':
                    leave_service.approve_request(int(request_id), hr_employee)
                    messages.success(request, "Leave request approved.")
                elif action == 'reject':
                    leave_service.reject_request(int(request_id), hr_employee, note)
                    messages.warning(request, "Leave request rejected.")
            except ValidationError as exc:
                messages.error(request, exc.message)
            except Exception as exc:
                messages.error(request, str(exc))

        return redirect('hr_leave_approvals')

    pending_requests = leave_service.get_pending_requests()
    context = {
        'leave_requests': pending_requests,
        'hr_employee':    hr_employee,
        'active_page':    'hr_leave_approvals',
        'current_year':   timezone.localdate().year,
        'recommendation_labels': {
            '':                'Awaiting Supervisor',
            'recommended':     'Recommended',
            'not_recommended': 'Not Recommended',
        },
    }
    return render(request, 'hr/hr_leave_approvals.html', context)


# ─────────────────────────────────────────────────────────────
# LEGACY COMPATIBILITY — keep old URL names working
# ─────────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def leave_approvals_view(request):
    """Redirect old 'leave_approvals' URL to the correct HR approvals page."""
    return redirect('hr_leave_approvals')


@login_required(login_url='/login/')
def request_leave(request):
    """Redirect old request-leave URL to the employee leave manager."""
    return redirect('employee_leave_manager')


@login_required(login_url='/login/')
def cancel_leave_view(request, request_id):
    """Employee cancels their own pending leave request."""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "No employee profile found.")
        return redirect('employee_leave_manager')

    if request.method == 'POST':
        try:
            leave_service.cancel_request(request_id, employee)
            messages.success(request, "Leave request cancelled.")
        except Exception as exc:
            messages.error(request, str(exc))
    return redirect('employee_leave_manager')


@login_required(login_url='/login/')
def leave_reports(request):
    """HR leave reports — summary by type, department, status."""
    if not is_hr(request.user):
        messages.error(request, "Access denied.")
        return redirect('/')

    from hr.models import Department
    from django.db.models import Count

    year = int(request.GET.get('year', timezone.localdate().year))

    all_requests = leave_service.get_all_requests().filter(start_date__year=year)

    # Summary by leave type
    by_type = (
        all_requests
        .values('leave_type__name')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    # Summary by status
    by_status = (
        all_requests
        .values('status')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    # Summary by department
    by_dept = (
        all_requests
        .values('employee__department__name')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    context = {
        'year':       year,
        'years':      [2024, 2025, 2026],
        'by_type':    list(by_type),
        'by_status':  list(by_status),
        'by_dept':    list(by_dept),
        'total':      all_requests.count(),
        'approved':   all_requests.filter(status='Approved').count(),
        'pending':    all_requests.filter(status='Pending').count(),
        'rejected':   all_requests.filter(status='Rejected').count(),
        'cancelled':  all_requests.filter(status='Cancelled').count(),
        'active_page': 'leave_reports',
    }
    return render(request, 'hr/leave_reports.html', context)
