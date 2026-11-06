import asyncio
import logging
import re
from asgiref.sync import sync_to_async
from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from django.db import transaction
from django.conf import settings
from app.bot.dialog import process_input, normalize_input, opens_fresh_message
from app.bot.presentation import (keyboard, message_chunks, notification_content, premium_error,
    reply_content, without_button_icons, without_custom_emoji, without_styles, without_urls)
from app.core.models import BotCursor, BotDialog
from app.core.notifications import complete_notification, take_notification


logger = logging.getLogger(__name__)


def config():
    return getattr(settings, "BOT_CONFIG", {})


def markup(reply):
    return keyboard(reply)


async def send_text(bot, chat_id, text, reply_markup=None):
    await send_content(bot, chat_id, notification_content(text), reply_markup)


async def send_content(bot, chat_id, content, reply_markup=None, *, message_id=None):
    chunks = list(message_chunks(content))
    sent_messages = []
    for index, (text, entities) in enumerate(chunks):
        current_markup = reply_markup if index == len(chunks) - 1 else None
        async def send(body, body_entities, buttons):
            timeout = config().get("request_timeout", 10)
            payload = {"reply_markup": buttons, "parse_mode": None,
                "entities": body_entities or None, "request_timeout": timeout}
            if message_id is not None and index == 0:
                try:
                    return await bot.edit_message_text(body, chat_id=chat_id, message_id=message_id, **payload)
                except TelegramBadRequest as error:
                    if "message is not modified" in error.message.lower():
                        return None
                    if not any(value in error.message.lower() for value in ("message can't be edited", "message to edit not found")):
                        raise
            return await bot.send_message(chat_id, body, **payload)
        try:
            result = await send(text, entities, current_markup)
        except TelegramBadRequest as error:
            if not markup_error(error):
                raise
            logger.warning("Telegram отклонил оформление сообщения: %s", safe_reason(error))
            plain_buttons = without_button_icons(current_markup)
            plain_entities = without_custom_emoji(entities)
            bare_buttons = without_urls(without_styles(plain_buttons))
            result = None
            last_error = error
            for body_entities, buttons in (
                (entities, plain_buttons),
                (plain_entities, plain_buttons),
                (plain_entities, bare_buttons),
                (plain_entities, None),
            ):
                try:
                    result = await send(text, body_entities, buttons)
                    break
                except TelegramBadRequest as next_error:
                    last_error = next_error
                    if not markup_error(next_error):
                        raise
            else:
                raise last_error
        sent_messages.append(result)
    return sent_messages


async def send_reply(bot, chat_id, reply, *, message_id=None):
    return await send_content(bot, chat_id, reply_content(reply), markup(reply), message_id=message_id)


async def deliver_screen(bot, chat_id, reply, *, message_id=None, attach_keyboard=False):
    if not attach_keyboard or not config().get("show_reply_keyboard", True):
        return await send_reply(bot, chat_id, reply, message_id=message_id)
    from app.bot.presentation import lower_keyboard
    keyboard_markup = lower_keyboard()
    if keyboard_markup is None:
        return await send_reply(bot, chat_id, reply, message_id=None)
    # Сначала сообщение с нижней клавиатурой, затем то же сообщение получает кнопки меню.
    # Правка не снимает уже показанную reply-клавиатуру.
    sent = await send_content(bot, chat_id, reply_content(reply), keyboard_markup, message_id=None)
    fresh_id = sent_message_id(sent)
    if fresh_id is None:
        return sent
    edited = await send_reply(bot, chat_id, reply, message_id=fresh_id)
    return edited or sent


@transaction.atomic
def consume_update(update):
    cursor, _ = BotCursor.objects.get_or_create(name="telegram")
    if update.update_id < cursor.offset:
        return None
    message = update.message
    response = None
    if message and message.chat.type == ChatType.PRIVATE and message.from_user and not message.from_user.is_bot:
        response = (message.chat.id, process_input(message.from_user.id, message.from_user.full_name, message.text))
    query = update.callback_query
    if query and query.message and query.message.chat.type == ChatType.PRIVATE and query.data and not query.from_user.is_bot and query.message.chat.id == query.from_user.id:
        response = (query.message.chat.id, process_input(query.from_user.id, query.from_user.full_name,
            None, callback=query.data))
    cursor.offset = update.update_id + 1
    cursor.save(update_fields=["offset"])
    return response


def get_offset():
    cursor, _ = BotCursor.objects.get_or_create(name="telegram")
    return cursor.offset


def screen_message(telegram_id):
    return BotDialog.objects.filter(telegram_id=telegram_id).values_list("screen_message_id", flat=True).first()


def dialog_step(telegram_id):
    return BotDialog.objects.filter(telegram_id=telegram_id).values_list("step", flat=True).first() or "idle"


def remember_screen(telegram_id, message_id):
    BotDialog.objects.filter(telegram_id=telegram_id).update(screen_message_id=message_id)


def owner_id(update):
    if update.callback_query and update.callback_query.from_user:
        return update.callback_query.from_user.id
    if update.message and update.message.from_user:
        return update.message.from_user.id
    return None


def command_name(raw):
    if not raw.startswith("/"):
        return ""
    return raw.split(maxsplit=1)[0].split("@", 1)[0]


def keeps_current_screen(raw):
    # «Главное меню» нормализуется в /start, но это кнопка, не команда.
    return normalize_input(raw) in {"Подать заявку", "Узнать статус", "Назад", "Подтвердить", "/start"}


def edit_target(update, stored_id, step="idle", next_step=None):
    """id для правки, нужно ли заново показать нижнюю клавиатуру и запоминать ли экран."""
    if not config().get("edit_messages", True):
        return None, False, True
    raw = (update.message.text or "").strip() if update.message else ""
    command = command_name(raw)
    if command == "/start":
        return None, True, True
    if command:
        return None, False, False
    if opens_fresh_message(step, next_step):
        return None, False, True
    query = update.callback_query
    if query and query.message:
        return query.message.message_id, False, True
    if raw and keeps_current_screen(raw):
        return stored_id, False, True
    if step in {"group", "item", "description", "contact", "confirm"}:
        return stored_id, False, True
    return None, False, True


def markup_error(error):
    text = error.message.lower()
    return premium_error(error) or any(word in text for word in ("entity", "url", "button", "keyboard", "style"))


def safe_reason(error):
    text = getattr(error, "message", "") or error.__class__.__name__
    return re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot<token>", text)[:300]


def sent_message_id(messages):
    for item in reversed(messages or []):
        message_id = getattr(item, "message_id", None)
        if message_id:
            return message_id
    return None


async def deliver_forever(bot, stop):
    interval = config().get("notification_interval", 2)
    while not stop.is_set():
        payload = await sync_to_async(take_notification, thread_sensitive=True)()
        if payload is None:
            try:
                await asyncio.wait_for(stop.wait(), interval)
            except asyncio.TimeoutError:
                pass
            continue
        pk, chat_id, text = payload
        error = None
        try:
            await send_text(bot, chat_id, text)
        except Exception as exc:
            error = exc
            logger.warning("Уведомление останется в очереди и будет отправлено повторно.")
        await sync_to_async(complete_notification, thread_sensitive=True)(pk, error)


async def poll(bot: Bot):
    offset = await sync_to_async(get_offset, thread_sensitive=True)()
    while True:
        try:
            timeout = config().get("poll_timeout", 20)
            updates = await bot.get_updates(offset=offset, timeout=timeout,
                request_timeout=timeout + config().get("request_timeout", 10), allowed_updates=["message", "callback_query"])
        except (TelegramAPIError, OSError, TimeoutError):
            logger.warning("Не удалось получить сообщения Telegram; повтор через 2 секунды.")
            await asyncio.sleep(config().get("poll_retry", 2))
            continue
        for update in updates:
            if update.callback_query:
                try:
                    await bot.answer_callback_query(update.callback_query.id, request_timeout=config().get("request_timeout", 10))
                except (TelegramAPIError, OSError, TimeoutError):
                    logger.warning("Не удалось подтвердить нажатие кнопки Telegram.")
            user_id = owner_id(update)
            step = await sync_to_async(dialog_step, thread_sensitive=True)(user_id) if user_id else "idle"
            response = await sync_to_async(consume_update, thread_sensitive=True)(update)
            offset = update.update_id + 1
            if response:
                chat_id, reply = response
                try:
                    stored = await sync_to_async(screen_message, thread_sensitive=True)(user_id) if user_id else None
                    message_id, attach_keyboard, remember = edit_target(update, stored, step, reply.stage)
                    sent = await deliver_screen(bot, chat_id, reply, message_id=message_id,
                        attach_keyboard=attach_keyboard)
                    new_id = sent_message_id(sent)
                    if user_id and new_id and remember:
                        await sync_to_async(remember_screen, thread_sensitive=True)(user_id, new_id)
                except (TelegramAPIError, OSError, TimeoutError) as error:
                    logger.warning("Не удалось отправить ответ Telegram: %s. Диалог сохранён; отправьте следующее сообщение.",
                        safe_reason(error))
