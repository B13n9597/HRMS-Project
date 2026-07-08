from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from hr.views import api_views, page_views, supervisor_views

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

    # ── Role Dashboards ────────────────────────────────────────────
    path('dashboard/employee/', page_views.employee_dashboard, name='dashboard_employee'),
    path('dashboard/hr/',       page_views.hr_dashboard,       name='dashboard_hr'),
    path('dashboard/dean/',     page_views.dean_dashboard,     name='dashboard_dean'),

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
