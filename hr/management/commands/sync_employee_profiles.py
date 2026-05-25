from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from hr.models import Employee


class Command(BaseCommand):
    help = 'Create missing Employee profiles for existing User accounts.'

    def handle(self, *args, **options):
        User = get_user_model()
        created_count = 0

        for user in User.objects.all():
            _, created = Employee.get_or_create_for_user(user)
            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Created {created_count} missing employee profiles.')
        )
