import uuid
from dataclasses import dataclass

from django.db import transaction
from app.core.models import BotDialog, CategoryGroup, CategoryItem
from app.core.services import RuleError, create_ticket, owner_status, required


@dataclass(frozen=True)
class Button:
    text: str
    data: str


@dataclass(frozen=True)
class Reply:
    text: str
    keyboard: tuple[tuple[Button, ...], ...]
    stage: str = "idle"
    details: tuple[tuple[str, str], ...] = ()


MENU = ((Button("Подать заявку", "new"),), (Button("Узнать статус", "status"),))


def choices(dialog):
    key = dialog.data.get("_menu_token", "")
    back = ((Button("Назад", f"back:{dialog.step}:{key}"),),)
    if dialog.step == "group":
        groups = CategoryGroup.objects.filter(active=True, categoryitem__active=True).distinct()
        return tuple((Button(group.name, f"group:{group.pk}:{key}"),) for group in groups) + back
    if dialog.step == "item":
        items = CategoryItem.objects.filter(group_id=dialog.data.get("group_id"), active=True,
            group__active=True)
        return tuple((Button(item.name, f"item:{item.pk}:{key}"),) for item in items) + back
    if dialog.step == "confirm":
        return ((Button("Подтвердить", f"confirm:{key}"),),) + back
    if dialog.step in ("description", "contact"):
        return back
    return MENU


def prompt(dialog):
    if dialog.step == "confirm":
        item = CategoryItem.objects.select_related("group").filter(pk=dialog.data.get("item_id")).first()
        return (f"Проверьте заявку.\nКатегория: {item}\nОписание: {dialog.data['description']}"
            f"\nКонтакт: {dialog.data['contact']}\nОтправить заявку?")
    if dialog.step == "submitted":
        return "Заявка сохранена.\n" + owner_status(dialog.telegram_id, dialog.data["number"])
    return {
        "idle": "Здравствуйте! Здесь можно подать заявку на обслуживание помещений и оборудования и узнать её статус.",
        "group": "Выберите группу заявки.",
        "item": "Выберите элемент категории.",
        "description": "Опишите проблему (до 4000 символов).",
        "contact": "Укажите контакт для обратной связи (до 300 символов).",
    }[dialog.step]


@transaction.atomic
def process_input(telegram_id, applicant, text, *, callback=None):
    dialog, _ = BotDialog.objects.get_or_create(telegram_id=telegram_id)
    value = text.strip() if isinstance(text, str) else ""
    initial_step, initial_data = dialog.step, dict(dialog.data)

    def reply(message=None):
        if dialog.step != initial_step or dialog.data != initial_data or "_menu_token" not in dialog.data:
            dialog.data["_menu_token"] = uuid.uuid4().hex
        dialog.save(update_fields=["step", "data", "updated_at"])
        details = ()
        if dialog.step == "confirm" and message is None:
            item = CategoryItem.objects.select_related("group").filter(pk=dialog.data.get("item_id")).first()
            details = (("Категория", str(item)), ("Описание", dialog.data["description"]),
                ("Контакт", dialog.data["contact"]))
        return Reply(message or prompt(dialog), choices(dialog), dialog.step, details)

    selection = None
    if callback is not None:
        parts = callback.split(":")
        key = dialog.data.get("_menu_token", "")
        if callback in ("new", "status"):
            value = "Подать заявку" if callback == "new" else "Узнать статус"
        elif len(parts) == 3 and parts[0] in ("group", "item") and parts[1].isascii() and parts[1].isdigit() and len(parts[1]) < 16 and parts[2] == key and dialog.step == parts[0]:
            selection = (parts[0], int(parts[1]))
        elif len(parts) == 3 and parts[0] == "back" and parts[1] == dialog.step and parts[2] == key:
            value = "Назад"
        elif len(parts) == 2 and parts[0] == "confirm" and (
            (parts[1] == key and dialog.step == "confirm") or
            (parts[1] == dialog.data.get("_confirmed_token") and dialog.step == "submitted")):
            value = "Подтвердить"
        else:
            return reply("Это меню уже устарело. Используйте кнопки под последним сообщением.")

    if value.split(maxsplit=1)[0:1] == ["/status"]:
        number = value.partition(" ")[2].strip()
        try:
            result = owner_status(telegram_id, number) if number else "Введите /status З-000001 — номер своей заявки."
        except RuleError as error:
            result = str(error)
        return reply(result)
    if value == "Узнать статус":
        return reply("Введите /status З-000001 — номер своей заявки. Команда доступна на любом этапе.")
    if value == "/start":
        dialog.step, dialog.data = "idle", {}
        return reply()
    if value == "Подать заявку":
        dialog.step = "group"
        dialog.data = {"key": str(uuid.uuid4()), "applicant": str(applicant or telegram_id).strip()[:200] or str(telegram_id)}
        return reply()
    if value == "Назад":
        dialog.step = {"group": "idle", "item": "group", "description": "item",
            "contact": "description", "confirm": "contact", "submitted": "idle", "idle": "idle"}[dialog.step]
        return reply()
    if dialog.step in ("idle", "submitted"):
        return reply()
    if not value and selection is None:
        return reply("Отправьте непустой текст или выберите кнопку.\n" + prompt(dialog))

    if dialog.step in ("item", "description", "contact", "confirm"):
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
            return reply("Выберите доступную группу с помощью кнопок.")
        dialog.data["group_id"] = group.pk
        dialog.step = "item"
    elif dialog.step == "item":
        items = CategoryItem.objects.filter(group_id=dialog.data["group_id"], active=True, group__active=True)
        item = items.filter(pk=selection[1]).first() if selection else items.filter(name=value).first()
        if not item:
            return reply("Выберите доступный элемент с помощью кнопок.")
        dialog.data["item_id"] = item.pk
        dialog.step = "description"
    elif dialog.step in ("description", "contact"):
        field = dialog.step
        try:
            dialog.data[field] = required(value, "Описание" if field == "description" else "Контакт",
                4000 if field == "description" else 300)
        except RuleError as error:
            return reply(str(error))
        dialog.step = "contact" if field == "description" else "confirm"
    elif dialog.step == "confirm":
        if value != "Подтвердить":
            return reply("Нажмите «Подтвердить» или «Назад».")
        try:
            ticket = create_ticket(telegram_id=telegram_id, applicant=dialog.data["applicant"],
                item_id=dialog.data["item_id"], description=dialog.data["description"],
                contact=dialog.data["contact"], key=dialog.data["key"])
        except RuleError as error:
            dialog.step = "group"
            return reply(str(error))
        dialog.step = "submitted"
        dialog.data = {"number": ticket.number, "key": str(ticket.key),
            "_confirmed_token": dialog.data.get("_menu_token")}
    return reply()
