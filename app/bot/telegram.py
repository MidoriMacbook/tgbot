import asyncio
import logging
from asgiref.sync import sync_to_async
from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from django.db import transaction
from app.bot.dialog import process_input
from app.core.models import BotCursor


logger = logging.getLogger(__name__)


def markup(reply):
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=value) for value in row]
        for row in reply.keyboard], resize_keyboard=True)


async def send_text(bot, chat_id, text, reply_markup=None):
    chunks = [text[index:index + 4000] for index in range(0, len(text), 4000)]
    for index, chunk in enumerate(chunks):
        await bot.send_message(chat_id, chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None, request_timeout=10)


async def send_reply(bot, chat_id, reply):
    await send_text(bot, chat_id, reply.text, markup(reply))


@transaction.atomic
def consume_update(update):
    cursor, _ = BotCursor.objects.get_or_create(name="telegram")
    if update.update_id < cursor.offset:
        return None
    message = update.message
    response = None
    if message and message.chat.type == ChatType.PRIVATE and message.from_user and not message.from_user.is_bot:
        response = (message.chat.id, process_input(message.from_user.id, message.from_user.full_name, message.text))
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
                request_timeout=30, allowed_updates=["message"])
        except (TelegramAPIError, OSError, TimeoutError):
            logger.warning("Не удалось получить сообщения Telegram; повтор через 2 секунды.")
            await asyncio.sleep(2)
            continue
        for update in updates:
            response = await sync_to_async(consume_update, thread_sensitive=True)(update)
            offset = update.update_id + 1
            if response:
                chat_id, reply = response
                try:
                    await send_reply(bot, chat_id, reply)
                except (TelegramAPIError, OSError, TimeoutError):
                    logger.warning("Не удалось отправить ответ Telegram. Диалог сохранён; отправьте следующее сообщение.")
