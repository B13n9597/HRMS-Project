import os, sys
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE','humanresource.settings')
import django
django.setup()
from django.utils import timezone
from hr.models import LeaveBalance

updated = LeaveBalance.objects.filter(last_updated__isnull=True).update(last_updated=timezone.localdate())
print('updated rows:', updated)
