"""
URL configuration for humanresource project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from hr.views import api_views
from hr.views import page_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('attendance/', include('hr.urls')),
    path('', api_views.home_view, name='home'),
    path('login/', page_views.login_view, name='login'),
    path('logout/', page_views.logout_view, name='logout'),
    path('kiosk/', api_views.kiosk_view, name='public_kiosk'),
    path('kiosk/api/employees/', api_views.api_kiosk_employees, name='api_kiosk_employees'),
    path('kiosk/api/scan/', api_views.api_kiosk_scan, name='api_kiosk_scan'),
    path('tablet-kiosk/', api_views.tablet_kiosk_view, name='tablet_kiosk'),

    path('dashboard/employee/', page_views.employee_dashboard, name='dashboard_employee'),
    path('dashboard/hr/', page_views.hr_dashboard, name='dashboard_hr'),
    path('dashboard/dean/', page_views.dean_dashboard, name='dashboard_dean'),

    path('employees/', page_views.employee_list, name='employee_list'),
    path('employees/create/', page_views.employee_create, name='employee_create'),
    path('employees/<int:employee_id>/update/', page_views.employee_update, name='employee_update'),
    path('employees/<int:employee_id>/delete/', page_views.employee_delete, name='employee_delete'),
    path('employees/<int:employee_id>/<str:action>/', page_views.employee_lifecycle, name='employee_lifecycle'),
    path('attendance-logs/', page_views.attendance_logs, name='attendance_logs'),

    # ── Named sidebar routes for SPA panel navigation ─────────────────────
    # These all render the SPA index.html (handled by JS panel switching)
    # but give Django's {% url %} tag real, resolvable route names.
    path('live-attendance/', api_views.index_view, name='live_attendance'),
    path('staff-directory/', page_views.staff_directory_view, name='staff_directory'),
    path('payroll-center/', api_views.index_view, name='payroll_center'),
    path('leave-approvals/', api_views.index_view, name='leave_approvals'),
    path('performance-kpis/', api_views.index_view, name='performance_kpis'),
    path('candidate-screen/', api_views.index_view, name='candidate_screen'),
    path('global-settings/', api_views.index_view, name='global_settings'),

    path('forgot-password/', page_views.forgot_password_view, name='forgot_password'),
    path('set-password/<uidb64>/<token>/', page_views.set_password_view, name='set_password'),
    
    path('', include('hr.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
