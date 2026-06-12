# hrms/services/settings_service.py
#
# Global settings read/write.
# All thresholds HR admins can change without touching code.

from hrms.models import SystemSetting


# ── defaults (used if key missing from DB) ────────────────────────────────────
DEFAULTS = [
    ('attendance', 'work_start_hour',         '8',   'Hour employees must clock in by (24h)'),
    ('attendance', 'late_grace_minutes',       '15',  'Minutes after start before marking Late'),
    ('attendance', 'required_days_per_month',  '20',  'Working days expected per month'),
    ('kpi',        'promotion_threshold',      '80',  'KPI score % needed for salary raise'),
    ('kpi',        'warning_threshold',        '50',  'KPI score % that triggers a warning'),
    ('kpi',        'excellent_threshold',      '90',  'KPI score % for excellent outcome'),
    ('kpi',        'satisfactory_threshold',   '60',  'KPI score % for satisfactory outcome'),
    ('kpi',        'probation_months',         '6',   'Probation period length in months'),
    ('kpi',        'excellent_raise_pct',      '10',  'Salary raise % for excellent outcome'),
    ('kpi',        'good_raise_pct',           '5',   'Salary raise % for good outcome'),
    ('recruitment','min_screening_pass',       '70',  'Qualification score % to pass auto-screening'),
    ('features',   'qr_attendance',            'true','Enable QR-based attendance'),
    ('features',   'chatbot',                  'true','Enable HR chatbot'),
    ('features',   'auto_payroll',             'false','Auto-generate payroll on month end'),
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


def save_settings(post_data: dict, user) -> None:
    """
    Updates every key that appears in post_data.
    post_data is flat: {'attendance__work_start_hour': '9', ...}
    Key format: category__key
    """
    for raw_key, value in post_data.items():
        if '__' not in raw_key:
            continue
        category, key = raw_key.split('__', 1)
        try:
            setting = SystemSetting.objects.get(category=category, key=key)
            setting.value      = value
            setting.updated_by = user
            setting.save(update_fields=['value', 'updated_by'])
        except SystemSetting.DoesNotExist:
            pass


def toggle_feature(feature_key: str, enabled: bool, user) -> None:
    """Toggle a feature flag on/off."""
    setting, _ = SystemSetting.objects.get_or_create(
        category='features', key=feature_key,
        defaults={'value': 'false', 'description': ''}
    )
    setting.value      = 'true' if enabled else 'false'
    setting.updated_by = user
    setting.save(update_fields=['value', 'updated_by'])