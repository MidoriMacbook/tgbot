import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase
from django.urls import reverse

from app.core.models import CategoryGroup, CategoryItem, Ticket
from app.core.services import create_ticket


class WebTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user('operator', password='Strong-test-2026', is_staff=True)
        cls.other = User.objects.create_user('other', password='Strong-test-2026', is_staff=True)
        cls.admin = User.objects.create_superuser('administrator', password='Strong-test-2026')
        cls.visitor = User.objects.create_user('visitor', password='Strong-test-2026')
        cls.item = CategoryItem.objects.first()

    def ticket(self, **changes):
        values = dict(telegram_id=123, applicant='Ирина', item_id=self.item.pk,
                      description='Не работает проектор', contact='@irina', key=uuid.uuid4())
        values.update(changes)
        return create_ticket(**values)

    def login(self, user=None):
        self.client.force_login(user or self.operator)

    def test_sessions_only_active_staff_can_enter(self):
        self.assertRedirects(self.client.get('/'), '/login/?next=/')
        for user in [self.visitor, self.operator]:
            if user == self.operator:
                user.is_active = False
                user.save()
            response = self.client.post('/login/', {'username': user.username, 'password': 'Strong-test-2026'})
            self.assertNotIn('_auth_user_id', self.client.session)
            self.assertContains(response, 'Введите правильные имя пользователя и пароль')
        self.login(self.visitor)
        self.assertEqual(self.client.get('/').status_code, 403)

    def test_login_and_post_logout(self):
        self.assertRedirects(self.client.post('/login/', {'username': 'operator', 'password': 'Strong-test-2026'}), '/')
        self.assertEqual(self.client.get('/logout/').status_code, 405)
        self.assertRedirects(self.client.post('/logout/'), '/login/')

    def test_filters_and_inclusive_moscow_dates(self):
        first = self.ticket()
        other_item = CategoryItem.objects.exclude(group=self.item.group).first()
        second = self.ticket(item_id=other_item.pk)
        Ticket.objects.filter(pk=first.pk).update(status='work', assignee=self.operator,
            created_at=datetime(2026, 11, 5, 23, 59, tzinfo=ZoneInfo('Europe/Moscow')))
        Ticket.objects.filter(pk=second.pk).update(created_at=datetime(2026, 11, 6, 0, 0, tzinfo=ZoneInfo('Europe/Moscow')))
        self.login()
        response = self.client.get('/', {'status': 'work', 'group': self.item.group_id,
            'assignee': self.operator.pk, 'date_from': '2026-11-05', 'date_to': '2026-11-05'})
        self.assertContains(response, first.number)
        self.assertNotContains(response, second.number)

    def test_invalid_filters_show_errors_and_do_not_crash(self):
        self.login()
        for filters in [{'status': 'wrong'}, {'group': 'no'}, {'assignee': 'no'},
                        {'date_from': '2026-02-31'}, {'date_from': '2026-11-06', 'date_to': '2026-11-05'}]:
            with self.subTest(filters=filters):
                response = self.client.get('/', filters)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['filter_form'].errors)

    def test_detail_contains_owner_contact_and_history(self):
        ticket = self.ticket()
        self.login()
        response = self.client.get(reverse('ticket_detail', args=[ticket.pk]))
        for text in ['Ирина', '@irina', 'Не работает проектор', 'Создана заявка', ticket.category_label]:
            self.assertContains(response, text)

    def test_full_cycle_and_stale_action(self):
        ticket = self.ticket()
        self.login()
        url = reverse('ticket_action', args=[ticket.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url, {'action': 'take', 'version': 0}), reverse('ticket_detail', args=[ticket.pk]))
        stale = self.client.post(url, {'action': 'take', 'version': 0})
        self.assertEqual(stale.status_code, 409)
        self.assertContains(stale, 'Обновите карточку', status_code=409)
        self.client.post(url, {'action': 'assign', 'assignee_id': self.other.pk, 'version': 1})
        empty = self.client.post(url, {'action': 'done', 'version': 2, 'comment': ' '})
        self.assertEqual(empty.status_code, 400)
        self.client.post(url, {'action': 'done', 'version': 2, 'comment': 'Заменена лампа'})
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'done')
        self.assertEqual(ticket.assignee_id, self.other.pk)
        self.assertEqual(ticket.history.count(), 4)

    def test_action_rejects_missing_version_inactive_target_and_unknown_action(self):
        ticket = self.ticket()
        self.login()
        self.other.is_active = False
        self.other.save()
        for values in [{'action': 'take'}, {'action': 'take', 'version': 'bad'},
                       {'action': 'assign', 'version': 0, 'assignee_id': self.other.pk},
                       {'action': 'unknown', 'version': 0}]:
            self.assertEqual(self.client.post(reverse('ticket_action', args=[ticket.pk]), values).status_code, 400)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'new')

    def test_direct_post_denied_to_nonstaff(self):
        ticket = self.ticket()
        self.login(self.visitor)
        self.assertEqual(self.client.post(reverse('ticket_action', args=[ticket.pk]), {'action': 'take', 'version': 0}).status_code, 403)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'new')

    def test_statistics_admin_only(self):
        self.ticket()
        self.login()
        self.assertEqual(self.client.get(reverse('statistics')).status_code, 403)
        self.login(self.admin)
        response = self.client.get(reverse('statistics'))
        self.assertContains(response, 'Статистика')
        self.assertContains(response, self.item.name)
        self.assertEqual(response.context['total'], 1)

    def test_admin_ignores_operator_model_permissions(self):
        self.operator.user_permissions.set(Permission.objects.all())
        self.login()
        for url in ['/admin/', '/admin/core/categorygroup/', '/admin/auth/user/']:
            self.assertEqual(self.client.get(url).status_code, 302)
        group = self.item.group
        self.assertEqual(self.client.post(f'/admin/core/categorygroup/{group.pk}/change/',
            {'name': 'Подмена', 'active': 'on'}).status_code, 302)
        group.refresh_from_db()
        self.assertNotEqual(group.name, 'Подмена')
        self.assertEqual(self.client.post('/admin/login/', {'username': 'operator', 'password': 'Strong-test-2026'}).status_code, 200)

    def test_admin_creates_operator_with_clear_role_fields(self):
        self.login(self.admin)
        response = self.client.post('/admin/auth/user/add/', {'username': 'new-operator',
            'password1': 'Moonlight-Library-2026!', 'password2': 'Moonlight-Library-2026!',
            'usable_password': 'true', 'first_name': 'Анна', 'is_staff': 'on', 'is_active': 'on'})
        self.assertEqual(response.status_code, 302)
        employee = User.objects.get(username='new-operator')
        self.assertTrue(employee.is_staff)
        self.assertFalse(employee.is_superuser)
        self.assertTrue(employee.check_password('Moonlight-Library-2026!'))

    def test_rejected_result_in_history_and_disabled_session_denied(self):
        ticket = self.ticket()
        self.login()
        url = reverse('ticket_action', args=[ticket.pk])
        self.client.post(url, {'action': 'take', 'version': 0})
        self.client.post(url, {'action': 'rejected', 'version': 1, 'comment': 'Требуется другое оборудование'})
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'rejected')
        self.assertEqual(ticket.history.last().comment, 'Требуется другое оборудование')
        self.operator.is_active = False
        self.operator.save()
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_login_does_not_redirect_to_an_external_site(self):
        response = self.client.post('/login/?next=https://example.com/',
            {'username': 'operator', 'password': 'Strong-test-2026', 'next': 'https://example.com/'})
        self.assertRedirects(response, '/')

    def test_admin_disables_and_never_deletes_referenced_records(self):
        ticket = self.ticket()
        self.login(self.admin)
        for model, obj, field in [('categorygroup', self.item.group, 'active'), ('categoryitem', self.item, 'active'),
                                  ('user', self.operator, 'is_active')]:
            prefix = 'auth' if model == 'user' else 'core'
            url = f'/admin/{prefix}/{model}/'
            self.assertEqual(self.client.get(f'{url}{obj.pk}/delete/').status_code, 403)
            self.client.post(url, {'action': 'deactivate', '_selected_action': [obj.pk], 'index': 0})
            obj.refresh_from_db()
            self.assertFalse(getattr(obj, field))
        self.assertTrue(Ticket.objects.filter(pk=ticket.pk).exists())
        self.assertEqual(ticket.history.count(), 1)

    def test_pagination_empty_state_and_escaped_description(self):
        self.login()
        self.assertContains(self.client.get('/'), 'Заявок пока нет')
        for _ in range(26):
            self.ticket(description='<script>alert(1)</script>')
        response = self.client.get('/')
        self.assertEqual(len(response.context['page_obj']), 25)
        self.assertContains(response, 'Следующая')
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_csrf_failure_has_russian_recovery(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.operator)
        response = client.post('/logout/')
        self.assertContains(response, 'Обновите страницу', status_code=403)
