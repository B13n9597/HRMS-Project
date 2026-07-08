# hr/services/payroll_service.py
#
# Payroll calculation logic using PayrollRecord model.

from django.utils import timezone
from django.core.exceptions import ValidationError

from hr.models import PayrollRecord, Employee, Salary, Attendance, SystemSetting


def get_all_payroll_records(query='', month='', year='', status=''):
    """Return filtered PayrollRecord queryset for HR payroll center."""
    from django.db.models import Q
    qs = (
        PayrollRecord.objects
        .select_related('employee', 'employee__department', 'employee__position')
        .order_by('-period_start', 'employee__first_name', 'employee__last_name')
    )
    if query:
        qs = qs.filter(
            Q(employee__first_name__icontains=query) |
            Q(employee__last_name__icontains=query)
        )
    if month:
        qs = qs.filter(period_start__month=month)
    if year:
        qs = qs.filter(period_start__year=year)
    if status:
        qs = qs.filter(payment_status=status)
    return qs


def get_employee_payroll_records(employee: Employee):
    """Return last 24 payroll records for an employee."""
    return (
        PayrollRecord.objects
        .filter(employee=employee)
        .order_by('-period_start')[:24]
    )


def generate_payroll(period_start, period_end, bonus_map: dict = None) -> dict:
    """
    Generate PayrollRecord for all active employees for a period.
    bonus_map: {employee_id: bonus_amount}
    Returns {'created': int, 'skipped': int, 'errors': list}
    """
    from hr.models import EmployeeStatus
    bonus_map = bonus_map or {}
    active_employees = Employee.objects.filter(
        is_deleted=False,
        status__name__iexact='Active'
    )
    created = skipped = 0
    errors = []

    for emp in active_employees:
        if PayrollRecord.objects.filter(
            employee=emp, period_start=period_start, period_end=period_end
        ).exists():
            skipped += 1
            continue

        bonus = float(bonus_map.get(emp.id, 0))
        try:
            vals = PayrollRecord.calculate_for_employee(emp, period_start, period_end, bonus)
            if vals['base_salary'] <= 0:
                skipped += 1
                continue

            PayrollRecord.objects.create(
                employee         = emp,
                period_start     = period_start,
                period_end       = period_end,
                base_salary      = vals['base_salary'],
                bonus            = vals['bonus'],
                absent_deduction = vals['absent_deduction'],
                gross_salary     = vals['gross_salary'],
                required_days    = vals['required_days'],
                days_worked      = vals['days_worked'],
                income_tax       = vals['income_tax'],
                pension          = vals['pension'],
                total_deductions = vals['total_deductions'],
                net_salary       = vals['net_salary'],
                payment_status   = 'Pending',
            )
            created += 1
        except Exception as e:
            errors.append(f"{emp.get_full_name()}: {e}")

    return {'created': created, 'skipped': skipped, 'errors': errors}


def mark_paid(record_id: int) -> PayrollRecord:
    record = PayrollRecord.objects.get(pk=record_id)
    record.payment_status = 'Paid'
    record.save(update_fields=['payment_status'])
    return record
