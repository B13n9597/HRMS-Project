from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from hr.views import api_views, page_views, supervisor_views, dashboard_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── Public / Auth ──────────────────────────────────────────────
    path('',        api_views.home_view,    name='home'),
    path('login/',  page_views.login_view,  name='login'),
    path('logout/', page_views.logout_view, name='logout'),

    # ── Kiosk ──────────────────────────────────────────────────────
    path('kiosk/',                    api_views.kiosk_view,          name='public_kiosk'),
    path('kiosk/api/employees/',      api_views.api_kiosk_employees, name='api_kiosk_employees'),
    path('kiosk/api/scan/',           api_views.api_kiosk_scan,      name='api_kiosk_scan'),
    path('tablet-kiosk/',             api_views.tablet_kiosk_view,   name='tablet_kiosk'),

    # ── Role Dashboards & Dedicated Routes ─────────────────────────
    path('dashboard/employee/',            page_views.employee_dashboard,            name='dashboard_employee'),
    path('dashboard/hr/',                  page_views.hr_dashboard,                  name='dashboard_hr'),
    
    # Dean Routes
    path('dean/dashboard/',                dashboard_views.dean_dashboard_view,      name='dean_dashboard'),
    path('dashboard/dean/',                dashboard_views.dean_dashboard_view,      name='dashboard_dean'),
    path('dean/export/attendance/',        dashboard_views.dean_export_attendance_csv, name='dean_export_attendance'),
    path('dean/export/leave/',             dashboard_views.dean_export_leave_csv,      name='dean_export_leave'),
    path('api/dean/leave/action/',         dashboard_views.dean_leave_action_api,      name='dean_leave_action_api'),

    # CEO / President Routes
    path('ceo/dashboard/',                dashboard_views.ceo_dashboard_view,                name='ceo_dashboard'),
    path('dashboard/president/',           dashboard_views.ceo_dashboard_view,                name='dashboard_president'),
    path('ceo/export/institution-report/', dashboard_views.ceo_export_institution_report_csv, name='ceo_export_institution_report'),
    path('ceo/export/audit-logs/',         dashboard_views.ceo_export_audit_logs_csv,         name='ceo_export_audit_logs'),

    # ── Dean JSON API Endpoints ────────────────────────────────────
    path('api/dean/attendance-summary/',       dashboard_views.api_dean_attendance_summary,      name='api_dean_attendance_summary'),
    path('api/dean/leave-requests/',           dashboard_views.api_dean_leave_requests,           name='api_dean_leave_requests'),

    # ── Dean Chart API Endpoints ───────────────────────────────────
    path('api/dean/charts/attendance-trend/',  dashboard_views.api_dean_chart_attendance_trend,   name='api_dean_chart_attendance_trend'),
    path('api/dean/charts/status-pie/',        dashboard_views.api_dean_chart_status_pie,         name='api_dean_chart_status_pie'),
    path('api/dean/charts/leave-overview/',    dashboard_views.api_dean_chart_leave_overview,     name='api_dean_chart_leave_overview'),
    path('api/dean/charts/kpi-scores/',        dashboard_views.api_dean_chart_kpi_scores,         name='api_dean_chart_kpi_scores'),
    path('api/dean/charts/late-trend/',        dashboard_views.api_dean_chart_late_trend,         name='api_dean_chart_late_trend'),

    # ── Dean Export ────────────────────────────────────────────────
    path('dean/export/report-pdf/',            dashboard_views.dean_export_pdf,                   name='dean_export_pdf'),

    # ── CEO JSON API Endpoints ─────────────────────────────────────
    path('api/ceo/analytics/attendance-trend/',       dashboard_views.api_ceo_attendance_trend,       name='api_ceo_attendance_trend'),
    path('api/ceo/analytics/department-performance/', dashboard_views.api_ceo_dept_performance,       name='api_ceo_dept_performance'),

    # ── CEO Chart API Endpoints ────────────────────────────────────
    path('api/ceo/charts/attendance-trend/',   dashboard_views.api_ceo_chart_attendance_trend,    name='api_ceo_chart_attendance_trend'),
    path('api/ceo/charts/dept-comparison/',    dashboard_views.api_ceo_chart_dept_comparison,     name='api_ceo_chart_dept_comparison'),
    path('api/ceo/charts/leave-distribution/', dashboard_views.api_ceo_chart_leave_distribution,  name='api_ceo_chart_leave_distribution'),
    path('api/ceo/charts/employee-performance/', dashboard_views.api_ceo_chart_emp_performance,   name='api_ceo_chart_emp_performance'),
    path('api/ceo/charts/monthly-summary/',    dashboard_views.api_ceo_chart_monthly_summary,     name='api_ceo_chart_monthly_summary'),

    # ── CEO Export ─────────────────────────────────────────────────
    path('ceo/export/report-pdf/',             dashboard_views.ceo_export_pdf,                    name='ceo_export_pdf'),

    path('dashboard/discipline-training/', page_views.discipline_training_dashboard, name='dashboard_discipline_training'),


    # ── Supervisor Dashboard (defined here to avoid prefix collision) ─
    path('dashboard/supervisor/',
         supervisor_views.supervisor_dashboard, name='supervisor_dashboard'),
    path('dashboard/supervisor/employees/',
         supervisor_views.supervisor_employees, name='supervisor_employees'),
    path('dashboard/supervisor/leave/',
         supervisor_views.supervisor_leave_approvals, name='supervisor_leave_approvals'),
    path('dashboard/supervisor/attendance/',
         supervisor_views.supervisor_attendance, name='supervisor_attendance'),
    path('dashboard/supervisor/kpi/',
         supervisor_views.supervisor_kpi, name='supervisor_kpi'),
    path('dashboard/supervisor/certificates/',
         supervisor_views.supervisor_certificates, name='supervisor_certificates'),
    path('dashboard/supervisor/training-requests/',
         supervisor_views.supervisor_training_requests, name='supervisor_training_requests'),
    path('dashboard/supervisor/discipline-reports/',
         supervisor_views.supervisor_discipline_reports, name='supervisor_discipline_reports'),
    path('dashboard/supervisor/hiring-request/',
         supervisor_views.supervisor_hiring_request, name='supervisor_hiring_request'),

    # ── Employee management (legacy form-based pages) ──────────────
    path('employees/',
         page_views.employee_list, name='employee_list'),
    path('employees/create/',
         page_views.employee_create, name='employee_create'),
    path('employees/<int:employee_id>/update/',
         page_views.employee_update, name='employee_update'),
    path('employees/<int:employee_id>/delete/',
         page_views.employee_delete, name='employee_delete'),
    path('employees/<int:employee_id>/<str:action>/',
         page_views.employee_lifecycle, name='employee_lifecycle'),

    # ── Password reset ────────────────────────────────────────────
    path('forgot-password/', page_views.forgot_password_view, name='forgot_password'),
    path('set-password/<uidb64>/<token>/',
         page_views.set_password_view, name='set_password'),

    # ── All other HR routes live under attendance/ prefix ─────────
    path('attendance/', include('hr.urls')),

    # ── Catch-all fallback for routes that don't need the prefix ──
    path('', include('hr.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )


