from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from unittest.mock import patch


@override_settings(CHIEF_OPERATOR_USERNAME='chief')
class TeamTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.chief = User.objects.create_superuser('chief', password='Original-Strong-2026!')
        cls.admin = User.objects.create_superuser('other-admin', password='Original-Strong-2026!')
        cls.operator = User.objects.create_user('worker', password='Original-Strong-2026!', is_staff=True)

    def test_only_chief_can_generate_access(self):
        for user in [self.admin, self.operator]:
            self.client.force_login(user)
            self.assertEqual(self.client.get('/team/').status_code, 403)
            self.assertEqual(self.client.post('/team/generate/', {'role': 'admin'}).status_code, 403)
        self.assertEqual(User.objects.count(), 3)

    def test_generated_credentials_work_and_are_not_stored_in_session(self):
        self.client.force_login(self.chief)
        self.assertEqual(self.client.get('/team/generate/').status_code, 405)
        for role in ['operator', 'admin']:
            response = self.client.post('/team/generate/', {'role': role})
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response['Cache-Control'])
            credentials = response.context['credentials']
            user = User.objects.get(username=credentials['username'])
            self.assertTrue(user.check_password(credentials['password']))
            self.assertTrue(user.is_staff)
            self.assertEqual(user.is_superuser, role == 'admin')
            self.assertGreaterEqual(len(credentials['password']), 24)
            self.assertNotIn(credentials['password'], str(dict(self.client.session)))
        self.assertIsNone(self.client.get('/team/').context.get('credentials'))

    def test_generation_validates_username_role_and_csrf(self):
        self.client.force_login(self.chief)
        for values in [{'username': 'chief', 'role': 'admin'}, {'username': 'bad login', 'role': 'operator'},
                       {'username': 'new-user', 'role': 'root'}]:
            self.assertEqual(self.client.post('/team/generate/', values).status_code, 400)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.chief)
        self.assertEqual(csrf_client.post('/team/generate/', {'role': 'admin'}).status_code, 403)
        self.assertEqual(User.objects.count(), 3)

    def test_other_admin_cannot_change_chief_password_or_disable_chief(self):
        self.client.force_login(self.admin)
        for suffix in ['change/', 'password/']:
            response = self.client.post(f'/admin/auth/user/{self.chief.pk}/{suffix}',
                {'username': 'renamed', 'password1': 'Hijacked-Strong-2026!', 'password2': 'Hijacked-Strong-2026!'})
            self.assertEqual(response.status_code, 403)
        self.client.post('/admin/auth/user/', {'action': 'deactivate', '_selected_action': [self.chief.pk], 'index': 0})
        self.chief.refresh_from_db()
        self.assertTrue(self.chief.is_active)
        self.assertEqual(self.chief.username, 'chief')
        self.assertTrue(self.chief.check_password('Original-Strong-2026!'))

    def test_other_admin_cannot_grant_admin_even_with_forged_post(self):
        self.client.force_login(self.admin)
        response = self.client.post('/admin/auth/user/add/', {'username': 'forged-admin',
            'usable_password': 'true', 'password1': 'Moonlight-Library-2026!', 'password2': 'Moonlight-Library-2026!',
            'is_staff': 'on', 'is_superuser': 'on', 'is_active': 'on'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.get(username='forged-admin').is_superuser)

    def test_bootstrap_never_resets_existing_password(self):
        self.chief.is_active = self.chief.is_staff = self.chief.is_superuser = False
        self.chief.save()
        with patch.dict('os.environ', {'CHIEF_OPERATOR_PASSWORD': 'Different-Password-2026!'}):
            call_command('bootstrap_chief', verbosity=0)
        self.chief.refresh_from_db()
        self.assertTrue(self.chief.is_active and self.chief.is_staff and self.chief.is_superuser)
        self.assertTrue(self.chief.check_password('Original-Strong-2026!'))

    @override_settings(CHIEF_OPERATOR_USERNAME='new-chief')
    def test_bootstrap_creates_account_with_initial_password(self):
        with patch.dict('os.environ', {'CHIEF_OPERATOR_PASSWORD': 'Initial-Password-2026!'}):
            call_command('bootstrap_chief', verbosity=0)
        chief = User.objects.get(username='new-chief')
        self.assertTrue(chief.is_active and chief.is_staff and chief.is_superuser)
        self.assertTrue(chief.check_password('Initial-Password-2026!'))
