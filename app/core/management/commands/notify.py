import asyncio
import os
from asgiref.sync import sync_to_async
from aiogram import Bot
from django.core.management.base import BaseCommand, CommandError
from app.bot.telegram import send_text
from app.core.notifications import deliver_pending


class Command(BaseCommand):
    help = "Доставка сохранённых уведомлений Telegram с повторами."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Обработать очередь один раз и завершиться.")
        parser.add_argument("--interval", type=float, default=2, help="Пауза между проходами очереди, секунды (по умолчанию 2).")

    def handle(self, *args, **options):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise CommandError("Задайте переменную TELEGRAM_BOT_TOKEN.")
        if not 0 < options["interval"] <= 30:
            raise CommandError("Интервал должен быть больше 0 и не больше 30 секунд.")
        try:
            bot = Bot(token=token)
        except Exception:
            raise CommandError("Некорректная настройка TELEGRAM_BOT_TOKEN.") from None

        async def run():
            loop = asyncio.get_running_loop()

            def sender(chat_id, text):
                future = asyncio.run_coroutine_threadsafe(
                    send_text(bot, chat_id, text), loop)
                try:
                    return future.result(timeout=25)
                except Exception:
                    future.cancel()
                    raise

            async with bot.context():
                while True:
                    sent = await sync_to_async(deliver_pending, thread_sensitive=True)(sender)
                    if sent:
                        self.stdout.write(f"Доставлено уведомлений: {sent}.")
                    if options["once"]:
                        break
                    await asyncio.sleep(options["interval"])

        try:
            asyncio.run(run())
        except KeyboardInterrupt:
            self.stdout.write("Доставка остановлена. Неотправленные сообщения сохранены в очереди.")
