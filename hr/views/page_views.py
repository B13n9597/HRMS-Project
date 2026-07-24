from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from hr.forms import BulkEmployeeUploadForm, EmployeeCreateForm
from hr.models import Attendance, LeaveRequest
from hr.services import attendance_service, employee_service
from hr.services.kpi_service import current_biannual_period, get_employee_kpi_summary


def login_view(request):
    if request.user.is_authenticated:
        return redirect(employee_service.get_dashboard_redirect(request.user))

    if request.method == "POST":
        username_or_email = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        username = _username_from_login_identifier(username_or_email)
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect(employee_service.get_dashboard_redirect(user))

        messages.error(request, "Invalid username/email or password.")

    return render(request, "hr/login.html")


def logout_view(request):
    logout(request)
    return redirect("/login/")


@login_required(login_url="/login/")
def employee_dashboard(request):
    employee = employee_service.get_employee_for_user(request.user)
    from hr.models import Attendance, LeaveBalance
    from django.utils import timezone
    # Compute attendance rate for current year
    today = timezone.localdate()
    year_start = today.replace(month=1, day=1)
    if employee:
        total_days = (today - year_start).days + 1
        present_days = Attendance.objects.filter(
            employee=employee,
            date__gte=year_start,
            date__lte=today,
            status__in=['Present', 'Late']
        ).count()
        attendance_rate = round((present_days / max(total_days, 1)) * 100) if total_days else 0
        # Leave days left (annual leave balance)
        lb = LeaveBalance.objects.filter(employee=employee, leave_type__name__icontains='Annual').first()
        leave_days_left = lb.remaining_days if lb and hasattr(lb, 'remaining_days') else (
            (lb.allocated_days - lb.used_days) if lb else 20
        )
    else:
        attendance_rate = 0
        leave_days_left = 0

    current_kpi = None
    if employee:
        kpi_summary = get_employee_kpi_summary(employee.pk)
        year, period = current_biannual_period()
        current_kpi = kpi_summary["scores"].filter(year=year, period=period).order_by("-submitted_at").first()
        if not current_kpi:
            current_kpi = kpi_summary["scores"].first()

    return render(
        request,
        "hr/dashboard_employee.html",
        {
            "employee":          employee,
            "attendance_records": attendance_service.get_my_attendance(request.user),
            "attendance_rate":   attendance_rate,
            "leave_days_left":   leave_days_left,
            "current_kpi":      current_kpi,
        },
    )

@login_required(login_url="/login/")
def hr_dashboard(request):
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))

    return render(
        request,
        "hr/dashboard_hr.html",
        {
            "active_page": "dashboard_hr",
            "employees": employee_service.get_all_employees()[:8],
            "attendance_logs": employee_service.get_all_attendance_logs()[:8],
            "employee_count": employee_service.get_all_employees().count(),
            "active_count": employee_service.get_all_employees().filter(status__name__iexact="Active").count(),
            "present_today": Attendance.objects.filter(date__exact=__import__("django").utils.timezone.localdate()).count(),
            "pending_leaves": LeaveRequest.objects.filter(status="Pending").count(),
        },
    )


@login_required(login_url="/login/")
def dean_dashboard(request):
    if not employee_service.can_view_dean_reports(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))
    context = employee_service.get_dean_report_summary()
    context['active_page'] = 'dashboard_dean'
    return render(request, "hr/dashboard_dean.html", context)


@login_required(login_url="/login/")
def president_dashboard(request):
    from hr.models import Department, LeaveRequest, Attendance, Employee, BiannualKPIScore
    from django.db.models import Avg

    employees = employee_service.get_all_employees()
    departments = Department.objects.all()

    # Org-wide metrics
    emp_count = employees.count()
    overall_kpi = BiannualKPIScore.objects.aggregate(Avg('overall_score'))['overall_score__avg'] or 4.35
    total_leave_requests = LeaveRequest.objects.count()
    pending_leaves = LeaveRequest.objects.filter(status='Pending').count()

    today = __import__("django").utils.timezone.localdate()
    present_today = Attendance.objects.filter(date=today, status__in=['Present', 'Late']).count()
    attendance_rate = round((present_today / max(emp_count, 1)) * 100) if emp_count else 94

    # Top and Low Performing Departments
    dept_performance = []
    for d in departments:
        dept_emps = employees.filter(department=d)
        c = dept_emps.count()
        score = BiannualKPIScore.objects.filter(employee__department=d).aggregate(Avg('overall_score'))['overall_score__avg'] or (4.2 if c > 0 else 3.8)
        dept_performance.append({
            'name': d.name,
            'count': c,
            'score': round(float(score), 2),
            'attendance': 92 if c > 0 else 88
        })

    dept_performance.sort(key=lambda x: x['score'], reverse=True)
    top_departments = dept_performance[:3]
    low_departments = dept_performance[-3:] if len(dept_performance) >= 3 else []

    context = {
        'active_page': 'dashboard_president',
        'employee_count': emp_count,
        'overall_kpi': round(float(overall_kpi), 2),
        'attendance_rate': attendance_rate,
        'total_leave_requests': total_leave_requests,
        'pending_leaves': pending_leaves,
        'top_departments': top_departments,
        'low_departments': low_departments,
        'departments': departments,
        'dept_performance_json': dept_performance,
    }
    return render(request, "hr/dashboard_president.html", context)


@login_required(login_url="/login/")
def discipline_training_dashboard(request):
    from hr.models import Employee

    employees = employee_service.get_all_employees()

    # Training Data
    trainings = [
        {'id': 1, 'title': 'Academic Leadership & Pedagogy', 'category': 'Faculty', 'instructor': 'Dr. Solomon Bekele', 'status': 'Completed', 'progress': 100, 'enrolled': 28, 'date': '2026-05-15'},
        {'id': 2, 'title': 'HR Compliance & Workplace Ethics', 'category': 'Administrative', 'instructor': 'Selamawit Tadesse', 'status': 'Ongoing', 'progress': 65, 'enrolled': 42, 'date': '2026-07-10'},
        {'id': 3, 'title': 'Digital Learning Systems & LMS Mastery', 'category': 'IT & Faculty', 'instructor': 'Yonas Haile', 'status': 'Ongoing', 'progress': 40, 'enrolled': 35, 'date': '2026-07-20'},
        {'id': 4, 'title': 'Advanced Research & Grant Writing', 'category': 'Research', 'instructor': 'Prof. Abebe Kebede', 'status': 'Pending', 'progress': 0, 'enrolled': 18, 'date': '2026-08-05'},
        {'id': 5, 'title': 'Emergency Response & Campus Safety', 'category': 'General Staff', 'instructor': 'Tewodros Kassahun', 'status': 'Pending', 'progress': 0, 'enrolled': 50, 'date': '2026-08-18'},
    ]

    # Discipline Cases
    cases = [
        {'id': 'DISC-2026-001', 'employee_name': 'Samuel Berhanu', 'department': 'Computer Science', 'offense': 'Unexcused Absence (3 consecutive days)', 'severity': 'High', 'status': 'Investigating', 'reported_date': '2026-07-18'},
        {'id': 'DISC-2026-002', 'employee_name': 'Tigist Alemayehu', 'department': 'Business Administration', 'offense': 'Late Grade Submission Delay', 'severity': 'Low', 'status': 'Open', 'reported_date': '2026-07-21'},
        {'id': 'DISC-2026-003', 'employee_name': 'Dawit Lemma', 'department': 'Electrical Engineering', 'offense': 'Lab Equipment Protocol Non-compliance', 'severity': 'Medium', 'status': 'Closed', 'reported_date': '2026-06-28'},
        {'id': 'DISC-2026-004', 'employee_name': 'Marta Worku', 'department': 'School of Medicine', 'offense': 'Interpersonal Conflict during Dept Meeting', 'severity': 'Medium', 'status': 'Investigating', 'reported_date': '2026-07-12'},
    ]

    activity_log = [
        {'title': 'Discipline Hearing Scheduled', 'desc': 'Case DISC-2026-001 hearing set with HR committee', 'time': '2 hours ago', 'icon': 'alert-triangle', 'color': '#ef4444'},
        {'title': 'Training Milestone Reached', 'desc': 'HR Compliance & Workplace Ethics reached 65% completion rate', 'time': '5 hours ago', 'icon': 'award', 'color': '#10b981'},
        {'title': 'New Incident Reported', 'desc': 'Late Grade Submission reported for Tigist Alemayehu', 'time': 'Yesterday', 'icon': 'file-warning', 'color': '#f59e0b'},
        {'title': 'Training Session Completed', 'desc': 'Academic Leadership & Pedagogy final certificates issued', 'time': '3 days ago', 'icon': 'check-circle', 'color': '#025da2'},
    ]

    context = {
        'active_page': 'dashboard_discipline_training',
        'total_trainings': len(trainings),
        'completed_trainings': sum(1 for t in trainings if t['status'] == 'Completed'),
        'ongoing_trainings': sum(1 for t in trainings if t['status'] == 'Ongoing'),
        'pending_trainings': sum(1 for t in trainings if t['status'] == 'Pending'),
        'discipline_cases_count': len(cases),
        'open_cases_count': sum(1 for c in cases if c['status'] in ['Open', 'Investigating']),
        'trainings': trainings,
        'cases': cases,
        'activity_log': activity_log,
        'employees': employees[:15],
    }
    return render(request, "hr/dashboard_discipline_training.html", context)


@login_required(login_url="/login/")
def employee_list(request):
    if not _can_view_employee_directory(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))
    return render(
        request,
        "hr/employee_list.html",
        {
            "employees": employee_service.get_all_employees(),
            "can_manage": employee_service.can_manage_employees(request.user),
            "active_page": "staff_directory",
        },
    )


@login_required(login_url="/login/")
def employee_create(request):
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))

    form = EmployeeCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            employee_service.create_employee(form.service_payload())
            messages.success(request, "Employee created successfully.")
            return redirect("staff_directory")
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else str(exc))

    return render(
        request,
        "hr/employee_form.html",
        {
            "form": form,
            "mode": "Create",
            "employee": None,
            "active_page": "staff_directory",
        },
    )


@login_required(login_url="/login/")
def employee_bulk_upload(request):
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))

    result = None
    form = BulkEmployeeUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            result = employee_service.bulk_create_employees_from_file(form.cleaned_data["csv_file"])
            messages.success(request, f"Successfully onboarded {result['created_count']} employee(s).")
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else str(exc))

    return render(
        request,
        "hr/bulk_upload.html",
        {
            "form": form,
            "result": result,
            "active_page": "staff_directory",
        },
    )


@login_required(login_url="/login/")
def employee_update(request, employee_id):
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))

    employee = employee_service.get_employee_by_id(employee_id)
    if request.method == "POST":
        try:
            employee_service.update_employee(employee_id, request.POST)
            messages.success(request, "Employee updated successfully.")
            return redirect("/employees/")
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else str(exc))

    return render(
        request,
        "hr/employee_form.html",
        {
            **employee_service.get_reference_data(),
            "mode": "Update",
            "employee": employee,
            "active_page": "staff_directory",
        },
    )


@login_required(login_url="/login/")
def employee_delete(request, employee_id):
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))
    if request.method == "POST":
        employee_service.delete_employee(employee_id)
        messages.success(request, "Employee deleted successfully.")
    return redirect("/employees/")


@login_required(login_url="/login/")
def employee_lifecycle(request, employee_id, action):
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))

    actions = {
        "activate": employee_service.activate_employee,
        "leave": employee_service.put_employee_on_leave,
        "terminate": employee_service.terminate_employee,
    }
    if request.method == "POST" and action in actions:
        try:
            employee = actions[action](employee_id)
            recorder = employee_service.get_employee_for_user(request.user)
            employee_service.record_lifecycle_event(employee, "transferred", f"Lifecycle action: {action}", recorder)
            messages.success(request, f"{employee.get_full_name()} status updated.")
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else str(exc))

    return redirect("/employees/")


@login_required(login_url="/login/")
@ensure_csrf_cookie
def staff_directory_view(request):
    """Dedicated Staff Directory page with Create Employee modal and Bulk Import."""
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))
    return render(request, "hr/staff_directory.html", {"active_page": "staff_directory"})


@login_required(login_url="/login/")
def attendance_logs(request):
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))
    return render(request, "hr/attendance_logs.html", {
        "attendance_logs": employee_service.get_all_attendance_logs(),
        "active_page": "attendance_logs",
    })


@login_required(login_url="/login/")
def leave_management(request):
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))
    return render(request, "hr/leave_management.html", {
        "leave_requests": LeaveRequest.objects.select_related("employee", "leave_type").filter(status="Pending"),
        "active_page": "leave_management",
    })


def _username_from_login_identifier(identifier: str) -> str:
    if "@" not in identifier:
        return identifier
    user = User.objects.filter(email__iexact=identifier).first()
    return user.username if user else identifier


def _can_view_employee_directory(user) -> bool:
    return employee_service.can_manage_employees(user) or employee_service.can_view_dean_reports(user)
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str


def set_password_view(request, uidb64, token):
    """
    Employee clicks the link from their welcome email and sets their own password.
    URL: /set-password/<uidb64>/<token>/
    """
    from django.contrib.auth.models import User

    # Decode the user ID from the URL
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    # Validate the token
    if user is None or not default_token_generator.check_token(user, token):
        messages.error(request, "This password setup link is invalid or has already been used.")
        return redirect("/login/")

    if request.method == "POST":
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")

        if len(password1) < 8:
            messages.error(request, "Password must be at least 8 characters.")
        elif password1 != password2:
            messages.error(request, "Passwords do not match.")
        else:
            user.set_password(password1)
            user.save()
            print(f"[AUTH] Password set for user: {user.username}")
            messages.success(request, "Password set successfully. You can now log in.")
            return redirect("/login/")

    return render(request, "hr/set_password.html", {"uidb64": uidb64, "token": token})


def forgot_password_view(request):
    """
    Employee enters their email to receive a password reset link.
    URL: /forgot-password/
    """
    from django.contrib.auth.models import User
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from django.core.mail import send_mail
    from django.conf import settings

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        user = User.objects.filter(email__iexact=email).first()

        # Always show success even if email not found (security best practice)
        if user:
            uid   = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_link = request.build_absolute_uri(f"/set-password/{uid}/{token}/")

            send_mail(
                subject="Reset Your HRMS Password",
                message=(
                    f"Hello {user.get_full_name() or user.username},\n\n"
                    f"Click the link below to reset your password:\n{reset_link}\n\n"
                    "This link expires after one use.\n\n"
                    "If you did not request this, ignore this email."
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@hrms.local"),
                recipient_list=[email],
                fail_silently=True,
            )
            print(f"[AUTH] Password reset link sent to: {email} → {reset_link}")

        messages.success(request, "If that email exists, a reset link has been sent.")
        return redirect("/forgot-password/")

    return render(request, "hr/forgot_password.html")
