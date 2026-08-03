from django.core.management.base import BaseCommand
from hr.services.probation_service import run_probation_checks


class Command(BaseCommand):
    help = 'Send 59th-day probation reminders and make eligible employees permanent.'

    def handle(self, *args, **options):
        result = run_probation_checks()
        self.stdout.write(self.style.SUCCESS(
            f"Probation checks complete: {result['notified']} notification(s), {result['converted']} conversion(s)."
        ))
