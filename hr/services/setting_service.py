# hr/services/setting_service.py
#
# Global settings read/write. All thresholds HR admins can change without code.

import holidays
from hr.models import SystemSetting

DEFAULTS = [
    # Attendance
    ('attendance', 'work_start_hour',        '8',     'Hour employees must clock in by (24h)'),
    ('attendance', 'late_grace_minutes',      '15',    'Minutes after start before marking Late'),
    ('attendance', 'required_days_per_month', '20',    'Working days expected per month'),

    # Leave policy
    ('leave', 'annual_leave_base_days',       '18',    'Annual leave starting days per year'),
    ('leave', 'annual_leave_max_days',        '30',    'Maximum annual leave days (cap)'),
    ('leave', 'annual_leave_increment',       '1',     'Days added per year of service'),
    ('leave', 'sick_leave_max_days',          '30',    'Maximum sick leave days'),
    ('leave', 'maternity_leave_days',         '90',    'Maternity leave days'),
    ('leave', 'paternity_leave_days',         '5',     'Paternity leave days'),
    ('leave', 'mourning_leave_days',          '3',     'Bereavement leave days'),
    ('leave', 'educational_leave_days',       '14',    'Educational/study leave days'),

    # Payroll
    ('payroll', 'pension_employee_pct',       '7',     'Employee pension contribution %'),
    ('payroll', 'pension_employer_pct',       '11',    'Employer pension contribution %'),
    ('payroll', 'currency',                   'ETB',   'Payroll currency'),

    # KPI
    ('kpi', 'promotion_threshold',            '80',    'KPI score % needed for salary raise'),
    ('kpi', 'warning_threshold',              '50',    'KPI score % that triggers a warning'),
    ('kpi', 'excellent_threshold',            '90',    'KPI score % for excellent outcome'),
    ('kpi', 'satisfactory_threshold',         '60',    'KPI score % for satisfactory outcome'),
    ('kpi', 'probation_months',               '6',     'Probation period length in months'),
    ('kpi', 'biannual_period',                'H1/H2', 'Evaluation periods: Jan-Jun (H1) and Jul-Dec (H2)'),

    # Recruitment
    ('recruitment', 'min_screening_pass',     '70',    'Score % to pass auto-screening'),

    # Features
    ('features', 'qr_attendance',             'true',  'Enable QR-based attendance'),
    ('features', 'chatbot',                   'true',  'Enable HR chatbot'),
    ('features', 'auto_payroll',              'false', 'Auto-generate payroll on month end'),
    ('features', 'ethiopian_calendar',        'true',  'Show Ethiopian calendar in leave forms'),

    # Role permissions
    ('permissions', 'supervisor_approve_leave', 'true',  'Allow supervisors to approve leave'),
    ('permissions', 'supervisor_view_kpi',      'true',  'Allow supervisors to view KPI scores'),
    ('permissions', 'supervisor_view_certs',    'true',  'Allow supervisors to view certificates'),
    ('permissions', 'dean_view_all_reports',    'true',  'Allow deans to view all department reports'),
]


def seed_defaults():
    """Call once on startup or migration to ensure all keys exist."""
    for cat, key, val, desc in DEFAULTS:
        SystemSetting.objects.get_or_create(
            category=cat, key=key,
            defaults={'value': val, 'description': desc}
        )


def get_all_settings() -> dict:
    """Returns all settings grouped by category as a nested dict."""
    seed_defaults()
    result = {}
    for s in SystemSetting.objects.all().order_by('category', 'key'):
        result.setdefault(s.category, {})[s.key] = {
            'value':       s.value,
            'description': s.description,
            'id':          s.pk,
        }
    return result


def get_settings_grouped_list() -> dict:
    """Returns settings grouped by category as lists (for template iteration)."""
    seed_defaults()
    result = {}
    for s in SystemSetting.objects.all().order_by('category', 'key'):
        s.display_label = (s.key or '').replace('_', ' ').title()
        result.setdefault(s.category, []).append(s)
    return result


def save_settings(post_data: dict, user) -> None:
    """
    Updates every key that appears in post_data.
    post_data key format: setting_category__key
    """
    for raw_key, value in post_data.items():
        if not raw_key.startswith('setting_'):
            continue
        inner = raw_key[len('setting_'):]
        if '__' not in inner:
            continue
        category, key = inner.split('__', 1)
        SystemSetting.objects.filter(category=category, key=key).update(
            value=value, updated_by=user
        )


def get_holiday_list():
    from django.utils import timezone
    from hr.models import Holiday

    seed_ethiopian_holidays(timezone.localdate().year)
    return Holiday.objects.all().order_by('date')


def seed_ethiopian_holidays(year: int):
    """Seed Ethiopian public holidays into the local Holiday table using the holidays package."""
    from hr.models import Holiday

    et_holidays = holidays.country_holidays('ET', years=[year], language='en')
    for holiday_date, name in et_holidays.items():
        Holiday.objects.get_or_create(date=holiday_date, defaults={'name': name, 'is_public': True})
