import math
import uuid
from datetime import timedelta
from django.db import transaction
from django.conf import settings
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from app.core.models import Notification


def bot_config():
    return getattr(settings, "BOT_CONFIG", {})


@transaction.atomic
def claim_next(*, now=None):
    now = now or timezone.now()
    earlier = Notification.objects.filter(ticket_id=OuterRef("ticket_id"), pk__lt=OuterRef("pk"),
        sent_at__isnull=True)
    job = Notification.objects.filter(sent_at__isnull=True, next_attempt__lte=now).annotate(
        has_earlier=Exists(earlier)).filter(has_earlier=False).filter(
        Q(lease_until__isnull=True) | Q(lease_until__lte=now)).order_by("id").first()
    if not job:
        return None
    job.lease_key = uuid.uuid4()
    job.lease_until = now + timedelta(seconds=bot_config().get("lease_seconds", 30))
    job.attempts += 1
    job.save(update_fields=["lease_key", "lease_until", "attempts"])
    return job


def retry_seconds(error, attempts):
    delay = min(bot_config().get("retry_max_seconds", 30), 2 ** min(attempts, 10))
    try:
        rate_delay = float(getattr(error, "retry_after", 0))
        if math.isfinite(rate_delay):
            delay = max(delay, rate_delay)
    except (ValueError, TypeError, OverflowError):
        pass
    return delay


def safe_error(error):
    # Исключения транспорта могут включать URL с токеном; сохраняется только фиксированный текст.
    if getattr(error, "retry_after", None) is not None:
        return "Telegram ограничил частоту запросов; отправка будет повторена."
    if isinstance(error, TimeoutError):
        return "Превышено время ожидания Telegram; отправка будет повторена."
    return "Не удалось доставить сообщение в Telegram; отправка будет повторена."


def deliver_pending(sender, *, now=None, limit=100):
    """sender(chat_id, text) завершает отправку всех частей раньше окончания аренды."""
    sent = 0
    for _ in range(limit):
        attempt_time = now or timezone.now()
        job = claim_next(now=attempt_time)
        if not job:
            break
        try:
            sender(job.ticket.telegram_id, job.text)
        except Exception as error:
            finish_job(job, error, now=now)
        else:
            finish_job(job, now=now)
            sent += 1
    return sent


def finish_job(job, error=None, *, now=None):
    moment = now or timezone.now()
    fields = {"lease_key": None, "lease_until": None}
    if error is None:
        fields.update(sent_at=moment, last_error="")
    else:
        fields.update(last_error=safe_error(error),
            next_attempt=moment + timedelta(seconds=retry_seconds(error, job.attempts)))
    Notification.objects.filter(pk=job.pk, lease_key=job.lease_key).update(**fields)


def take_notification():
    job = claim_next()
    if job is None:
        return None
    return job.pk, job.ticket.telegram_id, job.text


def complete_notification(pk, error=None):
    finish_job(Notification.objects.get(pk=pk), error)
