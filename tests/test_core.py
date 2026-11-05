import uuid
from concurrent.futures import ThreadPoolExecutor
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.test import TransactionTestCase
from app.core import services
from app.core.models import CategoryGroup, CategoryItem, Ticket, History, Notification


class TicketTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.operator = User.objects.create_user("operator", is_staff=True)
        self.other = User.objects.create_user("other", is_staff=True)
        self.item = CategoryItem.objects.first()

    def create(self, **changes):
        values = dict(telegram_id=123, applicant="Ирина", item_id=self.item.pk,
                      description="Не работает проектор", contact="@irina", key=uuid.uuid4())
        values.update(changes)
        return services.create_ticket(**values)

    def test_classifier_has_three_by_three(self):
        self.assertEqual(CategoryGroup.objects.count(), 3)
        self.assertTrue(all(g.categoryitem_set.count() == 3 for g in CategoryGroup.objects.all()))

    def test_creation_idempotency_and_owner(self):
        key = uuid.uuid4()
        ticket = self.create(key=key)
        self.assertEqual(self.create(key=key).pk, ticket.pk)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(ticket.history.count(), 1)
        self.assertIn("Новая", services.owner_status(123, ticket.number))
        with self.assertRaises(services.RuleError):
            services.owner_status(456, ticket.number)
        with self.assertRaises(services.RuleError):
            self.create(key=key, telegram_id=456)

    def test_blank_description_and_contact_rejected(self):
        for field in ["description", "contact", "applicant"]:
            with self.subTest(field=field), self.assertRaises(services.RuleError):
                self.create(**{field: "  "})
        self.item.active = False
        self.item.save()
        with self.assertRaises(services.RuleError):
            self.create()

    def test_full_cycle_history_and_notifications(self):
        ticket = self.create()
        ticket = services.change_ticket(ticket.pk, self.operator, "take", version=0)
        self.assertEqual(ticket.status, Ticket.Status.WORK)
        ticket = services.change_ticket(ticket.pk, self.operator, "assign", assignee_id=self.other.pk, version=1)
        self.assertEqual(ticket.assignee_id, self.other.pk)
        with self.assertRaises(services.RuleError):
            services.change_ticket(ticket.pk, self.operator, "done", comment=" ", version=2)
        ticket = services.change_ticket(ticket.pk, self.other, "done", comment="Лампа заменена", version=2)
        self.assertEqual(ticket.history.count(), 4)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(ticket.history.last().actor_id, self.other.pk)
        self.assertEqual(ticket.history.last().comment, "Лампа заменена")
        with self.assertRaises(services.RuleError):
            services.change_ticket(ticket.pk, self.operator, "take", version=3)

    def test_permissions_stale_and_atomicity(self):
        ticket = self.create()
        outsider = User.objects.create_user("outsider")
        with self.assertRaises(services.RuleError):
            services.change_ticket(ticket.pk, outsider, "take", version=0)
        with self.assertRaises(services.RuleError):
            services.change_ticket(ticket.pk, self.operator, "done", comment="Готово", version=0)
        self.other.is_active = False
        self.other.save()
        with self.assertRaises(services.RuleError):
            services.change_ticket(ticket.pk, self.operator, "assign", assignee_id=self.other.pk, version=0)
        services.change_ticket(ticket.pk, self.operator, "take", version=0)
        with self.assertRaises(services.RuleError):
            services.change_ticket(ticket.pk, self.other, "take", version=0)
        self.assertEqual(History.objects.count(), 2)
        self.assertEqual(Notification.objects.count(), 1)

    def test_concurrent_take_has_single_winner(self):
        ticket = self.create()

        def take(user_id):
            close_old_connections()
            try:
                services.change_ticket(ticket.pk, User.objects.get(pk=user_id), "take", version=0)
                return "ok"
            except services.RuleError:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(take, [self.operator.pk, self.other.pk]))
        self.assertCountEqual(results, ["ok", "conflict"])
        self.assertEqual(ticket.history.count(), 2)
