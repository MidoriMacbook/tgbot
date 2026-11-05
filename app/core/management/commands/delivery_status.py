from django.core.management.base import BaseCommand
from app.core.models import Notification


class Command(BaseCommand):
    help = "Показать очередь уведомлений без токенов и содержимого заявок"

    def handle(self, *args, **options):
        pending = Notification.objects.filter(sent_at__isnull=True)
        self.stdout.write(f"Ожидают доставки: {pending.count()}")
        self.stdout.write(f"Доставлены: {Notification.objects.filter(sent_at__isnull=False).count()}")
        for job in pending.select_related('ticket').order_by('id')[:20]:
            self.stdout.write(f"Задание {job.pk}, {job.ticket.number}, попыток: {job.attempts}, "
                              f"следующая: {job.next_attempt.isoformat()}, ошибка: {job.last_error or 'нет'}")
