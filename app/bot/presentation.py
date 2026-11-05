import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.formatting import BlockQuote, Bold, Code, CustomEmoji, Italic, Text
from django.conf import settings

from app.bot.emoji import ICONS


STAGES = {
    "idle": ("Служба заботы", "welcome", "Помещения · оборудование · обслуживание"),
    "group": ("С чего начнём?", "group", "Шаг 1 из 4 · Группа"),
    "item": ("Уточним категорию", "item", "Шаг 2 из 4 · Элемент"),
    "description": ("Расскажите о проблеме", "description", "Шаг 3 из 4 · Описание"),
    "contact": ("Как с вами связаться?", "contact", "Шаг 4 из 4 · Контакт"),
    "confirm": ("Всё верно?", "confirm", "Проверка перед отправкой"),
    "submitted": ("Заявка отправлена", "done", "Номер сохранён · уведомим об изменениях"),
}
STATUS_ICONS = {"Новая": "new", "В работе": "work", "Выполнена": "done", "Отклонена": "rejected"}
PREMIUM_TAG = re.compile(r"</?tg-emoji\b[^>]*>")


def premium_enabled():
    return getattr(settings, "TELEGRAM_CUSTOM_EMOJI", True)


def icon(name):
    identifier, fallback = ICONS[name]
    return CustomEmoji(fallback, custom_emoji_id=identifier) if premium_enabled() else Text(fallback)


def keyboard(reply):
    rows = []
    for row in reply.keyboard:
        buttons = []
        for button in row:
            kind = button.data.partition(":")[0]
            identifier, _ = ICONS[kind]
            style = {"new": "primary", "confirm": "success"}.get(kind)
            buttons.append(InlineKeyboardButton(text=button.text, callback_data=button.data,
                icon_custom_emoji_id=identifier if premium_enabled() else None, style=style))
        rows.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def highlight_numbers(value):
    pieces = re.split(r"(З-\d{6,})", value)
    return Text(*(Code(piece) if re.fullmatch(r"З-\d{6,}", piece) else piece for piece in pieces))


def reply_content(reply):
    if reply.text.startswith("Заявка З-"):
        return notification_content(reply.text)
    title, name, subtitle = STAGES[reply.stage]
    if reply.details:
        body = Text(*(Text(Bold(label), "\n", BlockQuote(value), "\n\n") for label, value in reply.details),
            "Нажмите «Подтвердить», чтобы передать заявку сотрудникам.\n«Назад» — чтобы изменить контакт.")
    else:
        body = highlight_numbers(reply.text)
    return Text(icon(name), " ", Bold(title), "\n", Italic(subtitle), "\n\n", body)


def notification_content(value):
    match = re.fullmatch(r"Заявка (З-\d+): (Новая|В работе|Выполнена|Отклонена)\.\n?(.*)", value, re.DOTALL)
    if not match:
        return Text(value)
    number, status, comment = match.groups()
    body = Text(icon(STATUS_ICONS[status]), " ", Bold("Статус заявки"), "\n\n",
        Code(number), " · ", Bold(status))
    if comment:
        body += Text("\n\n", BlockQuote(comment))
    return body


def html_chunks(content, limit=3800):
    text, entities = content.render()
    start = 0
    offset = 0
    while start < len(text):
        end = start
        size = 0
        while end < len(text):
            width = len(text[end].encode("utf-16-le")) // 2
            if size + width > limit:
                break
            size += width
            end += 1
        clipped = []
        for entity in entities:
            left = max(offset, entity.offset)
            right = min(offset + size, entity.offset + entity.length)
            if right > left:
                clipped.append(entity.model_copy(update={"offset": left - offset, "length": right - left}))
        yield Text.from_entities(text[start:end], clipped).as_html()
        start = end
        offset += size


def without_button_icons(markup):
    if markup is None:
        return None
    return markup.model_copy(update={"inline_keyboard": [
        [button.model_copy(update={"icon_custom_emoji_id": None}) for button in row]
        for row in markup.inline_keyboard]})


def without_premium(value):
    return PREMIUM_TAG.sub("", value)


def premium_error(error):
    return any(word in error.message.lower() for word in ("emoji", "premium", "document_invalid"))
