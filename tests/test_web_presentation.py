from django.contrib.auth.models import User
from django.test import TestCase


class WebPresentationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('design-admin', password='Strong-test-2026')

    def test_login_supports_password_managers_and_mobile_username_entry(self):
        response = self.client.get('/login/')
        self.assertContains(response, 'autocomplete="username"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, 'autocapitalize="none"')
        self.assertContains(response, 'spellcheck="false"')
        self.assertNotContains(response, 'autofocus')
        self.assertContains(response, 'href="#main"')

    def test_current_navigation_is_identified_for_assistive_technology(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/'), 'aria-current="page"')
        self.assertContains(self.client.get('/statistics/'), 'aria-current="page"')

    def test_admin_uses_local_theme_and_keeps_panel_return_link(self):
        self.client.force_login(self.admin)
        response = self.client.get('/admin/')
        self.assertContains(response, 'web/admin.css')
        self.assertContains(response, 'Справочники')
        self.assertContains(response, 'кнопки бота')
        self.assertContains(response, 'Открыть список')
        self.assertNotContains(response, 'Недоступно')
        self.assertContains(response, 'href="/"')
