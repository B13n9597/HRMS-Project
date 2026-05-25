from django.db.models.signals import post_save
from django.dispatch           import receiver
from django.contrib.auth.models import User
from django.utils              import timezone
 
from .models import Employee
 
 
@receiver(post_save, sender=User)
def create_employee_on_user_create(sender, instance, created, **kwargs):
    """
    Fires the moment a new User is saved for the first time (created=True).
 
    Creates a blank Employee profile linked to the new User.
    The qr_token UUID is generated automatically by the Employee model
    (default=uuid.uuid4) — no manual step needed.
 
    HR fills in department, position, salary etc. through the
    HR dashboard after the account is created.
    """
    if created:
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