from django.urls import path
from hr.views import api_views, leave_views, page_views
from hr.views import attendance_views as attendanceviews
from hr.views import employee_views, lifecycle_views, hr_modules_views, finance_views

urlpatterns = [
    # ── Root ───────────────────────────────────────────────────────
    path('', attendanceviews.live_attendance, name='hrms_dashboard'),

    # ── Attendance — HR pages ──────────────────────────────────────
    path('attendance-logs/',  attendanceviews.attendance_logs, name='attendance_logs'),
    path('live-attendance/',  attendanceviews.live_attendance, name='live_attendance'),

    # ── Attendance — Employee pages ────────────────────────────────
    path('my-attendance/',     attendanceviews.my_attendance,    name='my_attendance_record'),
    path('manual-attendance/', attendanceviews.manual_attendance, name='manual_attendance'),

    # ── Attendance — misc ──────────────────────────────────────────
    path('my-qr/',                         attendanceviews.my_qr_code,                  name='attendance_my_qr'),
    path('scan/',                          attendanceviews.scan_qr_secure,              name='attendance_scan'),
    path('today/',                         attendanceviews.today_attendance,            name='attendance_today'),
    path('report/<int:employee_id>/',      attendanceviews.employee_attendance_report,  name='attendance_report'),

    # ── Leave — Employee ───────────────────────────────────────────
    path('leave/my/',         leave_views.employee_leave_manager, name='employee_leave_manager'),
    path('leave/cancel/<int:request_id>/', leave_views.cancel_leave_view, name='cancel_leave'),

    # ── Leave — HR ────────────────────────────────────────────────
    path('leave/all/',        leave_views.hr_leave_manager,   name='hr_leave_manager'),
    path('leave/approvals/',  leave_views.hr_leave_approvals, name='hr_leave_approvals'),
    path('leave/reports/',    leave_views.leave_reports,       name='leave_reports'),

    # ── Legacy leave URLs ─────────────────────────────────────────
    path('dashboard/hr/leaves/',        leave_views.leave_approvals_view, name='leave_approvals'),
    path('dashboard/hr/request-leave/', leave_views.request_leave,        name='request_leave'),

    # ── HR modules ────────────────────────────────────────────────
    path('staff-directory/',                   employee_views.staff_directory_view, name='staff_directory'),
    path('employee-lifecycle/',                lifecycle_views.hr_lifecycle,        name='hr_lifecycle'),
    path('employee-details/<int:id>/',         lifecycle_views.employee_details,    name='employee_details'),
    path('my-lifecycle/',                      lifecycle_views.my_lifecycle,        name='my_lifecycle'),
    path('payroll-center/',                    hr_modules_views.payroll_center,     name='payroll_center'),
    path('finance/',                           finance_views.finance_dashboard,     name='finance_dashboard'),
    path('my-salary-slips/',                   hr_modules_views.my_salary_slips,    name='my_salary_slips'),
    path('performance-kpis/',                  hr_modules_views.performance_kpis,   name='performance_kpis'),
    path('my-kpi/',                            hr_modules_views.my_kpi,             name='my_kpi'),
    path('my-training/',                       hr_modules_views.my_training_view,   name='my_training'),
    path('my-grievances/',                     hr_modules_views.my_grievances_view, name='my_grievances'),
    path('candidate-screen/',                  hr_modules_views.candidate_screen,   name='candidate_screen'),
    path('global-settings/',                   hr_modules_views.global_settings,    name='global_settings'),
    path('departments/',                       hr_modules_views.departments_view,   name='departments'),
    path('training/',                          hr_modules_views.training_view,      name='training'),
    path('career-development/',                hr_modules_views.career_development_view, name='career_development'),
    path('hr-discipline-cases/',               hr_modules_views.hr_discipline_cases, name='hr_discipline_cases'),
    path('hr-grievances/',                     hr_modules_views.hr_grievances,      name='hr_grievances'),
    path('hr-reports/',                        hr_modules_views.hr_reports_view,    name='hr_reports'),
    path('roles-permissions/',                 hr_modules_views.roles_permissions_view, name='roles_permissions'),

    # ── Attendance APIs ────────────────────────────────────────────
    path('api/attendance/scan/',                         attendanceviews.scan_qr_secure,              name='api_attendance_scan'),
    path('api/attendance/my-qr/',                        attendanceviews.my_qr_code,                  name='api_attendance_my_qr'),
    path('api/attendance/my-record/',                    attendanceviews.my_attendance,               name='api_attendance_my_record'),
    path('api/attendance/today/',                        attendanceviews.today_attendance,            name='api_attendance_today'),
    path('api/attendance/report/<int:employee_id>/',     attendanceviews.employee_attendance_report,  name='api_attendance_report'),

    # ── Employee APIs ──────────────────────────────────────────────
    path('api/employees/create/',                        employee_views.create_employee,        name='api_employee_create'),
    path('api/employees/update/<int:employee_id>/',      employee_views.update_employee,        name='api_employee_update'),
    path('api/employees/status/<int:employee_id>/',      employee_views.change_employee_status, name='api_employee_status_change'),
    path('api/employees/active/',                        employee_views.list_active_employees,  name='api_employee_list_active'),
    path('api/employees/import-bulk/',                   employee_views.import_employees_bulk,  name='api_employee_import_bulk'),
    path('api/employees/promote/<int:employee_id>/',     employee_views.promote_employee,       name='api_employee_promote'),
    path('api/employees/transfer/<int:employee_id>/',    employee_views.transfer_employee,      name='api_employee_transfer'),

    # ── Core SPA APIs ─────────────────────────────────────────────
    path('api/me/',            api_views.api_me,          name='api_me'),
    path('api/login/',         api_views.api_login,       name='api_login'),
    path('api/logout/',        api_views.api_logout,      name='api_logout'),
    path('api/employees/',     api_views.api_employees,   name='api_employees'),
    path('api/lifecycle/',     api_views.api_lifecycle,   name='api_lifecycle'),
    path('api/leaves/',        api_views.api_leaves,      name='api_leaves'),
    path('api/leaves/cancel/<int:request_id>/', api_views.api_cancel_leave, name='api_cancel_leave'),
    path('api/admin/leaves/',  api_views.api_admin_leaves, name='api_admin_leaves'),
    path('api/payroll/',       api_views.api_payroll,     name='api_payroll'),
    path('api/performance/',   api_views.api_performance, name='api_performance'),
    path('api/recruitment/',   api_views.api_recruitment, name='api_recruitment'),
    path('api/settings/',      api_views.api_settings,    name='api_settings'),
    path('api/simulate-scan/', api_views.api_simulate_scan, name='api_simulate_scan'),

    # ── Auth pages ────────────────────────────────────────────────
    path('forgot-password/',                   page_views.forgot_password_view, name='forgot_password'),
    path('forgot_password/',                   page_views.forgot_password_view),
    path('set-password/<uidb64>/<token>/',     page_views.set_password_view,    name='set_password'),

    # ── Bulk / Tablet ─────────────────────────────────────────────
    path('api/employees/upload-csv/',                   api_views.api_upload_employees_csv,      name='api_employees_upload_csv'),
    path('api/attendance/tablet/authenticate/',         api_views.api_tablet_authenticate,       name='api_attendance_tablet_authenticate'),
    path('api/attendance/tablet/submit/',               api_views.api_tablet_submit,             name='api_attendance_tablet_submit'),

    # ── HR Form APIs ──────────────────────────────────────────────
    path('api/reference-data/',        api_views.api_reference_data,    name='api_reference_data'),
    path('api/employees/create-hr/',   api_views.api_create_employee_hr, name='api_employees_create_hr'),

    # ── Tablet Kiosk ──────────────────────────────────────────────
    path('tablet-kiosk/', api_views.tablet_kiosk_view, name='tablet_kiosk_attendance'),
]
