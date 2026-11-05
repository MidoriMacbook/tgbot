import uuid
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase

from app.core.models import CategoryItem, History, Ticket
from app.core.services import change_ticket, create_ticket


class StatisticsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('statistics-admin', password='Strong-Password-2026!')
        cls.assignee = User.objects.create_user('assignee', is_staff=True)
        cls.closer = User.objects.create_user('closer', first_name='Анна', is_staff=True)
        cls.item = CategoryItem.objects.first()

    def ticket(self):
        return create_ticket(telegram_id=42, applicant='Антон', item_id=self.item.pk,
                             description='Нет света', contact='@anton', key=uuid.uuid4())

    def test_api_requires_admin_and_bounded_period(self):
        self.assertEqual(self.client.get('/api/statistics/').status_code, 302)
        self.client.force_login(self.assignee)
        self.assertEqual(self.client.get('/api/statistics/').status_code, 403)
        self.client.force_login(self.admin)
        for days in ['0', '100000', 'wrong', '-7']:
            self.assertEqual(self.client.get('/api/statistics/', {'days': days}).status_code, 400)
        for days in [7, 30, 90]:
            payload = self.client.get('/api/statistics/', {'days': days}).json()
            self.assertEqual(len(payload['trend']), days)
            self.assertTrue(all(row['created'] == row['closed'] == 0 for row in payload['trend']))

    def test_closures_use_history_actor_and_moscow_date_independent_of_creation(self):
        ticket = self.ticket()
        change_ticket(ticket.pk, self.admin, 'assign', assignee_id=self.assignee.pk, version=0)
        change_ticket(ticket.pk, self.closer, 'done', comment='Заменена лампа', version=1)
        # 21:30 UTC — уже следующий календарный день в Москве.
        closure_time = datetime(2026, 11, 4, 21, 30, tzinfo=ZoneInfo('UTC'))
        Ticket.objects.filter(pk=ticket.pk).update(created_at=datetime(2026, 9, 1, tzinfo=ZoneInfo('UTC')))
        History.objects.filter(ticket=ticket, status='done').update(created_at=closure_time)
        self.client.force_login(self.admin)
        with patch('app.web.views.timezone.now', return_value=closure_time):
            response = self.client.get('/api/statistics/', {'days': 7})
        payload = response.json()
        self.assertEqual(payload['summary']['total'], 0)
        self.assertEqual(payload['summary']['closed'], 1)
        self.assertEqual(payload['trend'][-1], {'date': '2026-11-05', 'created': 0, 'closed': 1})
        self.assertEqual(payload['operators'], [{'name': 'Анна', 'completed': 1, 'rejected': 0, 'total': 1}])
        self.assertIn('no-store', response['Cache-Control'])

    def test_created_statuses_and_categories_use_selected_period(self):
        ticket = self.ticket()
        created = datetime(2026, 11, 4, 21, 0, tzinfo=ZoneInfo('UTC'))
        Ticket.objects.filter(pk=ticket.pk).update(created_at=created)
        self.client.force_login(self.admin)
        with patch('app.web.views.timezone.now', return_value=created):
            payload = self.client.get('/api/statistics/', {'days': 7}).json()
        self.assertEqual(payload['summary']['total'], 1)
        self.assertEqual(payload['summary']['new'], 1)
        self.assertEqual(payload['trend'][-1]['created'], 1)
        self.assertEqual(payload['categories'], [{'name': str(self.item), 'total': 1}])
