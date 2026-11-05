import uuid
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from app.core.models import Ticket, CategoryItem, History, Notification
from app.core.services import create_ticket, change_ticket, RuleError


class ReliabilityTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('worker', is_staff=True)
        self.item = CategoryItem.objects.first()
        self.ticket = create_ticket(telegram_id=7, applicant='Заявитель', item_id=self.item.pk,
            description='Пропало питание', contact='кабинет 101', key=uuid.uuid4())

    def test_transaction_rolls_back_if_history_fails(self):
        with patch('app.core.services.History.objects.create', side_effect=RuntimeError('Сбой записи')):
            with self.assertRaises(RuntimeError):
                change_ticket(self.ticket.pk, self.operator, 'take', version=0)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.NEW)
        self.assertIsNone(self.ticket.assignee)
        self.assertEqual(self.ticket.history.count(), 1)
        self.assertEqual(Notification.objects.count(), 0)

    def test_history_survives_renaming_and_deactivation(self):
        original = self.ticket.category_label
        change_ticket(self.ticket.pk, self.operator, 'take', version=0)
        self.item.name = 'Новое название'
        self.item.active = False
        self.item.save()
        self.operator.is_active = False
        self.operator.save()
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.category_label, original)
        self.assertEqual(self.ticket.history.last().actor_label, 'worker')
        with self.assertRaises(ProtectedError):
            self.operator.delete()
        with self.assertRaises(ProtectedError):
            self.item.delete()
        with self.assertRaises(RuleError):
            change_ticket(self.ticket.pk, self.operator, 'done', comment='Ремонт', version=1)

    def test_assignment_on_new_and_rejection(self):
        ticket = change_ticket(self.ticket.pk, self.operator, 'assign', assignee_id=self.operator.pk, version=0)
        self.assertEqual(ticket.status, Ticket.Status.WORK)
        ticket = change_ticket(ticket.pk, self.operator, 'rejected', comment='Дубликат обращения', version=1)
        self.assertEqual(ticket.status, Ticket.Status.REJECTED)
        self.assertEqual(ticket.history.count(), 3)
        self.assertEqual(Notification.objects.count(), 2)
