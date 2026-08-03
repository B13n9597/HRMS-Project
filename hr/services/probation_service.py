"""Probation reminders and automatic permanent-employment conversion."""
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from hr.models import Employee, EmployeeHistory, Notification


def _hr_users():
    return User.objects.filter(
        is_active=True,
    ).filter(
        # Staff and superusers are HR recipients even if they have no Employee profile.
        # Role-based HR users are included as well.
        Q(is_staff=True) | Q(is_superuser=True) | Q(employee__role__name__in=['HR', 'HR Manager', 'Admin'])
    ).distinct()


def run_probation_checks(today=None):
    """Notify HR on day 59 and convert probation staff on day 60; safe to run repeatedly."""
    today = today or timezone.localdate()
    notified = converted = 0
    for employee in Employee.objects.filter(is_deleted=False, hire_date__isnull=False).select_related('user'):
        days_worked = (today - employee.hire_date).days
        if days_worked == 59 and employee.employment_phase == 'Probation':
            message = f'Probation review due tomorrow: {employee.get_full_name()} completes 60 days on {today + timedelta(days=1)}.'
            for user in _hr_users():
                _, created = Notification.objects.get_or_create(user=user, message=message)
                notified += int(created)
        elif days_worked >= 60 and employee.employment_phase == 'Probation':
            employee.employment_phase = 'Permanent'
            employee.save(update_fields=['employment_phase'])
            EmployeeHistory.objects.get_or_create(
                employee=employee, event_type='probation_passed', start_date=today,
                defaults={
                    'department': employee.department, 'position': employee.position,
                    'old_value': 'Probation', 'new_value': 'Permanent',
                    'notes': 'Automatically converted to permanent employment after 60 days.',
                },
            )
            converted += 1
    return {'notified': notified, 'converted': converted}
