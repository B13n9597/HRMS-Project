# hr/services/kpi_service.py
#
# KPI and biannual performance evaluation logic.

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError

from hr.models import (
    KPICategory, KPIIndicator,
    PerformanceEvaluation, EvaluationScore,
    BiannualKPIScore,
    Employee, SystemSetting,
)


# ── Biannual period helpers ──────────────────────────────────────────────────

def current_biannual_period():
    """Returns (year, period) for today. H1=Jan-Jun, H2=Jul-Dec."""
    today = timezone.localdate()
    period = 'H1' if today.month <= 6 else 'H2'
    return today.year, period


def biannual_period_dates(year: int, period: str):
    """Return (start_date, end_date) for the given period."""
    import datetime
    if period == 'H1':
        return datetime.date(year, 1, 1), datetime.date(year, 6, 30)
    return datetime.date(year, 7, 1), datetime.date(year, 12, 31)


# ── Biannual KPI score CRUD ──────────────────────────────────────────────────

def submit_kpi_score(employee_id: int, evaluator: Employee, data: dict) -> BiannualKPIScore:
    """
    Create or update a BiannualKPIScore.
    data keys: evaluation_type, year, period,
               job_knowledge, work_quality, attendance, teamwork, ethics, comments
    """
    employee = get_object_or_404(Employee, pk=employee_id)
    eval_type = data.get('evaluation_type', 'self')
    year      = int(data.get('year',   timezone.localdate().year))
    period    = data.get('period',  current_biannual_period()[1])

    if eval_type == 'self' and employee != evaluator:
        raise ValidationError("You can only submit a self-assessment for yourself.")
    if eval_type == 'peer' and employee == evaluator:
        raise ValidationError("You cannot submit a peer evaluation for yourself.")

    scores = {}
    for field in ('job_knowledge', 'work_quality', 'attendance', 'teamwork', 'ethics'):
        val = int(data.get(field, 3))
        if not 1 <= val <= 5:
            raise ValidationError(f"{field} must be between 1 and 5.")
        scores[field] = val

    obj, _ = BiannualKPIScore.objects.update_or_create(
        employee=employee,
        evaluator=evaluator,
        evaluation_type=eval_type,
        year=year,
        period=period,
        defaults={
            **scores,
            'comments': data.get('comments', ''),
        }
    )
    obj.compute_overall()
    obj.save(update_fields=['overall_score'])
    return obj


def get_employee_kpi_summary(employee_id: int) -> dict:
    """Return all KPI scores for an employee, grouped by period."""
    employee = get_object_or_404(Employee, pk=employee_id)
    scores = BiannualKPIScore.objects.filter(
        employee=employee
    ).select_related('evaluator').order_by('-year', 'period', 'evaluation_type')
    return {'employee': employee, 'scores': scores}


def get_department_kpi_summary(department_ids) -> list:
    """Return average KPI scores for employees in given departments."""
    from django.db.models import Avg
    from hr.models import Employee as Emp
    employees = Emp.objects.filter(department_id__in=department_ids)
    results = []
    for emp in employees:
        avg = BiannualKPIScore.objects.filter(employee=emp).aggregate(
            avg=Avg('overall_score')
        )['avg']
        results.append({
            'employee': emp,
            'avg_score': round(float(avg), 2) if avg else None,
        })
    return results


def get_hr_kpi_dashboard() -> dict:
    """HR KPI dashboard: turnover, appraisal completion, etc."""
    from hr.models import Employee as Emp
    from django.db.models import Count, Avg
    total_employees = Emp.objects.filter(is_deleted=False).count()
    year, period = current_biannual_period()

    evaluated = BiannualKPIScore.objects.filter(
        year=year, period=period
    ).values('employee').distinct().count()

    completion_pct = round(evaluated / total_employees * 100) if total_employees else 0

    # Turnover: employees who left this year (resigned or terminated)
    from hr.models import EmployeeHistory
    terminated = EmployeeHistory.objects.filter(
        event_type__in=['resigned', 'retired'],
        start_date__year=year
    ).count()
    turnover_rate = round(terminated / total_employees * 100, 1) if total_employees else 0

    return {
        'total_employees':   total_employees,
        'evaluated':         evaluated,
        'completion_pct':    completion_pct,
        'turnover_rate':     turnover_rate,
        'current_year':      year,
        'current_period':    period,
    }


# ── Legacy evaluation helpers (kept for existing views) ──────────────────────

def get_all_categories():
    return KPICategory.objects.all().prefetch_related('kpiindicator_set')


def get_all_evaluations():
    return (
        PerformanceEvaluation.objects
        .select_related('employee', 'evaluator')
        .order_by('-evaluation_date')
    )


def get_employee_evaluations(employee_id: int):
    employee = get_object_or_404(Employee, pk=employee_id)
    return PerformanceEvaluation.objects.filter(
        employee=employee
    ).select_related('evaluator').order_by('-evaluation_date')


def create_evaluation(data: dict, evaluator: Employee) -> PerformanceEvaluation:
    employee = get_object_or_404(Employee, pk=data['employee_id'])
    evaluation = PerformanceEvaluation.objects.create(
        employee        = employee,
        evaluator       = evaluator,
        evaluation_type = data['evaluation_type'],
        evaluation_date = timezone.localdate(),
        period_start    = data['period_start'],
        period_end      = data['period_end'],
        comments        = data.get('comments', ''),
        status          = 'Draft',
    )
    for kpi_id, score_val in data.get('scores', {}).items():
        kpi = get_object_or_404(KPIIndicator, pk=kpi_id)
        score = float(score_val)
        if score > kpi.max_score:
            raise ValidationError(f"Score {score} exceeds max {kpi.max_score} for '{kpi.name}'.")
        EvaluationScore.objects.create(evaluation=evaluation, kpi=kpi, score=score, comment='')
    evaluation.calculate_overall_score()
    return evaluation


def get_kpi_summary() -> dict:
    categories  = list(get_all_categories())
    promotion_t = float(SystemSetting.get('kpi', 'promotion_threshold',   80))
    warning_t   = float(SystemSetting.get('kpi', 'warning_threshold',     50))
    excellent_t = float(SystemSetting.get('kpi', 'excellent_threshold',   90))
    satisf_t    = float(SystemSetting.get('kpi', 'satisfactory_threshold',60))
    return {
        'categories':  categories,
        'thresholds': {
            'excellent':    excellent_t,
            'promotion':    promotion_t,
            'satisfactory': satisf_t,
            'warning':      warning_t,
        },
        'recent_evaluations': get_all_evaluations()[:10],
    }
