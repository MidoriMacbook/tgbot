import uuid
from dataclasses import dataclass

from django.db import transaction
from app.core.models import BotDialog, CategoryGroup, CategoryItem
from app.core.services import RuleError, create_ticket, owner_status, required


@dataclass(frozen=True)
class Reply:
    text: str
    keyboard: tuple[tuple[str, ...], ...]


MENU = (("Подать заявку",), ("Узнать статус",))
BACK = (("Назад",),)


def choices(dialog):
    if dialog.step == "group":
        names = CategoryGroup.objects.filter(active=True, categoryitem__active=True).distinct().values_list("name", flat=True)
        return tuple((name,) for name in names) + BACK
    if dialog.step == "item":
        names = CategoryItem.objects.filter(group_id=dialog.data.get("group_id"), active=True,
            group__active=True).values_list("name", flat=True)
        return tuple((name,) for name in names) + BACK
    if dialog.step == "confirm":
        return (("Подтвердить",),) + BACK
    if dialog.step in ("description", "contact"):
        return BACK
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
def process_input(telegram_id, applicant, text):
    dialog, _ = BotDialog.objects.get_or_create(telegram_id=telegram_id)
    value = text.strip() if isinstance(text, str) else ""

    def reply(message=None):
        dialog.save(update_fields=["step", "data", "updated_at"])
        return Reply(message or prompt(dialog), choices(dialog))

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
    if not value:
        return reply("Отправьте непустой текст или выберите кнопку.\n" + prompt(dialog))

    if dialog.step in ("item", "description", "contact", "confirm"):
        valid_group = CategoryGroup.objects.filter(pk=dialog.data.get("group_id"), active=True).exists()
        valid_item = dialog.step == "item" or CategoryItem.objects.filter(pk=dialog.data.get("item_id"),
            group_id=dialog.data.get("group_id"), active=True, group__active=True).exists()
        if not valid_group or not valid_item:
            dialog.step = "group"
            return reply("Выбранная категория больше недоступна. Выберите группу заново.")
    if dialog.step == "group":
        group = CategoryGroup.objects.filter(name=value, active=True, categoryitem__active=True).distinct().first()
        if not group:
            return reply("Выберите доступную группу с помощью кнопок.")
        dialog.data["group_id"] = group.pk
        dialog.step = "item"
    elif dialog.step == "item":
        item = CategoryItem.objects.filter(group_id=dialog.data["group_id"], name=value, active=True,
            group__active=True).first()
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
        dialog.data = {"number": ticket.number, "key": str(ticket.key)}
    return reply()
