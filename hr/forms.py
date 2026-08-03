from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.contrib.auth.models import User

from hr.models import (
    Department,
    DisciplinaryIncident,
    Employee,
    EmployeeCertificate,
    EmployeeStatus,
    Grievance,
    Position,
    Role,
    TrainingRequest,
    Applicant,
    Application,
    JobPosting,
)


phone_validator = RegexValidator(
    regex=r'^\+?[0-9][0-9\s\-()]{6,19}$',
    message='Enter a valid phone number (digits, spaces, +, - and parentheses only).',
)


class PublicApplicationForm(forms.ModelForm):
    """Public-facing application form with server-side file and duplicate checks."""
    job = forms.ModelChoiceField(queryset=JobPosting.objects.none(), label='Position applied for')

    class Meta:
        model = Applicant
        fields = [
            'first_name', 'middle_name', 'last_name', 'gender', 'marital_status',
            'email', 'phone', 'emergency_contact', 'fayda_id', 'cv', 'qualification',
            'field_of_study', 'institution', 'work_experience',
        ]
        widgets = {
            'gender': forms.Select(), 'marital_status': forms.Select(),
            'work_experience': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['job'].queryset = JobPosting.objects.filter(
            is_deleted=False, closing_date__gte=__import__('django').utils.timezone.localdate()
        ).order_by('title')
        for field_name in ('phone', 'emergency_contact'):
            self.fields[field_name].validators.append(phone_validator)

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if Applicant.objects.filter(email__iexact=email).exists():
            raise ValidationError('An application with this email already exists.')
        return email

    def clean_fayda_id(self):
        return self._validate_upload(self.cleaned_data['fayda_id'], {'.pdf', '.jpg', '.jpeg', '.png'}, 'Fayda ID')

    def clean_cv(self):
        return self._validate_upload(self.cleaned_data['cv'], {'.pdf', '.doc', '.docx'}, 'CV')

    @staticmethod
    def _validate_upload(upload, extensions, label):
        import os
        if upload.size > 5 * 1024 * 1024:
            raise ValidationError(f'{label} must be 5 MB or smaller.')
        if os.path.splitext(upload.name)[1].lower() not in extensions:
            raise ValidationError(f'{label} must be one of: {", ".join(sorted(extensions))}.')
        return upload

    def save_application(self):
        applicant = self.save()
        return Application.objects.create(
            applicant=applicant, job=self.cleaned_data['job'],
            applied_date=__import__('django').utils.timezone.localdate(),
        )


class EmployeeCreateForm(forms.Form):
    first_name = forms.CharField(max_length=50, required=True)
    last_name = forms.CharField(max_length=50, required=True)
    email = forms.EmailField(required=True)
    username = forms.CharField(max_length=150, required=False)
    employee_id = forms.CharField(max_length=50, required=False)
    attendance_pin = forms.CharField(max_length=6, required=False)
    hire_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    department_id = forms.ModelChoiceField(queryset=Department.objects.none(), required=True, label="Department")
    position_id = forms.ModelChoiceField(queryset=Position.objects.none(), required=False, label="Position")
    role_id = forms.ModelChoiceField(queryset=Role.objects.none(), required=True, label="Role")
    status_id = forms.ModelChoiceField(queryset=EmployeeStatus.objects.none(), required=False, label="Status")
    phone = forms.CharField(max_length=20, required=False)
    address = forms.CharField(required=False)
    base_salary = forms.DecimalField(max_digits=10, decimal_places=2, required=False)
    send_email = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        self.existing_user_id = kwargs.pop("existing_user_id", None)
        super().__init__(*args, **kwargs)
        self.fields["department_id"].queryset = Department.objects.order_by("name")
        self.fields["position_id"].queryset = Position.objects.order_by("title")
        self.fields["role_id"].queryset = Role.objects.order_by("name")
        self.fields["status_id"].queryset = EmployeeStatus.objects.order_by("name")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        existing = User.objects.filter(email__iexact=email)
        if self.existing_user_id:
            existing = existing.exclude(id=self.existing_user_id)
        if existing.exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        existing = User.objects.filter(username__iexact=username)
        if self.existing_user_id:
            existing = existing.exclude(id=self.existing_user_id)
        if username and existing.exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_attendance_pin(self):
        pin = self.cleaned_data.get("attendance_pin", "").strip()
        if pin and (not pin.isdigit() or len(pin) != 6):
            raise forms.ValidationError("Attendance PIN must be exactly 6 digits.")
        return pin

    def service_payload(self):
        payload = {}
        for key, value in self.cleaned_data.items():
            if key.endswith("_id") and value is not None:
                payload[key] = value.id
            elif value not in (None, ""):
                payload[key] = value
        return payload


class BulkEmployeeUploadForm(forms.Form):
    csv_file = forms.FileField(label="Roster file")

    def clean_csv_file(self):
        uploaded = self.cleaned_data["csv_file"]
        name = uploaded.name.lower()
        if not (name.endswith(".csv") or name.endswith(".xlsx")):
            raise forms.ValidationError("Upload a .csv or .xlsx file.")
        return uploaded


class ManualAttendanceForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=True)
    time_in = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}), required=True)
    time_out = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}), required=True)
    pin = forms.CharField(
        max_length=10, 
        required=True,
        widget=forms.PasswordInput(attrs={"placeholder": "Enter your 4-6 digit PIN"})
    )
    signature = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "Type your full name as signature"}),
    )

    def clean(self):
        cleaned = super().clean()
        time_in = cleaned.get("time_in")
        time_out = cleaned.get("time_out")
        if time_in and time_out and time_out < time_in:
            raise forms.ValidationError("Clock-out time cannot be earlier than clock-in time.")
        return cleaned


class EmployeeKioskForm(forms.Form):
    """
    Simplified attendance form for employees using the dashboard (kiosk-like):
    only requires PIN and signature. Name is displayed/read-only from profile.
    """
    name = forms.CharField(max_length=100, required=False)
    pin = forms.CharField(
        max_length=10,
        required=True,
        widget=forms.PasswordInput(attrs={"placeholder": "Enter your 4-6 digit PIN"})
    )
    signature = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "Type your full name as signature"}),
    )


class TrainingRequestForm(forms.ModelForm):
    class Meta:
        model = TrainingRequest
        fields = [
            "title",
            "provider",
            "type",
            "start_date",
            "end_date",
            "cost",
            "funding_source",
            "business_justification",
            "supporting_document",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "business_justification": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")
        self.fields["supporting_document"].required = False


class SupervisorTrainingRequestForm(forms.ModelForm):
    employee = forms.ModelChoiceField(queryset=Employee.objects.none(), label="Employee")

    class Meta:
        model = TrainingRequest
        fields = [
            "employee",
            "title",
            "provider",
            "type",
            "start_date",
            "end_date",
            "cost",
            "funding_source",
            "business_justification",
            "required_skills",
            "supporting_document",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "business_justification": forms.Textarea(attrs={"rows": 4}),
            "required_skills": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        supervised_employees = kwargs.pop("supervised_employees", None)
        super().__init__(*args, **kwargs)
        if supervised_employees is not None:
            self.fields["employee"].queryset = supervised_employees.order_by("last_name", "first_name")
        else:
            self.fields["employee"].queryset = Employee.objects.none()
        self.fields["supporting_document"].required = False
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")


class TrainingCompletionForm(forms.ModelForm):
    class Meta:
        model = TrainingRequest
        fields = [
            "completion_date",
            "cpd_points",
            "certificate",
            "skills_learned",
            "knowledge_transfer_method",
            "feedback",
            "satisfaction_rating",
        ]
        widgets = {
            "completion_date": forms.DateInput(attrs={"type": "date"}),
            "skills_learned": forms.Textarea(attrs={"rows": 3}),
            "knowledge_transfer_method": forms.TextInput(attrs={"placeholder": "Presentation / Team briefing / SOP update"}),
            "feedback": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")


class GrievanceForm(forms.ModelForm):
    class Meta:
        model = Grievance
        fields = [
            "category",
            "subject",
            "description",
            "incident_date",
            "desired_resolution",
            "confidential",
            "evidence",
        ]
        widgets = {
            "incident_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "desired_resolution": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")


class DisciplinaryIncidentForm(forms.ModelForm):
    class Meta:
        model = DisciplinaryIncident
        fields = [
            "incident_date",
            "category",
            "description",
            "employee_response",
            "offense_number",
            "evidence_attachment",
            "investigation_notes",
            "action_taken",
            "decision_reason",
            "effective_date",
            "status",
        ]
        widgets = {
            "incident_date": forms.DateInput(attrs={"type": "date"}),
            "effective_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "employee_response": forms.Textarea(attrs={"rows": 3}),
            "investigation_notes": forms.Textarea(attrs={"rows": 4}),
            "decision_reason": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")


class EmployeeCertificateForm(forms.ModelForm):
    class Meta:
        model = EmployeeCertificate
        fields = [
            "title",
            "cert_type",
            "issued_by",
            "issued_date",
            "expiry_date",
            "document",
        ]
        widgets = {
            "issued_date": forms.DateInput(attrs={"type": "date"}),
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-input")
        self.fields["document"].widget.attrs.update({
            "accept": ".pdf,.png,.jpg,.jpeg",
            "id": "documentInput",
        })
        self.fields["document"].required = True
        self.fields["title"].required = True

    def clean_document(self):
        document = self.cleaned_data.get("document")
        if document:
            valid_ext = (".pdf", ".png", ".jpg", ".jpeg")
            if not document.name.lower().endswith(valid_ext):
                raise forms.ValidationError("Upload a PDF or image file (.pdf, .png, .jpg, .jpeg).")
        return document

