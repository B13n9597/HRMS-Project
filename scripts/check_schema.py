import os
import sys
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE','humanresource.settings')
import django
django.setup()
from django.db import connection
introspector = connection.introspection
try:
	desc = introspector.get_table_description(connection.cursor(), 'hr_leavebalance')
	cols = [col.name for col in desc]
	print('hr_leavebalance columns:', cols)
except Exception as e:
	# fallback for other DBs
	cur = connection.cursor()
	cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='hr_leavebalance'")
	rows = cur.fetchall()
	print('information_schema columns:', rows)
