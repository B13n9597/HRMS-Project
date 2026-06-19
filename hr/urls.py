from django.contrib import admin
from django.urls import path
from hr.views import api_views
from hr.views import page_views

# Standardized imports (adjust matching your file names if needed)
from hr.views import attendance_views as attendanceviews
from hr.views import employee_views

urlpatterns = [
    # ── Admin Panel ──────────────────────────────────────────────
    path('admin/', admin.site.urls),

    # ── Single Page Application Dashboard ──────────────────────────
    # Map root to the live attendance dashboard (explicit view)
    path('', attendanceviews.live_attendance, name='hrms_dashboard'),

    # ── Attendance Management (Web Layout Router) ────────────────
    path('my-qr/', attendanceviews.my_qr_code, name='attendance_my_qr'),
    path('scan/', attendanceviews.scan_qr_secure, name='attendance_scan'),
    path('today/', attendanceviews.today_attendance, name='attendance_today'),
    path('my-record/', attendanceviews.my_attendance, name='attendance_my_record'),
    path('report/<int:employee_id>/', attendanceviews.employee_attendance_report, name='attendance_report'),

    # ── Explicit sidebar routes (render full Django views)
    path('attendance-logs/', attendanceviews.attendance_logs, name='attendance_logs'),
    path('live-attendance/', attendanceviews.live_attendance, name='live_attendance'),
    path('staff-directory/', employee_views.staff_directory_view, name='staff_directory'),
    path('payroll-center/', api_views.index_view, name='payroll_center'),
    path('leave-approvals/', api_views.index_view, name='leave_approvals'),
    path('performance-kpis/', api_views.index_view, name='performance_kpis'),
    path('candidate-screen/', api_views.index_view, name='candidate_screen'),
    path('global-settings/', api_views.index_view, name='global_settings'),

    # ── Attendance APIs ──────────────────────────────────────────
    path('api/attendance/scan/', attendanceviews.scan_qr_secure, name='api_attendance_scan'),
    path('api/attendance/my-qr/', attendanceviews.my_qr_code, name='api_attendance_my_qr'),
    path('api/attendance/my-record/', attendanceviews.my_attendance, name='api_attendance_my_record'),
    path('api/attendance/today/', attendanceviews.today_attendance, name='api_attendance_today'),
    path('api/attendance/report/<int:employee_id>/', attendanceviews.employee_attendance_report, name='api_attendance_report'),

    # ── Employee APIs (Lifecycle: Recruitment to Retirement) ──────
    path('api/employees/create/', employee_views.create_employee, name='api_employee_create'),
    path('api/employees/update/<int:employee_id>/', employee_views.update_employee, name='api_employee_update'),
    path('api/employees/status/<int:employee_id>/', employee_views.change_employee_status, name='api_employee_status_change'),
    path('api/employees/active/', employee_views.list_active_employees, name='api_employee_list_active'),
    
    # ── Bulk Import endpoint ──────────────────────────────────────
    path('api/employees/import-bulk/', employee_views.import_employees_bulk, name='api_employee_import_bulk'),

    # ── Core SPA Frontend Endpoint Engines ───────────────────────
    path('api/me/', api_views.api_me, name='api_me'),
    path('api/login/', api_views.api_login, name='api_login'),
    path('api/logout/', api_views.api_logout, name='api_logout'),
    path('api/employees/', api_views.api_employees, name='api_employees'),
    path('api/lifecycle/', api_views.api_lifecycle, name='api_lifecycle'),
    path('api/leaves/', api_views.api_leaves, name='api_leaves'),
    path('api/admin/leaves/', api_views.api_admin_leaves, name='api_admin_leaves'),
    path('api/payroll/', api_views.api_payroll, name='api_payroll'),
    path('api/performance/', api_views.api_performance, name='api_performance'),
    path('api/recruitment/', api_views.api_recruitment, name='api_recruitment'),
    path('api/settings/', api_views.api_settings, name='api_settings'),
    path('api/simulate-scan/', api_views.api_simulate_scan, name='api_simulate_scan'),
    path('forgot-password/', page_views.forgot_password_view, name='forgot_password'),
    path('forgot_password/', page_views.forgot_password_view), 
    
    path('set-password/<uidb64>/<token>/', page_views.set_password_view, name='set_password'),
    # ── Bulk CSV Mass Onboarding & Tablet Attendance APIs ────────────────
    path('api/employees/upload-csv/', api_views.api_upload_employees_csv, name='api_employees_upload_csv'),
    path('api/attendance/tablet/authenticate/', api_views.api_tablet_authenticate, name='api_attendance_tablet_authenticate'),
    path('api/attendance/tablet/submit/', api_views.api_tablet_submit, name='api_attendance_tablet_submit'),

    # ── HR Form APIs ──────────────────────────────────────────────────────
    path('api/reference-data/', api_views.api_reference_data, name='api_reference_data'),
    path('api/employees/create-hr/', api_views.api_create_employee_hr, name='api_employees_create_hr'),

    # ── Tablet Kiosk View ─────────────────────────────────────────────────
    path('tablet-kiosk/', api_views.tablet_kiosk_view, name='tablet_kiosk_attendance'),
    
    path('api/employees/promote/<int:employee_id>/',employee_views.promote_employee,name='api_employee_promote'),

    path('api/employees/transfer/<int:employee_id>/',employee_views.transfer_employee,name='api_employee_transfer'),
]
