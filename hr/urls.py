from django.urls import path

# Import the specific views file from your new views folder
from hr.views import attendance_views

urlpatterns = [

    # ── Employee: get own QR code image ──────────────────────────
    # GET  /attendance/my-qr/
    # Returns a PNG image the employee screenshots or prints.
    path('my-qr/', attendance_views.my_qr_code, name='attendance_my_qr'),

    # ── Scanner kiosk: receive QR scan ───────────────────────────
    # POST /attendance/scan/
    # Body: { "token": "<uuid_or_signed_string>" }
    # Pointed to the new, hardened security view function: scan_qr_secure
    path('scan/', attendance_views.scan_qr_secure, name='attendance_scan'),

    # ── HR / dept head: today's full attendance list ──────────────
    # GET  /attendance/today/
    path('today/', attendance_views.today_attendance, name='attendance_today'),

    # ── Employee: own attendance history ─────────────────────────
    # GET  /attendance/my-record/?month=5&year=2026
    path('my-record/', attendance_views.my_attendance, name='attendance_my_record'),

    # ── HR: one employee's attendance report ─────────────────────
    # GET  /attendance/report/12/?month=5&year=2026
    path('report/<int:employee_id>/', attendance_views.employee_attendance_report, name='attendance_report'),

]