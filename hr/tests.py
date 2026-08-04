import ssl
from unittest.mock import patch

from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User
from django.urls import reverse, NoReverseMatch
from hr.models import Role, Employee, Department, LeaveBalance
from hr.services import employee_service
from hr.services import leave_service


class DashboardRoleAccessTestCase(TestCase):
    """
    Tests for Dean & CEO dashboard role-based access control.
    Uses get_or_create to be safe against pre-existing live DB records.
    All requests use SERVER_NAME='localhost' to pass ALLOWED_HOSTS.
    """

    @classmethod
    def setUpTestData(cls):
        # Roles
        cls.role_dean, _ = Role.objects.get_or_create(name='Dean')
        cls.role_ceo, _ = Role.objects.get_or_create(name='President')
        cls.role_emp, _ = Role.objects.get_or_create(name='Employee')
        cls.role_hr, _ = Role.objects.get_or_create(name='HR Manager')

        # Department
        cls.dept, _ = Department.objects.get_or_create(name='_Test Department')

        # Dean User & Employee
        cls.dean_user, _ = User.objects.get_or_create(
            username='_test_dean_user',
            defaults={'first_name': 'Academic', 'last_name': 'Dean', 'email': '_dean@test.test'}
        )
        cls.dean_user.set_password('testpass123')
        cls.dean_user.save()
        cls.dean_emp, _ = Employee.objects.get_or_create(
            user=cls.dean_user,
            defaults={
                'first_name': 'Academic', 'last_name': 'Dean',
                'role': cls.role_dean, 'department': cls.dept, 'employee_id': '_EMP-DEAN-1'
            }
        )
        # Always force-update role in case existing record has a different role
        Employee.objects.filter(pk=cls.dean_emp.pk).update(role=cls.role_dean)
        cls.dean_emp.refresh_from_db()

        # CEO User & Employee
        cls.ceo_user, _ = User.objects.get_or_create(
            username='_test_ceo_user',
            defaults={'first_name': 'Chief', 'last_name': 'Executive', 'email': '_ceo@test.test'}
        )
        cls.ceo_user.set_password('testpass123')
        cls.ceo_user.save()
        cls.ceo_emp, _ = Employee.objects.get_or_create(
            user=cls.ceo_user,
            defaults={
                'first_name': 'Chief', 'last_name': 'Executive',
                'role': cls.role_ceo, 'department': cls.dept, 'employee_id': '_EMP-CEO-1'
            }
        )
        # Always force-update role in case existing record has a different role
        Employee.objects.filter(pk=cls.ceo_emp.pk).update(role=cls.role_ceo)
        cls.ceo_emp.refresh_from_db()

        # Regular Employee User
        cls.emp_user, _ = User.objects.get_or_create(
            username='_test_emp_user',
            defaults={'first_name': 'Regular', 'last_name': 'Staff', 'email': '_emp@test.test'}
        )
        cls.emp_user.set_password('testpass123')
        cls.emp_user.save()
        cls.emp, _ = Employee.objects.get_or_create(
            user=cls.emp_user,
            defaults={
                'first_name': 'Regular', 'last_name': 'Staff',
                'role': cls.role_emp, 'department': cls.dept, 'employee_id': '_EMP-STAFF-1'
            }
        )
        # Always force-update role in case existing record has a different role
        Employee.objects.filter(pk=cls.emp.pk).update(role=cls.role_emp)
        cls.emp.refresh_from_db()

    def _client(self):
        """Return a new test client that passes ALLOWED_HOSTS."""
        return Client(SERVER_NAME='localhost')

    def test_url_routes_resolve(self):
        """Dean and CEO dashboard URL names resolve without error."""
        try:
            dean_url = reverse('dean_dashboard')
            ceo_url = reverse('ceo_dashboard')
            self.assertIn('/dean/dashboard/', dean_url)
            self.assertIn('/ceo/dashboard/', ceo_url)
        except NoReverseMatch as e:
            self.fail(f"URL reverse failed: {e}")

    def test_unauthenticated_redirect_to_login(self):
        """Unauthenticated user accessing /dean/dashboard/ or /ceo/dashboard/ is redirected to login."""
        c = self._client()
        for url in ['/dean/dashboard/', '/ceo/dashboard/']:
            response = c.get(url)
            self.assertIn(response.status_code, [302, 301],
                         f"Expected redirect for unauthenticated access to {url}, got {response.status_code}")
            if response.status_code in [302, 301]:
                self.assertIn('/login/', response.get('Location', ''),
                             f"Expected redirect to /login/ for {url}")

    def test_unauthorized_user_returns_403(self):
        """Regular employee accessing dean/ceo dashboards gets 403 Forbidden."""
        c = self._client()
        c.force_login(self.emp_user)
        for url in ['/dean/dashboard/', '/ceo/dashboard/']:
            response = c.get(url)
            self.assertEqual(response.status_code, 403,
                           f"Expected 403 for employee access to {url}, got {response.status_code}")

    def test_dean_dashboard_access(self):
        """Dean user accessing /dean/dashboard/ gets 200 OK and expected template."""
        c = self._client()
        c.force_login(self.dean_user)
        response = c.get('/dean/dashboard/')
        self.assertEqual(response.status_code, 200,
                        f"Expected 200 for dean access, got {response.status_code}")
        self.assertTemplateUsed(response, 'hr/dashboard_dean.html')

    def test_ceo_dashboard_access(self):
        """CEO (President) user accessing /ceo/dashboard/ gets 200 OK and expected template."""
        c = self._client()
        c.force_login(self.ceo_user)
        response = c.get('/ceo/dashboard/')
        self.assertEqual(response.status_code, 200,
                        f"Expected 200 for CEO access, got {response.status_code}")
        self.assertTemplateUsed(response, 'hr/dashboard_president.html')

    def test_dean_export_attendance_csv(self):
        """Dean export attendance endpoint returns CSV response."""
        c = self._client()
        c.force_login(self.dean_user)
        response = c.get('/dean/export/attendance/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response.get('Content-Type', ''))

    def test_dean_export_leave_csv(self):
        """Dean export leave endpoint returns CSV response."""
        c = self._client()
        c.force_login(self.dean_user)
        response = c.get('/dean/export/leave/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response.get('Content-Type', ''))

    def test_ceo_export_institution_report_csv(self):
        """CEO export institution report endpoint returns CSV response."""
        c = self._client()
        c.force_login(self.ceo_user)
        response = c.get('/ceo/export/institution-report/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response.get('Content-Type', ''))

    def test_ceo_export_audit_logs_csv(self):
        """CEO export audit logs endpoint returns CSV response."""
        c = self._client()
        c.force_login(self.ceo_user)
        response = c.get('/ceo/export/audit-logs/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response.get('Content-Type', ''))

    def test_role_key_resolution(self):
        """get_role_key correctly identifies Dean and CEO roles."""
        self.dean_emp.role = self.role_dean
        self.dean_emp.save(update_fields=['role'])
        self.ceo_emp.role = self.role_ceo
        self.ceo_emp.save(update_fields=['role'])
        self.emp.role = self.role_emp
        self.emp.save(update_fields=['role'])

        self.assertEqual(employee_service.get_role_key(self.dean_user), employee_service.ROLE_DEAN)
        self.assertEqual(employee_service.get_role_key(self.ceo_user), employee_service.ROLE_CEO)
        self.assertEqual(employee_service.get_role_key(self.emp_user), employee_service.ROLE_EMPLOYEE)

    def test_dashboard_redirect_routing(self):
        """get_dashboard_redirect routes Dean to /dean/dashboard/ and CEO to /ceo/dashboard/."""
        self.dean_emp.role = self.role_dean
        self.dean_emp.save(update_fields=['role'])
        self.ceo_emp.role = self.role_ceo
        self.ceo_emp.save(update_fields=['role'])

        self.assertEqual(employee_service.get_dashboard_redirect(self.dean_user), '/dean/dashboard/')
        self.assertEqual(employee_service.get_dashboard_redirect(self.ceo_user), '/ceo/dashboard/')

    def test_create_employee_continues_when_welcome_email_fails_with_ssl_error(self):
        """Employee creation should still succeed when SMTP/SSL delivery fails."""
        with patch('hr.services.employee_service.send_mail', side_effect=ssl.SSLError('certificate verify failed')):
            employee = employee_service.create_employee({
                'first_name': 'Ada',
                'last_name': 'Lovelace',
                'email': 'ada@example.com',
                'username': 'ada',
                'department_id': self.dept.id,
                'role_id': self.role_hr.id,
                'send_email': True,
            })

        self.assertEqual(employee.user.email, 'ada@example.com')
        self.assertEqual(employee.user.username, 'ada')
        self.assertTrue(Employee.objects.filter(user=employee.user).exists())


class GenderRestrictedLeaveTestCase(TestCase):
    def setUp(self):
        self.role, _ = Role.objects.get_or_create(name='Employee')
        self.female_user = User.objects.create_user(username='female_leave_test', password='testpass123')
        self.male_user = User.objects.create_user(username='male_leave_test', password='testpass123')
        # The user-creation signal creates these employee profiles.
        Employee.objects.filter(user=self.female_user).update(
            first_name='Aster', last_name='Test', employee_id='TEST-FEMALE-LEAVE',
            role=self.role, gender='Female',
        )
        Employee.objects.filter(user=self.male_user).update(
            first_name='Abel', last_name='Test', employee_id='TEST-MALE-LEAVE',
            role=self.role, gender='Male',
        )
        self.female_employee = Employee.objects.get(user=self.female_user)
        self.male_employee = Employee.objects.get(user=self.male_user)

    def test_balances_and_api_only_include_gender_eligible_leave_types(self):
        female_balances = leave_service.get_leave_balance(self.female_employee.id)
        male_balances = leave_service.get_leave_balance(self.male_employee.id)

        self.assertNotIn('Paternity', [balance.leave_type.name for balance in female_balances])
        self.assertNotIn('Maternity', [balance.leave_type.name for balance in male_balances])
        self.assertFalse(LeaveBalance.objects.filter(
            employee=self.female_employee, leave_type__name='Paternity'
        ).exists())
        self.assertFalse(LeaveBalance.objects.filter(
            employee=self.male_employee, leave_type__name='Maternity'
        ).exists())

        client = Client(SERVER_NAME='localhost')
        client.force_login(self.female_user)
        response = client.get(reverse('api_leaves'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn('Paternity', [balance['leave_type'] for balance in payload['balances']])
        self.assertNotIn('Paternity', [leave_type['name'] for leave_type in payload['leave_types']])
