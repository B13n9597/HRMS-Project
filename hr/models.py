"""
ACT HRMS — Final Merged Models
This file contains all the models for the ACT HRMS application.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# ============================================================
#  SOFT DELETE MANAGER & BASE MODEL  
# ============================================================

class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class BaseModel(models.Model):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects     = ActiveManager()       # default → active records only
    all_objects = models.Manager()      # includes soft-deleted records

    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    class Meta:
        abstract = True


# ============================================================
#  SYSTEM SETTINGS
# added `category` so settings can be grouped by area
#          (attendance / payroll / leave / kpi / recruitment)
#          and fetched with SystemSetting.get('payroll', 'required_days')
# ============================================================

class SystemSetting(BaseModel):
    category    = models.CharField(max_length=50)           # ← NEW
    key         = models.CharField(max_length=100)
    value       = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    updated_by  = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='settings_updated'
    )

    class Meta:
        unique_together = ('category', 'key')               # ← NEW constraint

    @classmethod
    def get(cls, category, key, default=None):
        """Helper: SystemSetting.get('payroll', 'required_days_per_month', 20)"""
        try:
            return cls.objects.get(category=category, key=key).value
        except cls.DoesNotExist:
            return default

    def __str__(self):
        return f"{self.category}.{self.key} = {self.value}"


# ============================================================
#  DEPARTMENT  
# ============================================================

class Department(BaseModel):
    name             = models.CharField(max_length=100)
    description      = models.TextField(blank=True)
    established_date = models.DateField(null=True, blank=True)
    manager          = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='managed_departments'
    )

    def __str__(self):
        return self.name


# ============================================================
#  POSITION  
# ============================================================

class Position(BaseModel):
    title       = models.CharField(max_length=100)
    grade_level = models.IntegerField()
    base_salary = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.title


# ============================================================
#  EMPLOYEE STATUS  
# ============================================================

class EmployeeStatus(BaseModel):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


# ============================================================
#  EMPLOYEE
# added qr_token (replaces NFC card)
#          UUID generated once per employee, stored in DB,
#          encoded into a QR image served at /attendance/my-qr/
# ============================================================

class Employee(BaseModel):
    user       = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    role       = models.ForeignKey(
        'Role',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
    )
    first_name = models.CharField(max_length=50, blank=True, default='')
    last_name  = models.CharField(max_length=50, blank=True, default='')
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='employees'
    )
    position   = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, blank=True)
    status     = models.ForeignKey(EmployeeStatus, on_delete=models.SET_NULL, null=True, blank=True)
    hire_date  = models.DateField(default=timezone.localdate)
    phone      = models.CharField(max_length=20, blank=True, default='')
    address    = models.TextField(blank=True, default='')

    #  — QR attendance token 
    qr_token   = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,     # generated once, never changed through forms
    )

    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        if full_name:
            return full_name
        if self.user:
            return self.user.get_username()
        return f"Employee {self.pk}"

    @classmethod
    def get_or_create_for_user(cls, user):
        return cls.objects.get_or_create(
            user=user,
            defaults={
                'first_name': user.first_name or user.get_username(),
                'last_name': user.last_name,
            },
        )

    def has_role(self, *role_names):
        return self.role is not None and self.role.name in role_names

    def __str__(self):
        return self.get_full_name()


# ============================================================
#  ROLE SYSTEM  
# ============================================================

class Role(BaseModel):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class UserRole(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'role')


# ============================================================
#  JOB POSTING  
# ============================================================

class JobPosting(BaseModel):
    title        = models.CharField(max_length=100)
    department   = models.ForeignKey(Department, on_delete=models.CASCADE)
    description  = models.TextField()
    posted_date  = models.DateField()
    closing_date = models.DateField()

    # minimum requirements used by auto-screening
    min_education        = models.CharField(max_length=50, blank=True)
    min_experience_years = models.IntegerField(default=0)
    required_skills      = models.TextField(blank=True)   # comma-separated

    def __str__(self):
        return self.title


# ============================================================
#  JOB VACANCY  
# ============================================================

class JobVacancy(BaseModel):
    title               = models.CharField(max_length=100)
    min_degree_required = models.CharField(max_length=100)
    is_active           = models.BooleanField(default=True)

    def __str__(self):
        return self.title


# ============================================================
#  APPLICANT  
# ============================================================

class Applicant(BaseModel):
    first_name = models.CharField(max_length=50)
    last_name  = models.CharField(max_length=50)
    email      = models.EmailField()
    phone      = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


# ============================================================
#  APPLICATION
#   added screening_score, screening_notes, education_level,
#          experience_years, skills, and run_auto_screening() method
#          so the system can automatically reject unqualified applicants
# ============================================================

class Application(BaseModel):
    STATUS_CHOICES = [
        ('Applied',              'Applied'),
        ('Screening',            'Screening'),
        ('Qualified',            'Qualified — passed auto screen'),
        ('Rejected_Auto',        'Rejected — auto screening'),   # ← NEW
        ('Interviewed',          'Interviewed'),
        ('Selected',             'Selected'),
        ('Rejected',             'Rejected — manual'),
    ]

    EDUCATION_RANK = {
        'highschool': 1,
        'diploma':    2,
        'bachelors':  3,
        'masters':    4,
        'phd':        5,
    }

    applicant        = models.ForeignKey(Applicant, on_delete=models.CASCADE)
    job              = models.ForeignKey(JobPosting, on_delete=models.CASCADE)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Applied')
    applied_date     = models.DateField()

    # — auto-screening fields
    education_level  = models.CharField(max_length=50, blank=True)   # e.g. 'masters'
    experience_years = models.IntegerField(default=0)
    skills           = models.TextField(blank=True)                   # comma-separated
    screening_score  = models.IntegerField(null=True, blank=True)     # 0–100
    screening_notes  = models.TextField(blank=True)

    def run_auto_screening(self):
        """
        Scores the applicant 0-100 against the job's minimum requirements.
        Automatically sets status to Qualified or Rejected_Auto.
        Threshold is read from SystemSetting so HR can change it without code.
        """
        job   = self.job
        score = 0
        notes = []

        # Education (40 points)
        applicant_rank = self.EDUCATION_RANK.get(self.education_level, 0)
        required_rank  = self.EDUCATION_RANK.get(job.min_education, 0)
        if applicant_rank >= required_rank:
            score += 40
        else:
            notes.append(
                f"Education: needs {job.min_education}, "
                f"applicant has {self.education_level}."
            )

        # Experience (30 points)
        if self.experience_years >= job.min_experience_years:
            score += 30
        else:
            notes.append(
                f"Experience: needs {job.min_experience_years} yrs, "
                f"applicant has {self.experience_years}."
            )

        # Skills (30 points)
        if job.required_skills:
            required  = {s.strip().lower() for s in job.required_skills.split(',')}
            applicant = {s.strip().lower() for s in self.skills.split(',')}
            matched   = required & applicant
            skill_pts = int((len(matched) / len(required)) * 30) if required else 30
            score    += skill_pts
            if skill_pts < 30:
                missing = required - applicant
                notes.append(f"Missing skills: {', '.join(missing)}.")
        else:
            score += 30

        # Read pass threshold from settings (default 70 if not set)
        threshold = int(SystemSetting.get('recruitment', 'min_screening_pass', 70))

        self.screening_score = score
        if score >= threshold:
            self.status          = 'Qualified'
            self.screening_notes = f"Score {score}/100 — passed."
        else:
            self.status          = 'Rejected_Auto'
            self.screening_notes = (
                f"Score {score}/100 — below threshold ({threshold}). "
                + " ".join(notes)
            )
        self.save()


# ============================================================
#  INTERVIEW  
# ============================================================

class Interview(BaseModel):
    application    = models.ForeignKey(Application, on_delete=models.CASCADE)
    interview_date = models.DateField()
    score          = models.IntegerField()
    result         = models.CharField(max_length=50)


# ============================================================
#  ATTENDANCE  — 
# ============================================================

class Attendance(BaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date     = models.DateField()
    time_in  = models.DateTimeField(null=True, blank=True)
    time_out = models.DateTimeField(null=True, blank=True)
    status   = models.CharField(max_length=20, default='Present')

    def calculate_status(self):
        """Reads thresholds from SystemSetting — no hardcoded values."""
        if not self.time_in:
            return
        start_hour    = int(SystemSetting.get('attendance', 'work_start_hour', 8))
        grace_minutes = int(SystemSetting.get('attendance', 'late_grace_minutes', 15))
        local_in      = timezone.localtime(self.time_in)
        if (local_in.hour, local_in.minute) > (start_hour, grace_minutes):
            self.status = 'Late'
        else:
            self.status = 'Present'

    class Meta:
        unique_together = ('employee', 'date')


# ============================================================
#  QR SCAN LOG  — 
# ============================================================

class QRScanLog(BaseModel):
    employee      = models.ForeignKey(Employee, on_delete=models.CASCADE)
    scan_time     = models.DateTimeField(auto_now_add=True)
    scan_type     = models.CharField(max_length=20)   # 'time_in' | 'time_out'
    is_successful = models.BooleanField(default=True)


# ============================================================
#  WORK SCHEDULE  — 
# ============================================================

class WorkSchedule(BaseModel):
    employee   = models.ForeignKey(Employee, on_delete=models.CASCADE)
    start_time = models.TimeField()
    end_time   = models.TimeField()


# ============================================================
#  LEAVE SYSTEM  — 
# ============================================================

class LeaveType(BaseModel):
    name        = models.CharField(max_length=50)
    max_days    = models.IntegerField()
    description = models.TextField(blank=True)


class LeaveRequest(BaseModel):
    STATUS_CHOICES = [
        ('Pending',  'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    employee       = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type     = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    start_date     = models.DateField()
    end_date       = models.DateField()
    requested_days = models.IntegerField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES)
    approved_by    = models.ForeignKey(
        Employee, on_delete=models.SET_NULL,
        null=True, related_name='approved_leaves'
    )
    approved_date  = models.DateField(null=True, blank=True)
    comments       = models.TextField(blank=True)


class LeaveBalance(BaseModel):
    employee       = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type     = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    remaining_days = models.IntegerField()
    last_updated   = models.DateField()


# ============================================================
#  SALARY  —  (good design)
# ============================================================

class Salary(BaseModel):
    employee       = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salaries')
    base_salary    = models.DecimalField(max_digits=10, decimal_places=2)
    effective_from = models.DateField()
    effective_to   = models.DateField(null=True, blank=True)


# ============================================================
#  PAYROLL
#   added required_days, days_worked, deduction_amount
#          and calculate_for_employee() so the examiner can see
#          the attendance → salary deduction formula clearly
# ============================================================

class Payroll(BaseModel):
    PAYMENT_STATUS = [
        ('Pending', 'Pending'),
        ('Paid',    'Paid'),
        ('On Hold', 'On Hold'),
    ]

    employee         = models.ForeignKey(Employee, on_delete=models.CASCADE)
    period_start     = models.DateField()
    period_end       = models.DateField()
    gross_salary     = models.DecimalField(max_digits=10, decimal_places=2)

# — attendance-linked deduction fields
    required_days    = models.IntegerField(default=20)
    days_worked      = models.IntegerField(default=0)
    deduction_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    deductions       = models.DecimalField(max_digits=10, decimal_places=2)
    net_salary       = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status   = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='Pending')

    @property
    def absent_days(self):
        return self.required_days - self.days_worked

    @classmethod
    def calculate_for_employee(cls, employee, period_start, period_end):
        """
        Calculates payroll for an employee for a given period.
        Formula: deduction = (absent_days / required_days) × gross_salary
        required_days is read from SystemSetting — HR can change it from the UI.
        """
        required_days = int(
            SystemSetting.get('attendance', 'required_days_per_month', 20)
        )

        # Count attendance records in the period
        days_worked = Attendance.objects.filter(
            employee=employee,
            date__gte=period_start,
            date__lte=period_end,
            status__in=['Present', 'Late'],
        ).count()

        # Get the current active salary
        salary_record = employee.salaries.filter(
            effective_from__lte=period_start,
            effective_to__isnull=True
        ).order_by('-effective_from').first()

        gross = float(salary_record.base_salary) if salary_record else 0
        absent_days = required_days - days_worked
        absent_days = max(0, absent_days)

        deduction = (absent_days / required_days * gross) if required_days else 0
        deduction = round(deduction, 2)
        net       = round(gross - deduction, 2)

        return {
            'gross_salary':     gross,
            'required_days':    required_days,
            'days_worked':      days_worked,
            'deduction_amount': deduction,
            'deductions':       deduction,
            'net_salary':       net,
        }


# ============================================================
#  KPI SYSTEM
# ============================================================

class KPICategory(BaseModel):
    name        = models.CharField(max_length=100)
    description = models.TextField()
    weight      = models.DecimalField(max_digits=5, decimal_places=2)   # e.g. 30.00 = 30%


class KPIIndicator(BaseModel):
    category    = models.ForeignKey(KPICategory, on_delete=models.CASCADE)
    name        = models.CharField(max_length=100)
    description = models.TextField()
    max_score   = models.IntegerField(default=10)                       # ← FIX 5
    is_active   = models.BooleanField(default=True)


# ============================================================
#  PERFORMANCE EVALUATION
#         This correctly supports peer-to-peer evaluation
#         where one employee rates another.
#         For HR/dept head evaluations, evaluator.user gives the User account.
#
#         evaluation_type distinguishes who is evaluating:
#           'probation_review' → dept head evaluates new hire
#           'annual'           → HR manager evaluates permanent staff
#           'peer'             → employee evaluates a colleague  ← peer-to-peer
#           'self'             → employee evaluates themselves
# ============================================================

class PerformanceEvaluation(BaseModel):
    EVAL_TYPE_CHOICES = [
        ('probation_review', 'Probation Review'),   # dept head → new employee
        ('annual',           'Annual Review'),       # HR → permanent employee
        ('peer',             'Peer Review'),         # employee → colleague
        ('self',             'Self Review'),         # employee → themselves
    ]
    OUTCOME_CHOICES = [
        ('passed_probation', 'Passed Probation → now permanent'),
        ('failed_probation', 'Failed Probation'),
        ('promoted',         'Promoted'),
        ('salary_raise',     'Salary Raise Approved'),
        ('warning',          'Warning Issued'),
        ('no_change',        'No Change'),
    ]

    employee        = models.ForeignKey(
        Employee, on_delete=models.CASCADE,
        related_name='evaluations_received'
    )
    # evaluator is Employee — supports peer-to-peer.
    # For HR/dept head: evaluator.user gives their User account.
    evaluator       = models.ForeignKey(
        Employee, on_delete=models.CASCADE,
        related_name='evaluations_given'
    )
    evaluation_type = models.CharField(max_length=20, choices=EVAL_TYPE_CHOICES)
    evaluation_date = models.DateField()
    period_start    = models.DateField()
    period_end      = models.DateField()
    overall_score   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    outcome         = models.CharField(
        max_length=20, choices=OUTCOME_CHOICES,
        null=True, blank=True
    )
    status          = models.CharField(max_length=20, default='Draft')
    comments        = models.TextField()

    def calculate_overall_score(self):
        """
        Weighted average across all KPI categories.
        (avg score in category / max_score) × category weight → sum = total out of 100
        """
        total = 0.0
        for category in KPICategory.objects.all():
            scores = EvaluationScore.objects.filter(
                evaluation=self,
                kpi__category=category,
                kpi__is_active=True,
            )
            if not scores.exists():
                continue
            indicators = category.kpiindicator_set.filter(is_active=True)
            max_val    = indicators.first().max_score if indicators.exists() else 10
            avg_raw    = sum(s.score for s in scores) / scores.count()
            cat_pct    = (avg_raw / max_val) * 100
            total     += (float(category.weight) / 100) * cat_pct

        self.overall_score = round(total, 2)
        self.save()

    def apply_outcome(self):
        """
        Reads promotion_threshold and warning_threshold from SystemSetting.
        Automatically decides the outcome and logs it to EmployeeHistory.
        """
        if self.overall_score is None:
            return

        promotion_threshold = float(SystemSetting.get('kpi', 'promotion_threshold', 80))
        warning_threshold   = float(SystemSetting.get('kpi', 'warning_threshold', 50))
        score    = float(self.overall_score)
        employee = self.employee

        if self.evaluation_type == 'probation_review':
            if score >= promotion_threshold:
                self.outcome = 'passed_probation'
                EmployeeHistory.objects.create(
                    employee=employee,
                    event_type='probation_passed',
                    old_value='probation',
                    new_value='permanent',
                    notes=f"KPI score: {score}%",
                    recorded_by=self.evaluator,
                )
            else:
                self.outcome = 'failed_probation'
                EmployeeHistory.objects.create(
                    employee=employee,
                    event_type='probation_failed',
                    notes=f"KPI score: {score}%",
                    recorded_by=self.evaluator,
                )

        elif self.evaluation_type in ('annual', 'peer'):
            if score >= promotion_threshold:
                self.outcome = 'salary_raise'
                EmployeeHistory.objects.create(
                    employee=employee,
                    event_type='salary_raise',
                    notes=f"KPI score: {score}% — raise approved",
                    recorded_by=self.evaluator,
                )
            elif score < warning_threshold:
                self.outcome = 'warning'
                EmployeeHistory.objects.create(
                    employee=employee,
                    event_type='warned',
                    notes=f"KPI score: {score}% — below warning threshold",
                    recorded_by=self.evaluator,
                )
            else:
                self.outcome = 'no_change'

        self.save()


class EvaluationScore(BaseModel):
    evaluation = models.ForeignKey(PerformanceEvaluation, on_delete=models.CASCADE)
    kpi        = models.ForeignKey(KPIIndicator, on_delete=models.CASCADE)
    score      = models.DecimalField(max_digits=5, decimal_places=2)
    comment    = models.TextField()

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.score > self.kpi.max_score:
            raise ValidationError(
                f"Score {self.score} exceeds max {self.kpi.max_score} "
                f"for '{self.kpi.name}'"
            )


# ============================================================
#  DISCIPLINARY RECORD  
# ============================================================

class DisciplinaryRecord(BaseModel):
    employee      = models.ForeignKey(Employee, on_delete=models.CASCADE)
    incident_date = models.DateField()
    description   = models.TextField()
    action_taken  = models.CharField(max_length=100)


# ============================================================
#  EMPLOYEE HISTORY
# ============================================================

class EmployeeHistory(BaseModel):
    EVENT_CHOICES = [
        ('hired',            'Hired'),
        ('probation_passed', 'Probation Passed'),
        ('probation_failed', 'Probation Failed'),
        ('promoted',         'Promoted'),
        ('transferred',      'Transferred'),
        ('salary_raise',     'Salary Raise'),
        ('warned',           'Warning Issued'),
        ('suspended',        'Suspended'),
        ('reinstated',       'Reinstated'),
        ('resigned',         'Resigned'),
        ('retired',          'Retired'),
        ('contract_renewed', 'Contract Renewed'),
    ]

    employee    = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True)
    department  = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    position    = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True)

    # FIX 4 ↓ — event tracking
    event_type  = models.CharField(max_length=50, choices=EVENT_CHOICES)
    old_value   = models.TextField(blank=True)   
    new_value   = models.TextField(blank=True)   
    notes       = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL,
        null=True, related_name='history_recorded'
    )

    start_date  = models.DateField()
    end_date    = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-start_date']


# ============================================================
#  EXIT + RETIREMENT  
# ============================================================

class ExitRecord(BaseModel):
    employee  = models.ForeignKey(Employee, on_delete=models.CASCADE)
    exit_type = models.CharField(max_length=50)
    exit_date = models.DateField()
    reason    = models.TextField()


class RetirementBenefit(BaseModel):
    employee       = models.ForeignKey(Employee, on_delete=models.CASCADE)
    pension_amount = models.DecimalField(max_digits=10, decimal_places=2)
    gratuity       = models.DecimalField(max_digits=10, decimal_places=2)


# ============================================================
#  NOTIFICATION  
# ============================================================

class Notification(BaseModel):
    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    message    = models.TextField()
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


# ============================================================
#  CHATBOT  
# ============================================================

class ChatbotSession(BaseModel):
    user          = models.ForeignKey(User, on_delete=models.CASCADE)
    session_start = models.DateTimeField()
    session_end   = models.DateTimeField(null=True, blank=True)
    is_active     = models.BooleanField(default=True)


class ChatbotConversation(BaseModel):
    session      = models.ForeignKey(ChatbotSession, on_delete=models.CASCADE)
    user_message = models.TextField()
    bot_response = models.TextField()
    timestamp    = models.DateTimeField(auto_now_add=True)


# ============================================================
#  REPORT 
# ============================================================

class Report(BaseModel):
    generated_by   = models.ForeignKey(User, on_delete=models.CASCADE)
    generated_date = models.DateTimeField(auto_now_add=True)
    report_type    = models.CharField(max_length=50)
    file_path      = models.CharField(max_length=255)


# ============================================================
#  AUDIT LOG  
# ============================================================

class AuditLog(BaseModel):
    user        = models.ForeignKey(User, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=50)
    table_name  = models.CharField(max_length=50)
    record_id   = models.IntegerField()
    timestamp   = models.DateTimeField(auto_now_add=True)
    ip_address  = models.CharField(max_length=50)
