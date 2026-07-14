from django import forms
from django.contrib.auth.models import User

from hr.models import Department, EmployeeCertificate, EmployeeStatus, Position, Role


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

