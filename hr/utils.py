import time
from django.core import signing
from django.utils import timezone

# Define aliases for attendance_views.py
def generate_daily_token(employee):
    return generate_qr_token(employee)

def verify_daily_token(signed_token):
    return verify_qr_token(signed_token)

def generate_qr_token(employee):
    """
    Generates a secure QR token that changes every 30 seconds.

    Payload includes:
    - employee.qr_token (UUID)
    - time window (changes every 30 seconds)
    """

    current_window = int(time.time() // 30)

    payload = {
        'token': str(employee.qr_token),
        'window': current_window,
    }

    return signing.dumps(payload, salt='qr-attendance-30s')


# Verify scanned QR token
def verify_qr_token(signed_token):
    """
    Verifies the QR token and returns:

        (Employee, None)  → if valid
        (None, error)     → if invalid

    Security checks:
    1. Signature validity
    2. Token expiration (~60 seconds)
    3. Time window match (±30 sec tolerance)
    4. Employee existence
    """

    from .models import Employee

    if not signed_token:
        return None, 'No token provided.'

    # Step 1 & 2: verify signature + expiration
    try:
        payload = signing.loads(
            signed_token,
            salt='qr-attendance-30s',
            max_age=60  # token expires in ~1 minute
        )
    except signing.SignatureExpired:
        return None, 'QR code expired — please refresh.'
    except signing.BadSignature:
        return None, 'Invalid QR code.'

    # Step 3: validate time window (anti-replay)
    current_window = int(time.time() // 30)
    token_window = payload.get('window')

    # Allow small delay (network/scan time)
    if abs(current_window - token_window) > 1:
        return None, 'QR expired — generate a new one.'

    # Step 4: find employee
    try:
        employee = Employee.objects.get(
            qr_token=payload.get('token')
        )
        return employee, None

    except Employee.DoesNotExist:
        return None, 'Employee not found.'


def verify_employee_credentials(employee_id, inputted_pin, current_signature_data):
    """
    Verifies the employee kiosk fallback credentials before committing attendance.

    Returns:
        (employee, verification_log, None) on success
        (None, verification_log, error) on failure
    """
    from .models import Employee

    verification_log = {
        'employee_id': employee_id,
        'pin_matched': False,
        'signature_supplied': False,
        'stored_signature_matched': False,
        'verified_at': timezone.now().isoformat(),
    }

    try:
        employee = Employee.objects.get(employee_id=employee_id)
    except Employee.DoesNotExist:
        return None, verification_log, 'Invalid Employee ID or PIN.'

    stored_pin = employee.attendance_pin or employee.pin or ''
    verification_log['pin_matched'] = stored_pin == str(inputted_pin or '').strip()
    if not verification_log['pin_matched']:
        return None, verification_log, 'Invalid Employee ID or PIN.'

    signature_data = (current_signature_data or '').strip()
    verification_log['signature_supplied'] = signature_data.startswith('data:image/')
    if not verification_log['signature_supplied']:
        return None, verification_log, 'A signature image is required.'

    if employee.signature_data:
        verification_log['stored_signature_matched'] = employee.signature_data == signature_data

    return employee, verification_log, None
