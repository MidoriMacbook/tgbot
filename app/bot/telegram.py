import asyncio
import logging
from asgiref.sync import sync_to_async
from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from django.db import transaction
from app.bot.dialog import process_input
from app.bot.presentation import (html_chunks, keyboard, notification_content, premium_error,
    reply_content, without_button_icons, without_premium)
from app.core.models import BotCursor


logger = logging.getLogger(__name__)


def markup(reply):
    return keyboard(reply)


async def send_text(bot, chat_id, text, reply_markup=None):
    await send_content(bot, chat_id, notification_content(text), reply_markup)


async def send_content(bot, chat_id, content, reply_markup=None):
    chunks = list(html_chunks(content))
    for index, chunk in enumerate(chunks):
        current_markup = reply_markup if index == len(chunks) - 1 else None
        async def send(body, buttons):
            return await bot.send_message(chat_id, body, reply_markup=buttons,
                parse_mode="HTML", request_timeout=10)
        try:
            await send(chunk, current_markup)
        except TelegramBadRequest as error:
            if not premium_error(error):
                raise
            plain_buttons = without_button_icons(current_markup)
            try:
                await send(chunk, plain_buttons)
            except TelegramBadRequest as second_error:
                if not premium_error(second_error):
                    raise
                await send(without_premium(chunk), plain_buttons)


async def send_reply(bot, chat_id, reply):
    await send_content(bot, chat_id, reply_content(reply), markup(reply))


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


async def poll(bot: Bot):
    offset = await sync_to_async(get_offset, thread_sensitive=True)()
    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=20,
                request_timeout=30, allowed_updates=["message", "callback_query"])
        except (TelegramAPIError, OSError, TimeoutError):
            logger.warning("Не удалось получить сообщения Telegram; повтор через 2 секунды.")
            await asyncio.sleep(2)
            continue
        for update in updates:
            if update.callback_query:
                try:
                    await bot.answer_callback_query(update.callback_query.id, request_timeout=10)
                except (TelegramAPIError, OSError, TimeoutError):
                    logger.warning("Не удалось подтвердить нажатие кнопки Telegram.")
            response = await sync_to_async(consume_update, thread_sensitive=True)(update)
            offset = update.update_id + 1
            if response:
                chat_id, reply = response
                try:
                    await send_reply(bot, chat_id, reply)
                except (TelegramAPIError, OSError, TimeoutError):
                    logger.warning("Не удалось отправить ответ Telegram. Диалог сохранён; отправьте следующее сообщение.")
