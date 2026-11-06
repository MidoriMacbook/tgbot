import uuid
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from app.core.models import CategoryItem, Ticket, History, Notification


def assignable_staff():
    staff = User.objects.filter(is_staff=True, is_active=True)
    if settings.CHIEF_OPERATOR_EMAIL:
        staff = staff.exclude(email__iexact=settings.CHIEF_OPERATOR_EMAIL)
    return staff.order_by("last_name", "first_name", "username")


class RuleError(ValueError):
    pass


def required(value, label, limit):
    value = str(value or "").strip()
    if not value:
        raise RuleError(f"Заполните поле «{label}».")
    if len(value) > limit:
        raise RuleError(f"Поле «{label}»: не более {limit} символов.")
    return value


@transaction.atomic
def create_ticket(*, telegram_id, applicant, item_id, description, contact, key):
    try:
        key = uuid.UUID(str(key))
    except (ValueError, TypeError, AttributeError):
        raise RuleError("Начните подачу заявки заново.")
    existing = Ticket.objects.filter(key=key).first()
    if existing:
        if existing.telegram_id != telegram_id:
            raise RuleError("Заявка недоступна.")
        return existing
    description = required(description, "Описание", 4000)
    contact = required(contact, "Контакт", 300)
    applicant = required(applicant, "Заявитель", 200)
    item = CategoryItem.objects.select_related("group").filter(
        pk=item_id, active=True, group__active=True).first()
    if not item:
        raise RuleError("Элемент больше недоступен. Выберите категорию заново.")
    ticket = Ticket.objects.create(key=key, telegram_id=telegram_id, applicant=applicant,
        item=item, category_label=str(item), description=description, contact=contact)
    History.objects.create(ticket=ticket, actor_label=applicant, action="Создана заявка", status=ticket.status)
    return ticket


@transaction.atomic
def change_ticket(ticket_id, actor, action, *, assignee_id=None, comment="", version=None):
    actor = User.objects.filter(pk=actor.pk, is_active=True, is_staff=True).first()
    if not actor:
        raise RuleError("Доступ разрешён только активным сотрудникам.")
    ticket = Ticket.objects.select_related("assignee").filter(pk=ticket_id).first()
    if not ticket:
        raise RuleError("Заявка не найдена.")
    if version is None or ticket.version != version:
        raise RuleError("Заявка уже изменена другим сотрудником. Обновите карточку.")
    old_status = ticket.status
    if action in ("take", "assign"):
        if ticket.status not in (Ticket.Status.NEW, Ticket.Status.WORK):
            raise RuleError("Закрытую заявку нельзя назначить повторно.")
        if action == "take" and ticket.status != Ticket.Status.NEW:
            raise RuleError("Заявку уже взяли в работу. Обновите карточку.")
        target_id = actor.pk if action == "take" else assignee_id
        target = User.objects.filter(pk=target_id, is_active=True, is_staff=True).first()
        if not target:
            raise RuleError("Выберите активного сотрудника.")
        if action == "assign" and settings.CHIEF_OPERATOR_EMAIL and target.email.lower() == settings.CHIEF_OPERATOR_EMAIL:
            raise RuleError("Главный оператор не назначается исполнителем.")
        if target.pk == ticket.assignee_id:
            raise RuleError("Этот сотрудник уже назначен.")
        label = "Назначен исполнитель" if old_status == Ticket.Status.NEW else "Переназначен исполнитель"
        ticket.assignee = target
        ticket.status = Ticket.Status.WORK
        comment = f"Исполнитель: {target.get_full_name() or target.username}"
    elif action in ("done", "rejected"):
        if ticket.status != Ticket.Status.WORK:
            raise RuleError("Закрыть можно только заявку в работе.")
        comment = required(comment, "Результат", 4000)
        ticket.status = action
        label = "Заявка выполнена" if action == "done" else "Заявка отклонена"
    else:
        raise RuleError("Неизвестное действие.")
    ticket.version += 1
    ticket.save(update_fields=["status", "assignee", "version", "updated_at"])
    History.objects.create(ticket=ticket, actor=actor,
        actor_label=actor.get_full_name() or actor.username, action=label, comment=comment,
        status=ticket.status,
        assignee_label=(ticket.assignee.get_full_name() or ticket.assignee.username) if ticket.assignee else "")
    if old_status != ticket.status:
        Notification.objects.create(ticket=ticket, next_attempt=timezone.now(),
            text=f"Заявка {ticket.number}: {ticket.get_status_display()}.\n{comment}")
    return ticket


def owner_status(telegram_id, number):
    value = str(number).strip().upper().removeprefix("З-")
    if not value.isascii() or not value.isdigit() or len(value) > 12:
        raise RuleError("Введите номер заявки, например З-000001.")
    ticket = Ticket.objects.filter(pk=int(value), telegram_id=telegram_id).first()
    if not ticket:
        raise RuleError("Заявка не найдена среди ваших обращений.")
    result = f"Заявка {ticket.number}: {ticket.get_status_display()}."
    if ticket.status in (Ticket.Status.DONE, Ticket.Status.REJECTED):
        result += f"\nРезультат: {ticket.history.last().comment}"
    return result
