# hrms/services/recruitment_service.py
#
# Recruitment pipeline: job posts, candidates, auto-screening, offers.

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError

from hrms.models import (
    JobPost, Candidate, CandidateApplication,
    InterviewPanel, OfferLetter,
    Department, Position, SystemSetting,
)


# ── JOB POSTS ──────────────────────────────────────────────────────────────────

def get_all_job_posts():
    return (
        JobPost.objects
        .select_related('department', 'position')
        .order_by('-posted_date')
    )


def get_active_job_posts():
    return get_all_job_posts().filter(status='open')


def create_job_post(data: dict, posted_by) -> JobPost:
    dept = get_object_or_404(Department, pk=data['department_id'])
    pos  = Position.objects.filter(pk=data.get('position_id')).first()
    return JobPost.objects.create(
        title                = data['title'],
        department           = dept,
        position             = pos,
        description          = data.get('description', ''),
        responsibilities     = data.get('responsibilities', ''),
        min_education        = data.get('min_education', 'bachelors'),
        min_experience_years = int(data.get('min_experience_years', 0)),
        required_skills      = data.get('required_skills', ''),
        vacancies            = int(data.get('vacancies', 1)),
        deadline             = data.get('deadline') or None,
        status               = 'open',
        posted_by            = posted_by,
    )


def close_job_post(post_id: int) -> JobPost:
    post = get_object_or_404(JobPost, pk=post_id)
    post.status = 'closed'
    post.save(update_fields=['status'])
    return post


# ── CANDIDATES & APPLICATIONS ─────────────────────────────────────────────────

def get_all_applications():
    return (
        CandidateApplication.objects
        .select_related('candidate', 'job_post', 'job_post__department')
        .order_by('-applied_date')
    )


def get_applications_for_post(post_id: int):
    post = get_object_or_404(JobPost, pk=post_id)
    return (
        CandidateApplication.objects
        .filter(job_post=post)
        .select_related('candidate')
        .order_by('-applied_date')
    )


def submit_application(data: dict) -> CandidateApplication:
    """
    Creates (or finds) a Candidate and submits their application.
    Immediately runs auto-screening.
    """
    post = get_object_or_404(JobPost, pk=data['post_id'])

    if not post.is_accepting_applications():
        raise ValidationError("This job post is no longer accepting applications.")

    candidate, _ = Candidate.objects.get_or_create(
        email=data['email'],
        defaults={
            'first_name':       data.get('first_name', ''),
            'last_name':        data.get('last_name', ''),
            'phone':            data.get('phone', ''),
            'education_level':  data.get('education_level', ''),
            'experience_years': int(data.get('experience_years', 0)),
            'skills':           data.get('skills', ''),
        }
    )

    if CandidateApplication.objects.filter(candidate=candidate, job_post=post).exists():
        raise ValidationError("This candidate has already applied for this post.")

    application = CandidateApplication.objects.create(
        candidate    = candidate,
        job_post     = post,
        applied_date = timezone.localdate(),
        status       = 'applied',
    )

    # Run auto-screening immediately
    application.run_auto_screening()
    return application


def hire_candidate(application_id: int, hire_data: dict, hr_user) -> object:
    """
    Converts a qualified candidate into an Employee.
    hire_data keys: department_id, position_id, hire_date, salary
    """
    application = get_object_or_404(CandidateApplication, pk=application_id)
    dept        = get_object_or_404(Department, pk=hire_data['department_id'])
    position    = get_object_or_404(Position, pk=hire_data['position_id'])

    return application.convert_to_employee(
        department  = dept,
        position    = position,
        hire_date   = hire_data['hire_date'],
        salary      = hire_data['salary'],
        created_by  = hr_user,
    )


# ── SUMMARY ──────────────────────────────────────────────────────────────────

def get_recruitment_summary() -> dict:
    applications  = get_all_applications()
    threshold     = int(SystemSetting.get('recruitment', 'min_screening_pass', 70))
    return {
        'posts':        get_all_job_posts(),
        'applications': applications,
        'qualified':    applications.filter(status='screening_passed').count(),
        'rejected_auto':applications.filter(status='screening_rejected').count(),
        'pending':      applications.filter(status='applied').count(),
        'threshold':    threshold,
    }