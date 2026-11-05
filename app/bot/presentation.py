import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from urllib.parse import urlsplit

from aiogram.utils.formatting import BlockQuote, Bold, Code, CustomEmoji, Italic, Text, TextLink
from django.conf import settings

from app.bot.emoji import get_icon


STATUS_ICONS = {"Новая": "new", "В работе": "work", "Выполнена": "done", "Отклонена": "rejected"}
PREMIUM_TAG = re.compile(r"</?tg-emoji\b[^>]*>")


def premium_enabled():
    return getattr(settings, "TELEGRAM_CUSTOM_EMOJI", True)


def icon(name):
    identifier, fallback = get_icon(name)
    return CustomEmoji(fallback, custom_emoji_id=identifier) if identifier and premium_enabled() else Text(fallback)


def config():
    return getattr(settings, "BOT_CONFIG", {})


ACCENT_ACTIONS = {"new", "confirm", "back", "menu"}


def button_style(kind):
    if kind not in ACCENT_ACTIONS:
        return None
    style = config().get("button_styles", {}).get(kind)
    return style or {"new": "primary", "confirm": "success", "back": "danger", "menu": "danger"}.get(kind)


def keyboard(reply):
    rows = []
    for row in reply.keyboard:
        buttons = []
        for button in row:
            kind = button.data.partition(":")[0]
            identifier, fallback = get_icon(button.icon) if button.icon else ("", "")
            text = button.text if not fallback or (identifier and premium_enabled()) else f"{fallback} {button.text}"
            icon_id = identifier if identifier and premium_enabled() else None
            if button.url:
                buttons.append(InlineKeyboardButton(text=text, url=button.url, icon_custom_emoji_id=icon_id))
            else:
                buttons.append(InlineKeyboardButton(text=text, callback_data=button.data, style=button_style(kind),
                    icon_custom_emoji_id=icon_id))
        rows.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lower_keyboard():
    rows = []
    for item in config().get("lower_buttons", []):
        if item.get("action") == "panel":
            continue
        identifier, fallback = get_icon(item.get("icon", item["action"]))
        rows.append([KeyboardButton(
            text=item["text"] if premium_enabled() and identifier else f"{fallback} {item['text']}",
            icon_custom_emoji_id=identifier if premium_enabled() and identifier else None,
            style=item.get("style") if item.get("action") in ACCENT_ACTIONS else None)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True) if rows else None


def highlight_numbers(value):
    pieces = re.split(r"(З-\d{6,})", value)
    return Text(*(Code(piece) if re.fullmatch(r"З-\d{6,}", piece) else piece for piece in pieces))


def reply_content(reply):
    if reply.text.startswith("Заявка З-"):
        return notification_content(reply.text)
    stage = config().get("texts", {}).get(reply.stage, {})
    title = stage.get("title", getattr(settings, "APP_BRAND", "Служба заявок"))
    name, subtitle = stage.get("icon", reply.stage), stage.get("subtitle", "")
    if reply.details:
        body = Text(*(Text(Bold(label), "\n", BlockQuote(value), "\n\n") for label, value in reply.details),
            "Нажмите «Подтвердить», чтобы передать заявку сотрудникам.\n«Назад» — чтобы изменить контакт.")
    else:
        body = highlight_numbers(reply.text)
    url = config().get("public_url", "")
    if reply.stage in ("idle", "submitted") and urlsplit(url).scheme in {"http", "https"} and urlsplit(url).hostname:
        body += Text("\n\n", icon("panel"), " ", TextLink("Открыть панель", url=url))
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


def html_chunks(content, limit=None):
    limit = limit or config().get("chunk_size", 3800)
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
    key = "inline_keyboard" if isinstance(markup, InlineKeyboardMarkup) else "keyboard"
    fallbacks = {str(item.get("id")): item.get("fallback", "") for item in config().get("emojis", {}).values()}
    rows = []
    for row in getattr(markup, key):
        buttons = []
        for button in row:
            fallback = fallbacks.get(button.icon_custom_emoji_id, "")
            text = f"{fallback} {button.text}" if fallback and not button.text.startswith(fallback) else button.text
            buttons.append(button.model_copy(update={"icon_custom_emoji_id": None, "text": text}))
        rows.append(buttons)
    return markup.model_copy(update={key: rows})


def without_styles(markup):
    if markup is None:
        return None
    key = "inline_keyboard" if isinstance(markup, InlineKeyboardMarkup) else "keyboard"
    rows = [[button.model_copy(update={"style": None}) for button in row] for row in getattr(markup, key)]
    return markup.model_copy(update={key: rows})


def without_urls(markup):
    if not isinstance(markup, InlineKeyboardMarkup):
        return markup
    rows = [[button for button in row if not button.url] for row in markup.inline_keyboard]
    rows = [row for row in rows if row]
    return markup.model_copy(update={"inline_keyboard": rows}) if rows else None


def without_premium(value):
    return PREMIUM_TAG.sub("", value)


def premium_error(error):
    return any(word in error.message.lower() for word in ("emoji", "premium", "document_invalid"))
