import csv

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils.crypto import get_random_string

from hr.models import Department, Employee, EmployeeStatus, Position


class Command(BaseCommand):
    help = (
        "Create users and linked employee profiles from a CSV file. "
        "Expected columns: username,email,first_name,last_name,phone,address,"
        "department,position,status,password"
    )

    def add_arguments(self, parser):
        parser.add_argument('csv_path', help='Path to the employee CSV file')
        parser.add_argument(
            '--default-password',
            default=None,
            help='Password used when a row has no password column/value',
        )

    def handle(self, *args, **options):
        csv_path = options['csv_path']
        default_password = options['default_password']
        User = get_user_model()

        try:
            csv_file = open(csv_path, newline='', encoding='utf-8-sig')
        except OSError as exc:
            raise CommandError(f'Could not open CSV file: {exc}') from exc

        created_count = 0
        updated_count = 0

        with csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames:
                raise CommandError('CSV file is empty or missing a header row.')

            for row_number, row in enumerate(reader, start=2):
                email = (row.get('email') or '').strip()
                username = (row.get('username') or email).strip()

                if not username:
                    raise CommandError(f'Row {row_number}: username or email is required.')

                first_name = (row.get('first_name') or '').strip()
                last_name = (row.get('last_name') or '').strip()
                password = (row.get('password') or default_password or get_random_string(12)).strip()

                user, user_created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'email': email,
                        'first_name': first_name,
                        'last_name': last_name,
                    },
                )

                if user_created:
                    user.set_password(password)
                    user.save(update_fields=['password'])
                else:
                    changed_fields = []
                    for field, value in {
                        'email': email,
                        'first_name': first_name,
                        'last_name': last_name,
                    }.items():
                        if value and getattr(user, field) != value:
                            setattr(user, field, value)
                            changed_fields.append(field)
                    if changed_fields:
                        user.save(update_fields=changed_fields)

                employee, _ = Employee.get_or_create_for_user(user)
                employee.first_name = first_name or employee.first_name or user.username
                employee.last_name = last_name or employee.last_name
                employee.phone = (row.get('phone') or employee.phone or '').strip()
                employee.address = (row.get('address') or employee.address or '').strip()

                department_name = (row.get('department') or '').strip()
                if department_name:
                    employee.department, _ = Department.objects.get_or_create(name=department_name)

                position_title = (row.get('position') or '').strip()
                if position_title:
                    employee.position = Position.objects.filter(title=position_title).first()
                    if employee.position is None:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Row {row_number}: position "{position_title}" was not found; left blank.'
                            )
                        )

                status_name = (row.get('status') or '').strip()
                if status_name:
                    employee.status, _ = EmployeeStatus.objects.get_or_create(name=status_name)

                employee.save()

                if user_created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Onboarding complete. Created {created_count} users, updated {updated_count} users.'
            )
        )
