import uuid
from dataclasses import dataclass

from django.db import transaction
from django.conf import settings
from django.utils import timezone
from app.core.models import BotDialog, CategoryGroup, CategoryItem, Ticket
from app.core.phones import russian_name, russian_phone
from app.core.services import RuleError, create_ticket, owner_status, required

PAGE_SIZE = 5
INVALID_INPUT = "Неверные данные, отправьте верные чтобы продолжить"
STATUS_ICON = {"new": "new", "work": "work", "done": "done", "rejected": "rejected"}


@dataclass(frozen=True)
class Button:
    text: str
    data: str
    icon: str = ""
    url: str = ""


@dataclass(frozen=True)
class Reply:
    text: str
    keyboard: tuple[tuple[Button, ...], ...]
    stage: str = "idle"
    details: tuple[tuple[str, str], ...] = ()


def bot_config():
    return getattr(settings, "BOT_CONFIG", {})


def label(name, fallback):
    return bot_config().get("button_labels", {}).get(name, fallback)


def normalize_input(value):
    actions = {"new": "Подать заявку", "status": "Узнать статус", "menu": "/start",
        "back": "Назад", "confirm": "Подтвердить"}
    aliases = {text: actions[key] for key, text in bot_config().get("button_labels", {}).items() if key in actions}
    aliases.update({button["text"]: actions[button["action"]]
        for button in bot_config().get("lower_buttons", []) if button.get("action") in actions})
    aliases["Отменить ввод"] = "/start"
    decorated = {f"{icon.get('fallback')} {text}": action
        for icon in bot_config().get("emojis", {}).values() if icon.get("fallback")
        for text, action in aliases.items()}
    aliases.update(decorated)
    return aliases.get(value, value)


def owned_tickets(dialog):
    return Ticket.objects.filter(telegram_id=dialog.telegram_id, platform=dialog.platform)


def owner_page(dialog):
    total = owned_tickets(dialog).count()
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(0, int(dialog.data.get("_page") or 0)), pages - 1)
    return page, pages, total


def keeps_current_screen(raw):
    return raw in {"Подать заявку", "Узнать статус", "Назад", "Подтвердить", "/start"}


def opens_fresh_message(previous, current):
    # Имя, телефон и подтверждение приходят отдельными сообщениями.
    # «Заявка принята» остаётся правкой сообщения подтверждения.
    return (previous, current) in {("description", "name"), ("name", "contact"), ("contact", "confirm")}


def navigation(dialog):
    key = dialog.data.get("_menu_token", "")
    return_step = dialog.data.get("_return_step") or "idle"
    # На один шаг назад — только «Назад». Если этот шаг уже главное меню или возвращаться некуда — только «Главное меню».
    one_step_back = dialog.step in {"item", "description", "name", "contact", "confirm", "ticket"} or (
        dialog.step == "tickets" and return_step != "idle")
    if one_step_back:
        return ((Button(label("back", "Назад"), f"back:{dialog.step}:{key}", "back"),),)
    if dialog.step != "idle":
        return ((Button(label("menu", "Главное меню"), f"menu:{key}", "menu"),),)
    return ()


def choices(dialog):
    key = dialog.data.get("_menu_token", "")
    icons = bot_config().get("category_icons", {})
    nav = navigation(dialog)
    if dialog.step == "tickets":
        page, _pages, total = owner_page(dialog)
        tickets = owned_tickets(dialog).order_by("-id")[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
        rows = tuple((Button(ticket.number, f"open:{ticket.pk}:{key}", STATUS_ICON.get(ticket.status, "status")),) for ticket in tickets)
        page_nav = []
        if page > 0:
            page_nav.append(Button("Предыдущая", f"pg:{page - 1}:{key}", "back"))
        if (page + 1) * PAGE_SIZE < total:
            page_nav.append(Button("Следующая", f"pg:{page + 1}:{key}", "status"))
        if page_nav:
            rows += (tuple(page_nav),)
        return rows + nav
    if dialog.step == "ticket":
        return nav
    if dialog.step == "group":
        groups = CategoryGroup.objects.filter(active=True, categoryitem__active=True).distinct()
        return tuple((Button(group.name, f"group:{group.pk}:{key}", icons.get(group.name, "")),) for group in groups) + nav
    if dialog.step == "item":
        items = CategoryItem.objects.filter(group_id=dialog.data.get("group_id"), active=True,
            group__active=True)
        return tuple((Button(item.name, f"item:{item.pk}:{key}", icons.get(item.name, "")),) for item in items) + nav
    if dialog.step == "confirm":
        return ((Button(label("confirm", "Подтвердить"), f"confirm:{key}", "confirm"),),) + nav
    if dialog.step in ("description", "name", "contact", "submitted"):
        return nav
    return ((Button(label("new", "Подать заявку"), "new", "new"),),
        (Button(label("status", "Узнать статус"), "status", "status"),))


def public_status(ticket):
    return {"new": "Открыта", "work": "Открыта", "done": "успешно закрыта",
        "rejected": "отклонена"}.get(ticket.status, ticket.get_status_display())


def staff_post(user):
    if user is None:
        return "Сотрудник"
    if settings.CHIEF_OPERATOR_EMAIL and (user.email or "").lower() == settings.CHIEF_OPERATOR_EMAIL:
        return "Главный оператор"
    if user.is_superuser:
        return "Администратор"
    return "Оператор"


def ticket_dialog(ticket):
    moment = timezone.localtime(ticket.created_at).strftime("%d.%m.%Y, %H:%M")
    lines = [f"Заявка {ticket.number}", f"Статус заявки: {public_status(ticket)}", "",
        f"Вы {moment}", ticket.description]
    replies = ticket.history.select_related("actor").exclude(comment="").order_by("id")
    for event in replies:
        if event.actor_id is None:
            continue
        when = timezone.localtime(event.created_at).strftime("%d.%m.%Y, %H:%M")
        lines.extend(["", f"{event.actor.username} {staff_post(event.actor)} {when}", event.comment])
    return "\n".join(lines)


def prompt(dialog):
    if dialog.step == "confirm":
        item = CategoryItem.objects.select_related("group").filter(pk=dialog.data.get("item_id")).first()
        return (f"Проверьте заявку.\nКатегория: {item}\nОписание проблемы: {dialog.data['description']}"
            f"\nИмя: {dialog.data['applicant']}\nТелефон: {dialog.data['contact']}\nОтправить заявку?")
    if dialog.step == "submitted":
        return "Заявка сохранена.\n" + owner_status(dialog.telegram_id, dialog.data["number"], dialog.platform)
    if dialog.step == "tickets":
        page, pages, total = owner_page(dialog)
        if not total:
            return "У вас пока нет заявок."
        return f"Всего {total}. Страница {page + 1} из {pages}."
    if dialog.step == "ticket":
        ticket = owned_tickets(dialog).filter(pk=dialog.data.get("_ticket")).first()
        if not ticket:
            return "Заявка не найдена среди ваших обращений."
        return ticket_dialog(ticket)
    return bot_config().get("texts", {}).get(dialog.step, {}).get("prompt", "Выберите действие.")


@transaction.atomic
def process_input(telegram_id, applicant, text, *, callback=None, platform="telegram", nickname="", chat_id=0):
    dialog, _ = BotDialog.objects.get_or_create(platform=platform, telegram_id=telegram_id)
    nick = str(nickname or "").strip().lstrip("@")[:64]
    if nick and dialog.data.get("_nickname") != nick:
        dialog.data["_nickname"] = nick
    if platform == "max" and chat_id:
        dialog.data["_chat_id"] = int(chat_id)
        Ticket.objects.filter(platform="max", telegram_id=telegram_id).exclude(
            max_chat_id=int(chat_id)).update(max_chat_id=int(chat_id))
    value = normalize_input(text.strip()) if isinstance(text, str) else ""
    initial_step, initial_data = dialog.step, dict(dialog.data)

    def reply(message=None):
        if dialog.step != initial_step or dialog.data != initial_data or "_menu_token" not in dialog.data:
            dialog.data["_menu_token"] = uuid.uuid4().hex
        dialog.save(update_fields=["step", "data", "updated_at"])
        details = ()
        if dialog.step == "confirm" and message is None:
            item = CategoryItem.objects.select_related("group").filter(pk=dialog.data.get("item_id")).first()
            details = (("Категория", str(item)), ("Описание проблемы", dialog.data["description"]),
                ("Имя", dialog.data["applicant"]), ("Телефон", dialog.data["contact"]))
        return Reply(message or prompt(dialog), choices(dialog), dialog.step, details)

    selection = None
    if callback is not None:
        parts = callback.split(":")
        key = dialog.data.get("_menu_token", "")
        if callback in ("new", "status"):
            value = "Подать заявку" if callback == "new" else "Узнать статус"
        elif len(parts) == 3 and parts[0] in ("group", "item") and parts[1].isascii() and parts[1].isdigit() and len(parts[1]) < 16 and parts[2] == key and dialog.step == parts[0]:
            selection = (parts[0], int(parts[1]))
        elif len(parts) == 2 and parts[0] == "menu" and parts[1] == key:
            dialog.step, dialog.data = "idle", {}
            return reply()
        elif len(parts) == 3 and parts[0] == "back" and parts[1] == dialog.step and parts[2] == key:
            value = "Назад"
        elif len(parts) == 2 and parts[0] == "confirm" and (
            (parts[1] == key and dialog.step == "confirm") or
            (parts[1] == dialog.data.get("_confirmed_token") and dialog.step == "submitted")):
            value = "Подтвердить"
        elif len(parts) == 3 and parts[0] == "pg" and parts[1].isdigit() and len(parts[1]) < 6 and parts[2] == key and dialog.step == "tickets":
            dialog.data["_page"] = int(parts[1])
            return reply()
        elif len(parts) == 3 and parts[0] == "open" and parts[1].isdigit() and len(parts[1]) < 16 and parts[2] == key and dialog.step in ("tickets", "ticket"):
            ticket = owned_tickets(dialog).filter(pk=int(parts[1])).first()
            if not ticket:
                return reply("Заявка не найдена среди ваших обращений.")
            dialog.step = "ticket"
            dialog.data["_ticket"] = ticket.pk
            return reply()
        else:
            return reply("Это меню уже устарело. Используйте кнопки под последним сообщением.")

    if value.split(maxsplit=1)[0:1] == ["/status"]:
        number = value.partition(" ")[2].strip()
        try:
            result = owner_status(telegram_id, number, platform) if number else "Введите /status З-000001 — номер своей заявки."
        except RuleError as error:
            result = str(error)
        return reply(result)
    if value == "Узнать статус":
        if dialog.step not in ("tickets", "ticket"):
            dialog.data["_return_step"] = dialog.step
        dialog.step = "tickets"
        dialog.data["_page"] = 0
        return reply()
    if value == "/start":
        dialog.step, dialog.data = "idle", {}
        return reply()
    if value == "Подать заявку":
        dialog.step = "group"
        dialog.data = {"key": str(uuid.uuid4()), "applicant": str(applicant or telegram_id).strip()[:200] or str(telegram_id)}
        return reply()
    if value == "Назад":
        if dialog.step == "ticket":
            dialog.step = "tickets"
            return reply()
        if dialog.step == "tickets":
            dialog.step = dialog.data.get("_return_step") or "idle"
            if dialog.step not in {"idle", "group", "item", "description", "name", "contact", "confirm", "submitted"}:
                dialog.step = "idle"
            return reply()
        dialog.step = {"group": "idle", "item": "group", "description": "item",
            "name": "description", "contact": "name", "confirm": "contact",
            "submitted": "idle", "idle": "idle"}[dialog.step]
        return reply()
    if dialog.step in ("idle", "submitted"):
        return reply()
    if not value and selection is None:
        return reply(INVALID_INPUT)

    if dialog.step in ("item", "description", "name", "contact", "confirm"):
        valid_group = CategoryGroup.objects.filter(pk=dialog.data.get("group_id"), active=True).exists()
        valid_item = dialog.step == "item" or CategoryItem.objects.filter(pk=dialog.data.get("item_id"),
            group_id=dialog.data.get("group_id"), active=True, group__active=True).exists()
        if not valid_group or not valid_item:
            dialog.step = "group"
            return reply("Выбранная категория больше недоступна. Выберите группу заново.")
    if dialog.step == "group":
        groups = CategoryGroup.objects.filter(active=True, categoryitem__active=True).distinct()
        group = groups.filter(pk=selection[1]).first() if selection else groups.filter(name=value).first()
        if not group:
            return reply(INVALID_INPUT)
        dialog.data["group_id"] = group.pk
        dialog.step = "item"
    elif dialog.step == "item":
        items = CategoryItem.objects.filter(group_id=dialog.data["group_id"], active=True, group__active=True)
        item = items.filter(pk=selection[1]).first() if selection else items.filter(name=value).first()
        if not item:
            return reply(INVALID_INPUT)
        dialog.data["item_id"] = item.pk
        dialog.step = "description"
    elif dialog.step == "description":
        try:
            dialog.data["description"] = required(value, "Описание", 4000)
        except RuleError:
            return reply(INVALID_INPUT)
        dialog.step = "name"
    elif dialog.step == "name":
        try:
            dialog.data["applicant"] = russian_name(value)
        except ValueError:
            return reply(INVALID_INPUT)
        dialog.step = "contact"
    elif dialog.step == "contact":
        try:
            dialog.data["contact"] = russian_phone(value)
        except ValueError:
            return reply(INVALID_INPUT)
        dialog.step = "confirm"
    elif dialog.step == "confirm":
        if value != "Подтвердить":
            return reply(INVALID_INPUT)
        try:
            ticket = create_ticket(telegram_id=telegram_id, applicant=dialog.data["applicant"],
                item_id=dialog.data["item_id"], description=dialog.data["description"],
                contact=dialog.data["contact"], key=dialog.data["key"], platform=platform,
                nickname=dialog.data.get("_nickname", ""),
                max_chat_id=dialog.data.get("_chat_id") or None)
        except RuleError as error:
            dialog.step = "group"
            return reply(str(error))
        dialog.step = "submitted"
        dialog.data = {"number": ticket.number, "key": str(ticket.key),
            "_confirmed_token": dialog.data.get("_menu_token")}
    return reply()
