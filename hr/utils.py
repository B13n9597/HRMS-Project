from django.core   import signing
from django.utils  import time
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