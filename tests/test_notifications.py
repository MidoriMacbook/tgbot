import uuid
from datetime import timedelta
from django.db import connection
from django.db import close_old_connections
from concurrent.futures import ThreadPoolExecutor
from django.test import TransactionTestCase
from django.utils import timezone
from app.core.models import CategoryItem, Notification
from app.core.services import create_ticket
from app.core.notifications import deliver_pending, claim_next


class NotificationTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        ticket = create_ticket(telegram_id=123, applicant="Ирина", item_id=CategoryItem.objects.first().pk,
            description="Не включается", contact="@irina", key=uuid.uuid4())
        self.now = timezone.now()
        self.job = Notification.objects.create(ticket=ticket, text="Заявка принята", next_attempt=self.now)

    def test_delivery_has_no_open_transaction_and_is_not_repeated(self):
        calls = []
        def send(chat_id, text):
            self.assertFalse(connection.in_atomic_block)
            calls.append((chat_id, text))
        self.assertEqual(deliver_pending(send, now=self.now), 1)
        self.assertEqual(deliver_pending(send, now=self.now), 0)
        self.assertEqual(calls, [(123, "Заявка принята")])
        self.job.refresh_from_db()
        self.assertIsNotNone(self.job.sent_at)

    def test_failure_persists_retry_and_scrubs_exception(self):
        def fail(*args):
            raise RuntimeError("https://api.telegram.org/bot123:secret-token/sendMessage")
        deliver_pending(fail, now=self.now)
        self.job.refresh_from_db()
        self.assertIsNone(self.job.sent_at)
        self.assertEqual(self.job.attempts, 1)
        self.assertNotIn("secret", self.job.last_error)
        self.assertEqual(self.job.next_attempt, self.now + timedelta(seconds=2))
        self.assertEqual(deliver_pending(lambda *args: None, now=self.now), 0)
        self.assertEqual(deliver_pending(lambda *args: None, now=self.now + timedelta(seconds=2)), 1)

    def test_lease_blocks_second_worker_and_recovers_after_crash(self):
        first = claim_next(now=self.now)
        self.assertIsNotNone(first)
        self.assertIsNone(claim_next(now=self.now))
        second = claim_next(now=self.now + timedelta(seconds=31))
        self.assertIsNotNone(second)
        self.assertNotEqual(first.lease_key, second.lease_key)

    def test_rate_limit_retry_after_is_respected(self):
        class Limited(Exception):
            retry_after = 47
        def fail(*args):
            raise Limited("токен не должен попасть в журнал")
        deliver_pending(fail, now=self.now)
        self.job.refresh_from_db()
        self.assertEqual(self.job.next_attempt, self.now + timedelta(seconds=47))

    def test_two_concurrent_workers_have_one_lease(self):
        def claim(_):
            close_old_connections()
            try:
                job = claim_next(now=self.now)
                return job.pk if job else None
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, [1, 2]))
        self.assertCountEqual(results, [self.job.pk, None])

    def test_failed_earlier_status_blocks_same_ticket_but_not_other_ticket(self):
        Notification.objects.create(ticket=self.job.ticket, text="Выполнена", next_attempt=self.now)
        other = create_ticket(telegram_id=456, applicant="Олег", item_id=CategoryItem.objects.first().pk,
            description="Нет бумаги", contact="@oleg", key=uuid.uuid4())
        Notification.objects.create(ticket=other, text="Другая заявка", next_attempt=self.now)
        calls = []
        def send(chat_id, text):
            calls.append((chat_id, text))
            if text == self.job.text:
                raise TimeoutError("Недоступно")
        deliver_pending(send, now=self.now)
        self.assertEqual(calls, [(123, self.job.text), (456, "Другая заявка")])
        calls.clear()
        deliver_pending(lambda chat_id, text: calls.append((chat_id, text)),
            now=self.now + timedelta(seconds=2))
        self.assertEqual(calls, [(123, self.job.text), (123, "Выполнена")])
