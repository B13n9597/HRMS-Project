from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from hr.services import attendance_service, employee_service


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
    return render(
        request,
        "hr/dashboard_employee.html",
        {
            "employee": employee,
            "attendance_records": attendance_service.get_my_attendance(request.user),
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
            "employees": employee_service.get_all_employees()[:8],
            "attendance_logs": employee_service.get_all_attendance_logs()[:8],
        },
    )


@login_required(login_url="/login/")
def dean_dashboard(request):
    if not employee_service.can_view_dean_reports(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))
    return render(request, "hr/dashboard_dean.html", employee_service.get_dean_report_summary())


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
        },
    )


@login_required(login_url="/login/")
def employee_create(request):
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))

    if request.method == "POST":
        try:
            employee_service.create_employee(request.POST)
            messages.success(request, "Employee created successfully.")
            return redirect("/employees/")
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else str(exc))

    return render(
        request,
        "hr/employee_form.html",
        {
            **employee_service.get_reference_data(),
            "mode": "Create",
            "employee": None,
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
    return render(request, "hr/staff_directory.html")


@login_required(login_url="/login/")
def attendance_logs(request):
    if not employee_service.can_manage_employees(request.user):
        return redirect(employee_service.get_dashboard_redirect(request.user))
    return render(request, "hr/attendance_logs.html", {"attendance_logs": employee_service.get_all_attendance_logs()})


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