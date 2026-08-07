"""
ACT HRMS — Final Merged Models
This file contains all the models for the ACT HRMS application.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError



# ============================================================
#  SOFT DELETE MANAGER & BASE MODEL  
# ============================================================

class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class BaseModel(models.Model):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects     = ActiveManager()       # default -> active records only
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
    GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female')]
    MARITAL_STATUS_CHOICES = [('Single', 'Single'), ('Married', 'Married')]
    EMPLOYMENT_PHASE_CHOICES = [('Probation', 'Probation'), ('Permanent', 'Permanent')]
    user       = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    role       = models.ForeignKey(
        'Role',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        db_index=True,
    )
    first_name = models.CharField(max_length=50, blank=True, default='')
    middle_name = models.CharField(max_length=50, blank=True, default='')
    last_name  = models.CharField(max_length=50, blank=True, default='')
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, default='')
    marital_status = models.CharField(max_length=10, choices=MARITAL_STATUS_CHOICES, blank=True, default='')
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='employees',
        db_index=True,
    )
    position   = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, blank=True)
    status     = models.ForeignKey(EmployeeStatus, on_delete=models.SET_NULL, null=True, blank=True)
    hire_date  = models.DateField(default=timezone.localdate)
    employment_phase = models.CharField(
        max_length=12, choices=EMPLOYMENT_PHASE_CHOICES, default='Probation'
    )
    phone      = models.CharField(max_length=20, blank=True, default='')
    emergency_contact = models.CharField(max_length=20, blank=True, default='')
    fayda_id = models.FileField(upload_to='ids/', null=True, blank=True)
    qualification = models.CharField(max_length=100, blank=True, default='')
    field_of_study = models.CharField(max_length=100, blank=True, default='')
    institution = models.CharField(max_length=150, blank=True, default='')
    address    = models.TextField(blank=True, default='')

    #  — QR attendance token 
    qr_token   = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,    
    )

    # — Tablet login/signature fields
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    pin         = models.CharField(max_length=6, null=True, blank=True)
    attendance_pin = models.CharField(max_length=6, blank=True, default='')
    signature_data = models.TextField(blank=True, default='')
    photo       = models.ImageField(upload_to='employee_photos/', null=True, blank=True)


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
    GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female')]
    MARITAL_STATUS_CHOICES = [('Single', 'Single'), ('Married', 'Married')]
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, default='')
    last_name  = models.CharField(max_length=50)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    marital_status = models.CharField(max_length=10, choices=MARITAL_STATUS_CHOICES)
    email      = models.EmailField(unique=True)
    phone      = models.CharField(max_length=20)
    emergency_contact = models.CharField(max_length=20)
    fayda_id = models.FileField(upload_to='ids/')
    cv = models.FileField(upload_to='cvs/')
    qualification = models.CharField(max_length=100)
    field_of_study = models.CharField(max_length=100)
    institution = models.CharField(max_length=150)
    work_experience = models.TextField(blank=True, default='')

    @property
    def full_name(self):
        return ' '.join(part for part in (self.first_name, self.middle_name, self.last_name) if part)

    def __str__(self):
        return self.full_name


# ============================================================
#  APPLICATION
#   added screening_score, screening_notes, education_level,
#          experience_years, skills, and run_auto_screening() method
#          so the system can automatically reject unqualified applicants
# ============================================================

class Application(BaseModel): 
    STATUS_CHOICES = [
        ('Applied',              'Applied'),
        ('Shortlisted',          'Shortlisted'),
        ('Interview',            'Interview'),
        ('Screening',            'Screening'),
        ('Qualified',            'Qualified — passed auto screen'),
        ('Rejected_Auto',        'Rejected — auto screening'),   # ← NEW
        ('Interviewed',          'Interviewed'),
        ('Selected',             'Selected'),
        ('Hired',                'Hired'),
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
    hr_notes = models.TextField(blank=True, default='')
    converted_employee = models.OneToOneField(
        Employee, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='source_application',
    )

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
    employee  = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date      = models.DateField()
    time_in   = models.DateTimeField(null=True, blank=True)
    time_out  = models.DateTimeField(null=True, blank=True)
    status    = models.CharField(max_length=20, default='Present')
    signature = models.ImageField(upload_to='signatures/', null=True, blank=True)
    # Text signature stored separately so manual attendance always has one
    signature_text = models.CharField(max_length=255, blank=True, default='')

    def clean(self):
        super().clean()
        if self.time_in and self.time_out and self.time_out < self.time_in:
            raise ValidationError('Clock-out time cannot be earlier than clock-in time.')

    def calculate_status(self):
        """
        Derive attendance status from time_in.
        Called after check-in is created so the status reflects punctuality.
        Late threshold: 09:00 AM local time.
        """
        if not self.time_in:
            self.status = 'Absent'
            return
        from django.utils import timezone as tz
        local_in = tz.localtime(self.time_in)
        # Late if arriving after 09:00 AM
        if local_in.hour > 9 or (local_in.hour == 9 and local_in.minute > 0):
            self.status = 'Late'
        else:
            self.status = 'Present'

    def get_worked_hours(self):
        """Return total worked hours as a float, or None if not clocked out."""
        if self.time_in and self.time_out:
            delta = self.time_out - self.time_in
            return round(delta.total_seconds() / 3600, 2)
        return None

    class Meta:
        unique_together = ('employee', 'date')
        indexes = [
            models.Index(fields=['date', 'status'], name='attendance_date_status_idx'),
        ]



# ============================================================
#  QR SCAN LOG  — 
# ============================================================

class QRScanLog(BaseModel):
    employee      = models.ForeignKey(Employee, on_delete=models.CASCADE)
    scan_time     = models.DateTimeField(auto_now_add=True)
    scan_type     = models.CharField(max_length=20)   # 'time_in' | 'time_out'
    is_successful = models.BooleanField(default=True)
    ip_address    = models.CharField(max_length=50, blank=True, default='')
    user_agent    = models.TextField(blank=True, default='')
    failure_reason = models.TextField(blank=True, default='')



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
    def __str__(self):
        return self.name


class LeavePolicy(BaseModel):
    """Optional gender rule for a leave type; blank means available to everyone."""
    GENDER_CHOICES = [('', 'All employees'), ('Male', 'Male'), ('Female', 'Female')]
    leave_type = models.OneToOneField(LeaveType, on_delete=models.CASCADE, related_name='policy')
    allowed_gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, default='')

    def __str__(self):
        return f"{self.leave_type.name}: {self.allowed_gender or 'All'}"


class LeaveRequest(BaseModel):
    STATUS_CHOICES = [
        ('Pending',  'Pending'),
        ('Recommended', 'Recommended'),
        ('Not Recommended', 'Not Recommended'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
    ]

    SUPERVISOR_RECOMMENDATION_CHOICES = [
        ('', 'Pending Supervisor Review'),
        ('recommended', 'Recommended'),
        ('not_recommended', 'Not Recommended'),
    ]

    employee       = models.ForeignKey(Employee, on_delete=models.CASCADE, db_index=True)
    leave_type     = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    start_date     = models.DateField()
    end_date       = models.DateField()
    requested_days = models.IntegerField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending', db_index=True)
    approved_by    = models.ForeignKey(
        Employee, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_leaves'
    )
    approved_date  = models.DateField(null=True, blank=True)
    comments       = models.TextField(blank=True)

    # Supervisor recommendation fields
    supervisor_recommendation = models.CharField(
        max_length=20,
        choices=SUPERVISOR_RECOMMENDATION_CHOICES,
        blank=True,
        default='',
    )
    supervisor_reviewed_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='supervised_leave_reviews'
    )
    supervisor_reviewed_date = models.DateField(null=True, blank=True)
    supervisor_note = models.TextField(blank=True, default='')

    # Contact info during leave
    contact_info_during_leave = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Phone number or address where employee can be reached during leave'
    )

    # Optional supporting document (PDF or image)
    document       = models.FileField(
        upload_to='leave_documents/', null=True, blank=True
    )

    def clean(self):
        super().clean()
        if not self.employee_id or not self.leave_type_id:
            return
        # Import locally to avoid a models/services import cycle during startup.
        from hr.services.leave_service import is_leave_type_available
        if not is_leave_type_available(self.employee, self.leave_type):
            raise ValidationError({
                'leave_type': f'{self.leave_type.name} leave is not available for this employee.'
            })


class LeaveBalance(BaseModel):
    employee       = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type     = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    allocated_days = models.IntegerField(default=0)
    used_days      = models.IntegerField(default=0)
    remaining_days = models.IntegerField()
    last_updated   = models.DateField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'leave_type')


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
#          the attendance -> salary deduction formula clearly
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
#           'probation_review' -> dept head evaluates new hire
#           'annual'           -> HR manager evaluates permanent staff
#           'peer'             -> employee evaluates a colleague  <- peer-to-peer
#           'self'             -> employee evaluates themselves
# ============================================================

class PerformanceEvaluation(BaseModel):
    EVAL_TYPE_CHOICES = [
        ('probation_review', 'Probation Review'),   # dept head -> new employee
        ('annual',           'Annual Review'),       # HR -> permanent employee
        ('peer',             'Peer Review'),         # employee -> colleague
        ('self',             'Self Review'),         # employee -> themselves
    ]
    OUTCOME_CHOICES = [
        ('passed_probation', 'Passed Probation -> now permanent'),
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
        (avg score in category / max_score) * category weight -> sum = total out of 100
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
        # ── Recruitment Pipeline ───────────────────────────────
        ('application_submitted',    'Job Application Submitted'),
        ('application_reviewed',     'Application Reviewed'),
        ('interview_scheduled',      'Interview Scheduled'),
        ('interview_completed',      'Interview Completed'),
        ('candidate_selected',       'Candidate Selected'),
        ('offer_sent',               'Offer Sent'),
        ('offer_accepted',           'Offer Accepted'),
        # ── Onboarding & Probation ────────────────────────────
        ('hired',                    'Employee Created'),
        ('recruitment_completed',    'Recruitment Completed'),
        ('onboarding_started',       'Onboarding Started'),
        ('onboarding_completed',     'Onboarding Completed'),
        ('probation_started',        'Probation Started'),
        ('probation_passed',         'Probation Completed'),
        ('confirmed_permanent',      'Confirmed as Permanent Employee'),
        ('probation_failed',         'Probation Failed'),
        # ── Career Progression ────────────────────────────────
        ('promoted',                 'Promotion'),
        ('demoted',                  'Demotion'),
        ('transferred',              'Department Transfer'),
        ('position_change',          'Position Change'),
        ('salary_change',            'Salary Grade Change'),
        ('salary_raise',             'Salary Raise'),
        ('contract_renewed',         'Contract Renewed'),
        # ── Performance & Development ─────────────────────────
        ('training_assigned',        'Training Assigned'),
        ('training_completed',       'Training Completed'),
        ('performance_review',       'Performance Review Completed'),
        # ── Disciplinary ──────────────────────────────────────
        ('warned',                   'Warning Issued'),
        ('suspended',                'Suspended'),
        ('reinstated',               'Reinstated / Reactivated'),
        # ── Exit ──────────────────────────────────────────────
        ('terminated',               'Termination'),
        ('resigned',                 'Resignation'),
        ('retired',                  'Retirement'),
    ]

    # All event types that belong on the career timeline.
    # Operational records (daily attendance, leave balance, payslips) are
    # deliberately excluded — they live in their own modules.
    CAREER_EVENT_TYPES = {
        'application_submitted', 'application_reviewed', 'interview_scheduled',
        'interview_completed', 'candidate_selected', 'offer_sent', 'offer_accepted',
        'hired', 'recruitment_completed', 'onboarding_started', 'onboarding_completed',
        'probation_started', 'probation_passed', 'confirmed_permanent', 'probation_failed',
        'promoted', 'demoted', 'transferred', 'position_change',
        'salary_change', 'salary_raise', 'contract_renewed',
        'training_assigned', 'training_completed', 'performance_review',
        'warned', 'suspended', 'reinstated',
        'terminated', 'resigned', 'retired',
    }

    # Colour category used by the template to pick dot/badge colour
    EVENT_CATEGORY = {
        'application_submitted': 'blue',  'application_reviewed': 'blue',
        'interview_scheduled':   'blue',  'interview_completed':  'blue',
        'candidate_selected':    'blue',  'offer_sent':           'blue',
        'offer_accepted':        'green',
        'hired':                 'green', 'recruitment_completed':'green',
        'onboarding_started':    'green', 'onboarding_completed': 'green',
        'probation_started':     'green', 'probation_passed':     'green',
        'confirmed_permanent':   'green', 'probation_failed':     'amber',
        'promoted':              'purple','demoted':              'amber',
        'transferred':           'purple','position_change':      'purple',
        'salary_change':         'purple','salary_raise':         'purple',
        'contract_renewed':      'purple',
        'training_assigned':     'teal',  'training_completed':   'teal',
        'performance_review':    'teal',
        'warned':                'amber', 'suspended':            'amber',
        'reinstated':            'green',
        'terminated':            'red',   'resigned':             'red',
        'retired':               'red',
    }

    employee    = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True)
    department  = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    position    = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True)

    event_type  = models.CharField(max_length=50, choices=EVENT_CHOICES)
    old_value   = models.TextField(blank=True)
    new_value   = models.TextField(blank=True)
    notes       = models.TextField(blank=True)

    # Who triggered this event (HR officer, system, etc.)
    performed_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='lifecycle_events_performed'
    )
    # Legacy FK kept for backward-compat (Employee-typed recorder)
    recorded_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='history_recorded'
    )

    start_date  = models.DateField()
    event_time  = models.TimeField(null=True, blank=True)  # time within start_date
    end_date    = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-start_date', '-event_time']

    def get_event_category(self):
        return self.EVENT_CATEGORY.get(self.event_type, 'blue')


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


# ============================================================
#  SUPERVISOR -> DEPARTMENT ASSIGNMENT
# ============================================================

class SupervisorDepartment(BaseModel):
    """Links a supervisor employee to the department(s) they supervise."""
    supervisor = models.ForeignKey(
        Employee, on_delete=models.CASCADE,
        related_name='supervised_departments'
    )
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE,
        related_name='supervisors'
    )

    class Meta:
        unique_together = ('supervisor', 'department')

    def __str__(self):
        return f"{self.supervisor.get_full_name()} -> {self.department.name}"


# ============================================================
#  EMPLOYEE CERTIFICATE / DOCUMENT UPLOAD
# ============================================================

class EmployeeCertificate(BaseModel):
    CERT_TYPES = [
        ('degree',   'Academic Degree'),
        ('diploma',  'Diploma'),
        ('training', 'Training Certificate'),
        ('license',  'Professional License'),
        ('other',    'Other'),
    ]
    employee    = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='certificates')
    title       = models.CharField(max_length=200)
    cert_type   = models.CharField(max_length=20, choices=CERT_TYPES, default='other')
    issued_by   = models.CharField(max_length=200, blank=True)
    issued_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    document    = models.FileField(upload_to='certificates/', null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.title}"


# ============================================================
#  TRAINING & CPD MODULE
# ============================================================

class TrainingRequest(BaseModel):
    TYPE_CHOICES = [
        ('In-House', 'In-House'),
        ('External', 'External'),
        ('Overseas', 'Overseas'),
        ('Online', 'Online'),
    ]
    STATUS_CHOICES = [
        ('Submitted', 'Submitted'),
        ('Supervisor Review', 'Supervisor Review'),
        ('Supervisor Rejected', 'Supervisor Rejected'),
        ('HR Review', 'HR Review'),
        ('HR Rejected', 'HR Rejected'),
        ('Approved', 'Approved'),
        ('Completed', 'Completed'),
    ]
    REQUEST_SOURCE_CHOICES = [
        ('Employee', 'Employee Requested'),
        ('Supervisor', 'Supervisor Recommended'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='training_requests')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='training_requests')
    title = models.CharField(max_length=200)
    provider = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='In-House')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    funding_source = models.CharField(max_length=200, blank=True, default='')
    business_justification = models.TextField(blank=True, default='')
    required_skills = models.TextField(blank=True, default='')
    supporting_document = models.FileField(upload_to='training_documents/', null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Submitted')
    request_source = models.CharField(max_length=20, choices=REQUEST_SOURCE_CHOICES, default='Employee')
    requested_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='training_requests_initiated')
    request_date = models.DateTimeField(auto_now_add=True)
    supervisor = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='training_requests_reviewed')
    supervisor_comment = models.TextField(blank=True, default='')
    supervisor_decision_date = models.DateTimeField(null=True, blank=True)
    hr_comment = models.TextField(blank=True, default='')
    hr_decision_date = models.DateTimeField(null=True, blank=True)
    completion_date = models.DateTimeField(null=True, blank=True)
    cpd_points = models.PositiveIntegerField(default=0)
    certificate = models.FileField(upload_to='training_certificates/', null=True, blank=True)
    skills_learned = models.TextField(blank=True, default='')
    knowledge_transfer_method = models.CharField(max_length=200, blank=True, default='')
    feedback = models.TextField(blank=True, default='')
    satisfaction_rating = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-request_date']

    @property
    def annual_cpd_progress(self):
        year = timezone.localdate().year
        completed_points = TrainingRequest.objects.filter(
            employee=self.employee,
            status='Completed',
            completion_date__year=year,
            is_deleted=False,
        ).aggregate(models.Sum('cpd_points'))['cpd_points__sum'] or 0
        return completed_points

    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.title} ({self.status})"


# ============================================================
#  DISCIPLINE / EMPLOYEE RELATIONS
# ============================================================

class DisciplinaryIncident(BaseModel):
    ACTION_CHOICES = [
        ('No Action', 'No Action'),
        ('Verbal Warning', 'Verbal Warning'),
        ('Written Warning', 'Written Warning'),
        ('Final Warning', 'Final Warning'),
        ('Suspension', 'Suspension'),
        ('Demotion', 'Demotion'),
        ('Dismissal', 'Dismissal'),
    ]
    STATUS_CHOICES = [
        ('Reported', 'Reported'),
        ('Under Investigation', 'Under Investigation'),
        ('Decision', 'Decision'),
        ('Employee Acknowledgment', 'Employee Acknowledgment'),
        ('Appeal', 'Appeal'),
        ('Closed', 'Closed'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='disciplinary_incidents')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='disciplinary_incidents')
    incident_date = models.DateField()
    date_reported = models.DateField(auto_now_add=True)
    reporting_supervisor = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='reported_incidents')
    category = models.CharField(max_length=100)
    description = models.TextField()
    evidence_attachment = models.FileField(upload_to='discipline_evidence/', null=True, blank=True)
    employee_response = models.TextField(blank=True, default='')
    offense_number = models.CharField(max_length=50, blank=True, default='')
    investigation_notes = models.TextField(blank=True, default='')
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default='Reported')
    action_taken = models.CharField(max_length=40, choices=ACTION_CHOICES, default='No Action')
    decision_reason = models.TextField(blank=True, default='')
    effective_date = models.DateField(null=True, blank=True)
    decided_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='decided_incidents')
    decision_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-incident_date']

    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.category}"


class DisciplinaryAppeal(BaseModel):
    STATUS_CHOICES = [
        ('Submitted', 'Submitted'),
        ('Under Review', 'Under Review'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Closed', 'Closed'),
    ]
    incident = models.ForeignKey(DisciplinaryIncident, on_delete=models.CASCADE, related_name='appeals')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='disciplinary_appeals')
    appeal_reason = models.TextField()
    appeal_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Submitted')
    reviewer = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='appeal_reviews')
    decision_comment = models.TextField(blank=True, default='')
    decision_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-appeal_date']

    def __str__(self):
        return f"Appeal for {self.incident}"


class Grievance(BaseModel):
    STATUS_CHOICES = [
        ('Submitted', 'Submitted'),
        ('Under Review', 'Under Review'),
        ('Investigation', 'Investigation'),
        ('Action Required', 'Action Required'),
        ('Resolved', 'Resolved'),
        ('Closed', 'Closed'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='grievances')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='grievances')
    category = models.CharField(max_length=100)
    subject = models.CharField(max_length=200)
    description = models.TextField()
    incident_date = models.DateField(null=True, blank=True)
    evidence = models.FileField(upload_to='grievance_evidence/', null=True, blank=True)
    desired_resolution = models.TextField(blank=True, default='')
    confidential = models.BooleanField(default=False)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='Submitted')
    submitted_at = models.DateTimeField(auto_now_add=True)
    assigned_investigator = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_grievances')
    investigation_notes = models.TextField(blank=True, default='')
    findings = models.TextField(blank=True, default='')
    corrective_action = models.TextField(blank=True, default='')
    response = models.TextField(blank=True, default='')
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.subject}"


# ============================================================
#  HOLIDAY CALENDAR
# ============================================================

class Holiday(BaseModel):
    name      = models.CharField(max_length=100)
    date      = models.DateField()
    is_public = models.BooleanField(default=True)
    notes     = models.TextField(blank=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.name} ({self.date})"


# ============================================================
#  PAYROLL RECORD (detailed, replaces simple Payroll for new logic)
# ============================================================

class PayrollRecord(BaseModel):
    PAYMENT_STATUS = [
        ('Pending', 'Pending'),
        ('Reviewed', 'Reviewed'),
        ('HR Approved', 'HR Approved'),
        ('Paid',    'Paid'),
        ('On Hold', 'On Hold'),
    ]
    employee         = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payroll_records')
    period_start     = models.DateField()
    period_end       = models.DateField()
    base_salary      = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bonus            = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gross_salary     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    required_days    = models.IntegerField(default=20)
    days_worked      = models.IntegerField(default=0)
    absent_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    income_tax       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pension          = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    loan_deduction   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_salary       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status   = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='Pending')
    notes            = models.TextField(blank=True)

    class Meta:
        unique_together = ('employee', 'period_start', 'period_end')

    @staticmethod
    def calculate_income_tax(gross: float) -> float:
        """Flat 15% income tax."""
        return round(gross * 0.15, 2)

    @classmethod
    def calculate_for_employee(cls, employee, period_start, period_end, bonus=0):
        required_days = int(SystemSetting.get('attendance', 'required_days_per_month', 20))
        days_worked = Attendance.objects.filter(
            employee=employee, date__gte=period_start, date__lte=period_end,
            status__in=['Present', 'Late'],
        ).count()
        salary_record = Salary.objects.filter(
            employee=employee, effective_from__lte=period_start,
        ).order_by('-effective_from').first()
        base = float(salary_record.base_salary) if salary_record else 0.0
        absent_days = max(0, required_days - days_worked)
        absent_deduction = round((absent_days / required_days * base) if required_days else 0, 2)
        gross = round(base - absent_deduction + float(bonus), 2)
        pension = round(gross * 0.07, 2)
        income_tax = round(cls.calculate_income_tax(gross), 2)
        total_deductions = round(pension + income_tax, 2)
        net = round(gross - total_deductions, 2)
        return {
            'base_salary': base, 'bonus': float(bonus),
            'absent_deduction': absent_deduction, 'gross_salary': gross,
            'required_days': required_days, 'days_worked': days_worked,
            'pension': pension, 'income_tax': income_tax,
            'total_deductions': total_deductions, 'net_salary': net,
        }

    def __str__(self):
        return f"{self.employee.get_full_name()} {self.period_start}"


# ============================================================
#  BIANNUAL KPI SCORE (1-5 scale, per criterion)
# ============================================================

class BiannualKPIScore(BaseModel):
    PERIOD_CHOICES = [('H1', 'Jan-Jun'), ('H2', 'Jul-Dec')]
    SCORE_CHOICES  = [(i, str(i)) for i in range(1, 6)]
    EVAL_TYPE      = [('self', 'Self'), ('peer', 'Peer'), ('supervisor', 'Supervisor'), ('hr', 'HR')]

    employee        = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='kpi_scores')
    evaluator       = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='kpi_scores_given')
    evaluation_type = models.CharField(max_length=20, choices=EVAL_TYPE)
    year            = models.IntegerField()
    period          = models.CharField(max_length=2, choices=PERIOD_CHOICES)
    job_knowledge   = models.IntegerField(choices=SCORE_CHOICES, default=3)
    work_quality    = models.IntegerField(choices=SCORE_CHOICES, default=3)
    attendance      = models.IntegerField(choices=SCORE_CHOICES, default=3)
    teamwork        = models.IntegerField(choices=SCORE_CHOICES, default=3)
    ethics          = models.IntegerField(choices=SCORE_CHOICES, default=3)
    overall_score   = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    comments        = models.TextField(blank=True)
    submitted_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'evaluator', 'evaluation_type', 'year', 'period')

    def compute_overall(self):
        scores = [self.job_knowledge, self.work_quality, self.attendance, self.teamwork, self.ethics]
        self.overall_score = round(sum(scores) / len(scores), 2)
        return self.overall_score

    def __str__(self):
        return f"{self.employee.get_full_name()} {self.evaluation_type} {self.year}/{self.period}"


# ============================================================
#  SUPERVISOR HIRING REQUEST
# ============================================================

class HiringRequest(BaseModel):
    STATUS_CHOICES = [
        ('Pending',  'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    EMPLOYMENT_TYPES = [
        ('Full-Time',  'Full-Time'),
        ('Part-Time',  'Part-Time'),
        ('Contract',   'Contract'),
        ('Internship', 'Internship'),
        ('Temporary',  'Temporary'),
    ]

    requested_by = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='hiring_requests'
    )
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name='hiring_requests'
    )
    position_title       = models.CharField(max_length=100)
    number_needed        = models.PositiveIntegerField(default=1)
    employment_type      = models.CharField(max_length=50, choices=EMPLOYMENT_TYPES, default='Full-Time')
    reason               = models.TextField()
    required_skills      = models.TextField(blank=True, default='')
    preferred_start_date = models.DateField()

    request_date = models.DateTimeField(auto_now_add=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')

    reviewed_by   = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_hiring_requests'
    )
    decision_date = models.DateTimeField(null=True, blank=True)
    hr_comment    = models.TextField(blank=True, default='')

    created_vacancy = models.ForeignKey(
        'JobPosting', on_delete=models.SET_NULL, null=True, blank=True, related_name='hiring_requests'
    )

    class Meta:
        ordering = ['-request_date']

    def __str__(self):
        return f"{self.position_title} - {self.department.name} ({self.status})"

