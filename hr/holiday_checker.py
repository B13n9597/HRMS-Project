import holidays
from datetime import date

_ET_HOLIDAYS = holidays.country_holidays('ET', language='en')


def is_day_off(date_to_check: date) -> bool:
    """Return True for weekends or official Ethiopian holidays."""
    if date_to_check.weekday() >= 5:
        return True
    if date_to_check in _ET_HOLIDAYS:
        return True

    from hr.models import Holiday
    return Holiday.objects.filter(date=date_to_check, is_public=True).exists()
