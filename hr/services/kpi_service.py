# hrms/services/kpi_service.py
#
# KPI and performance evaluation business logic.

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError

from hrms.models import (
    KPICategory, KPIIndicator,
    PerformanceEvaluation, EvaluationScore,
    Employee, SystemSetting, EmployeeHistory,
)


def get_all_categories():
    return KPICategory.objects.all().prefetch_related('indicators')


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
    """
    Creates a PerformanceEvaluation and its EvaluationScore rows.

    data keys:
        employee_id, evaluation_type, period_start, period_end,
        comments, scores: {kpi_id: score_value, ...}
    """
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
            raise ValidationError(
                f"Score {score} exceeds max {kpi.max_score} for '{kpi.name}'."
            )
        EvaluationScore.objects.create(
            evaluation = evaluation,
            kpi        = kpi,
            score      = score,
        )

    evaluation.calculate_overall_score()
    return evaluation


def finalize_evaluation(evaluation_id: int) -> PerformanceEvaluation:
    """
    Finalises an evaluation: calculates score, applies outcome,
    updates EmployeeHistory.
    """
    evaluation = get_object_or_404(PerformanceEvaluation, pk=evaluation_id)
    evaluation.calculate_overall_score()
    evaluation.apply_outcome()
    evaluation.status = 'Final'
    evaluation.save()
    return evaluation


def get_kpi_summary() -> dict:
    """
    Dashboard summary: category weights and threshold settings.
    """
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