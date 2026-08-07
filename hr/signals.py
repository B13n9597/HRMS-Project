"""
hr/signals.py
=============
All Django signals that auto-write EmployeeHistory lifecycle events.

Sources of events:
  User.post_save     → create Employee profile
  Employee.post_save → write 'hired' event on first creation
  Application.post_save → recruitment pipeline events
  Employee.pre_save  → detect employment_phase / status changes
  TrainingRequest.post_save → training_assigned / training_completed
  BiannualKPIScore.post_save → performance_review
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone


# ---------------------------------------------------------------------------
# 1. User → Employee profile auto-creation
# ---------------------------------------------------------------------------

@receiver(post_save, sender=User)
def create_employee_on_user_create(sender, instance, created, **kwargs):
    """Creates a blank Employee profile the moment a new User is saved."""
    if not created:
        return
    from .models import Employee
    Employee.objects.get_or_create(
        user=instance,
        defaults={
            'first_name': instance.first_name or '',
            'last_name':  instance.last_name  or '',
            'phone':      '',
            'address':    '',
            'hire_date':  timezone.localdate(),
        }
    )


# ---------------------------------------------------------------------------
# 2. Employee.post_save → 'hired' (Employee Created) event
# ---------------------------------------------------------------------------

@receiver(post_save, sender='hr.Employee')
def create_hired_lifecycle_event(sender, instance, created, **kwargs):
    """Auto-creates 'Employee Created' event so the timeline is never empty."""
    if not created:
        return
    from .models import EmployeeHistory
    if EmployeeHistory.objects.filter(employee=instance).exists():
        return
    from django.utils.timezone import localtime
    EmployeeHistory.objects.create(
        employee   = instance,
        department = instance.department,
        position   = instance.position,
        event_type = 'hired',
        new_value  = instance.status.name if instance.status else 'Active',
        notes      = 'Employee record created.',
        start_date = instance.hire_date or timezone.localdate(),
        event_time = localtime(timezone.now()).time(),
    )


# ---------------------------------------------------------------------------
# 3. Employee.pre_save → detect employment_phase & status transitions
# ---------------------------------------------------------------------------

@receiver(pre_save, sender='hr.Employee')
def _store_employee_prev_state(sender, instance, **kwargs):
    """Stash old employment_phase and status so post_save can compare."""
    if not instance.pk:
        instance._prev_phase  = None
        instance._prev_status = None
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        instance._prev_phase  = old.employment_phase
        instance._prev_status = old.status_id
    except sender.DoesNotExist:
        instance._prev_phase  = None
        instance._prev_status = None


@receiver(post_save, sender='hr.Employee')
def track_employee_phase_change(sender, instance, created, **kwargs):
    """
    Fires lifecycle events when employment_phase or status changes:
      Probation  → Permanent    : probation_passed + confirmed_permanent
      Active     → Terminated   : terminated
      Active     → On Leave     : (not a lifecycle milestone — skip)
      Terminated → Active       : reinstated
    """
    if created:
        return

    from .models import EmployeeHistory
    from django.utils.timezone import localtime

    def _write(event_type, notes='', old_val='', new_val=''):
        EmployeeHistory.objects.create(
            employee   = instance,
            department = instance.department,
            position   = instance.position,
            event_type = event_type,
            old_value  = old_val,
            new_value  = new_val,
            notes      = notes,
            start_date = timezone.localdate(),
            event_time = localtime(timezone.now()).time(),
        )

    prev_phase  = getattr(instance, '_prev_phase', None)
    prev_status = getattr(instance, '_prev_status', None)

    # Probation → Permanent
    if prev_phase == 'Probation' and instance.employment_phase == 'Permanent':
        _write('probation_passed',      'Probation period completed successfully.',
               'Probation', 'Permanent')
        _write('confirmed_permanent',   'Confirmed as a permanent employee.',
               '', 'Permanent')

    # Status change → Terminated
    if (prev_status is not None
            and prev_status != instance.status_id
            and instance.status
            and instance.status.name in ('Terminated', 'Resigned', 'Retired')):
        status_to_event = {
            'Terminated': 'terminated',
            'Resigned':   'resigned',
            'Retired':    'retired',
        }
        ev = status_to_event.get(instance.status.name)
        if ev:
            _write(ev, f'Employee status changed to {instance.status.name}.',
                   '', instance.status.name)

    # Terminated → Active (reactivation)
    if (prev_status is not None
            and prev_status != instance.status_id
            and instance.status
            and instance.status.name == 'Active'):
        try:
            from .models import EmployeeStatus
            old_status_obj = EmployeeStatus.objects.filter(pk=prev_status).first()
            if old_status_obj and old_status_obj.name in ('Terminated', 'Resigned'):
                _write('reinstated', 'Employee reactivated.',
                       old_status_obj.name, 'Active')
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 4. Application.post_save → recruitment pipeline events
# ---------------------------------------------------------------------------

# Map each Application status to a lifecycle event type
_APP_STATUS_TO_EVENT = {
    'Applied':       'application_submitted',
    'Shortlisted':   'application_reviewed',
    'Interview':     'interview_scheduled',
    'Interviewed':   'interview_completed',
    'Selected':      'candidate_selected',
    'Hired':         'recruitment_completed',
    'Qualified':     'application_reviewed',   # auto-screen passed
}


@receiver(pre_save, sender='hr.Application')
def _store_app_prev_status(sender, instance, **kwargs):
    """Stash previous Application status for comparison in post_save."""
    if not instance.pk:
        instance._prev_app_status = None
        return
    try:
        instance._prev_app_status = sender.objects.get(pk=instance.pk).status
    except sender.DoesNotExist:
        instance._prev_app_status = None


@receiver(post_save, sender='hr.Application')
def track_application_lifecycle(sender, instance, created, **kwargs):
    """
    Fires a lifecycle event whenever an Application status advances.
    If the application is 'Hired' and has a linked employee
    (converted_employee), also writes offer_accepted + hired events.
    """
    from .models import EmployeeHistory
    from django.utils.timezone import localtime

    new_status = instance.status
    prev_status = getattr(instance, '_prev_app_status', None)

    # Nothing changed
    if not created and new_status == prev_status:
        return

    event_type = _APP_STATUS_TO_EVENT.get(new_status)
    if not event_type:
        return

    # We need an Employee to write against.
    # For statuses before hiring, there's no employee yet — record on
    # converted_employee if available, else skip (event will be backfilled
    # when the employee is created).
    employee = getattr(instance, 'converted_employee', None)
    if employee is None:
        return

    # Avoid duplicating the same event
    if EmployeeHistory.objects.filter(
        employee=employee, event_type=event_type
    ).exists():
        return

    now_t = localtime(timezone.now()).time()

    EmployeeHistory.objects.create(
        employee   = employee,
        department = employee.department,
        position   = employee.position,
        event_type = event_type,
        new_value  = new_status,
        notes      = f'Application status changed to "{new_status}".',
        start_date = instance.applied_date or timezone.localdate(),
        event_time = now_t,
    )

    # When hired: also write offer_sent → offer_accepted chain
    if new_status == 'Hired' and not EmployeeHistory.objects.filter(
        employee=employee, event_type='offer_accepted'
    ).exists():
        EmployeeHistory.objects.create(
            employee   = employee,
            department = employee.department,
            position   = employee.position,
            event_type = 'offer_sent',
            new_value  = 'Hired',
            notes      = 'Offer letter sent to candidate.',
            start_date = instance.applied_date or timezone.localdate(),
            event_time = now_t,
        )
        EmployeeHistory.objects.create(
            employee   = employee,
            department = employee.department,
            position   = employee.position,
            event_type = 'offer_accepted',
            new_value  = 'Hired',
            notes      = 'Candidate accepted the offer.',
            start_date = instance.applied_date or timezone.localdate(),
            event_time = now_t,
        )


# ---------------------------------------------------------------------------
# 5. TrainingRequest.post_save → training_assigned / training_completed
# ---------------------------------------------------------------------------

@receiver(pre_save, sender='hr.TrainingRequest')
def _store_training_prev_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._prev_tr_status = None
        return
    try:
        instance._prev_tr_status = sender.objects.get(pk=instance.pk).status
    except sender.DoesNotExist:
        instance._prev_tr_status = None


@receiver(post_save, sender='hr.TrainingRequest')
def track_training_lifecycle(sender, instance, created, **kwargs):
    """
    training_assigned  → when a TrainingRequest is created or first approved
    training_completed → when status reaches 'Completed'
    """
    from .models import EmployeeHistory
    from django.utils.timezone import localtime

    employee   = instance.employee if hasattr(instance, 'employee') else None
    if employee is None:
        return

    now_t      = localtime(timezone.now()).time()
    prev_status = getattr(instance, '_prev_tr_status', None)

    def _write(event_type, notes=''):
        EmployeeHistory.objects.create(
            employee   = employee,
            department = employee.department,
            position   = employee.position,
            event_type = event_type,
            new_value  = instance.title,
            notes      = notes,
            start_date = timezone.localdate(),
            event_time = now_t,
        )

    # New training request created
    if created:
        _write('training_assigned',
               f'Training assigned: "{instance.title}".')
        return

    # Status transitioned to Completed
    if (prev_status != 'Completed'
            and instance.status == 'Completed'
            and not EmployeeHistory.objects.filter(
                employee=employee,
                event_type='training_completed',
                new_value=instance.title
            ).exists()):
        _write('training_completed',
               f'Training completed: "{instance.title}".')


# ---------------------------------------------------------------------------
# 6. BiannualKPIScore.post_save → performance_review
# ---------------------------------------------------------------------------

@receiver(post_save, sender='hr.BiannualKPIScore')
def track_performance_review(sender, instance, created, **kwargs):
    """Writes a 'Performance Review Completed' event when a KPI score is saved."""
    if not created:
        return  # only on initial submission
    from .models import EmployeeHistory
    from django.utils.timezone import localtime

    employee = instance.employee
    if not employee:
        return

    period_label = f"{instance.year} {instance.period}"
    if EmployeeHistory.objects.filter(
        employee=employee,
        event_type='performance_review',
        new_value=period_label
    ).exists():
        return

    EmployeeHistory.objects.create(
        employee   = employee,
        department = employee.department,
        position   = employee.position,
        event_type = 'performance_review',
        new_value  = period_label,
        notes      = (
            f'Performance review submitted for {period_label}. '
            f'Overall score: {instance.overall_score}/5.0'
            if instance.overall_score else
            f'Performance review submitted for {period_label}.'
        ),
        start_date = (
            instance.submitted_at.date()
            if instance.submitted_at else timezone.localdate()
        ),
        event_time = (
            localtime(instance.submitted_at).time()
            if instance.submitted_at else localtime(timezone.now()).time()
        ),
    )
