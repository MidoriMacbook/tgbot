import asyncio
import logging
from asgiref.sync import sync_to_async
from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from django.db import transaction
from django.conf import settings
from app.bot.dialog import process_input, normalize_input
from app.bot.presentation import (html_chunks, keyboard, notification_content, premium_error,
    reply_content, without_button_icons, without_premium, lower_keyboard)
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
    chunks = list(html_chunks(content))
    sent_messages = []
    for index, chunk in enumerate(chunks):
        current_markup = reply_markup if index == len(chunks) - 1 else None
        async def send(body, buttons):
            timeout = config().get("request_timeout", 10)
            if message_id is not None and index == 0:
                try:
                    return await bot.edit_message_text(body, chat_id=chat_id, message_id=message_id,
                        reply_markup=buttons, parse_mode="HTML", request_timeout=timeout)
                except TelegramBadRequest as error:
                    if "message is not modified" in error.message.lower():
                        return None
                    if not any(value in error.message.lower() for value in ("message can't be edited", "message to edit not found")):
                        raise
            return await bot.send_message(chat_id, body, reply_markup=buttons,
                parse_mode="HTML", request_timeout=timeout)
        try:
            result = await send(chunk, current_markup)
        except TelegramBadRequest as error:
            if not premium_error(error):
                raise
            plain_buttons = without_button_icons(current_markup)
            try:
                result = await send(chunk, plain_buttons)
            except TelegramBadRequest as second_error:
                if not premium_error(second_error):
                    raise
                result = await send(without_premium(chunk), plain_buttons)
        sent_messages.append(result)
    return sent_messages


async def send_reply(bot, chat_id, reply, *, message_id=None):
    return await send_content(bot, chat_id, reply_content(reply), markup(reply), message_id=message_id)


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


def remember_screen(telegram_id, message_id):
    BotDialog.objects.filter(telegram_id=telegram_id).update(screen_message_id=message_id)


def owner_id(update):
    if update.callback_query and update.callback_query.from_user:
        return update.callback_query.from_user.id
    if update.message and update.message.from_user:
        return update.message.from_user.id
    return None


def edit_target(update, stored_id):
    """Возвращает id сообщения для правки и признак первого показа нижней клавиатуры."""
    if not config().get("edit_messages", True):
        return None, False
    query = update.callback_query
    if query and query.message:
        return query.message.message_id, False
    text = normalize_input((update.message.text or "").strip()) if update.message else ""
    attach_keyboard = bool(update.message and text == "/start" and config().get("show_reply_keyboard", True) and not stored_id)
    return (None if attach_keyboard else stored_id), attach_keyboard


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
            response = await sync_to_async(consume_update, thread_sensitive=True)(update)
            offset = update.update_id + 1
            if response:
                chat_id, reply = response
                try:
                    user_id = owner_id(update)
                    stored = await sync_to_async(screen_message, thread_sensitive=True)(user_id) if user_id else None
                    message_id, attach_keyboard = edit_target(update, stored)
                    if attach_keyboard:
                        sent = await send_content(bot, chat_id, reply_content(reply), lower_keyboard())
                    else:
                        sent = await send_reply(bot, chat_id, reply, message_id=message_id)
                    new_id = sent_message_id(sent)
                    if user_id and new_id:
                        await sync_to_async(remember_screen, thread_sensitive=True)(user_id, new_id)
                except (TelegramAPIError, OSError, TimeoutError):
                    logger.warning("Не удалось отправить ответ Telegram. Диалог сохранён; отправьте следующее сообщение.")
