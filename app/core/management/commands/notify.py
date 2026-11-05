import asyncio
import signal
from asgiref.sync import sync_to_async
from aiogram import Bot
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from app.bot.telegram import send_text
from app.core.notifications import deliver_pending


class Command(BaseCommand):
    help = "Доставка сохранённых уведомлений Telegram с повторами."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Обработать очередь один раз и завершиться.")
        parser.add_argument("--interval", type=float, default=None, help="Пауза между проходами очереди, секунды (по умолчанию из .env).")

    def handle(self, *args, **options):
        config = settings.BOT_CONFIG
        token = config.get("token", "").strip()
        if not token:
            raise CommandError("Задайте переменную TELEGRAM_BOT_TOKEN.")
        interval = options["interval"] if options["interval"] is not None else config.get("notification_interval", 2)
        if not 0 < interval <= 30:
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
                    return future.result(timeout=config.get("notification_timeout", 25))
                except Exception:
                    future.cancel()
                    raise

            async with bot.context():
                while True:
                    sent = await sync_to_async(deliver_pending, thread_sensitive=True)(sender,
                        limit=config.get("notification_batch_size", 100))
                    if sent:
                        self.stdout.write(f"Доставлено уведомлений: {sent}.")
                    if options["once"]:
                        break
                    await asyncio.sleep(interval)

        try:
            def stop(*_):
                raise KeyboardInterrupt
            signal.signal(signal.SIGTERM, stop)
            asyncio.run(run())
        except KeyboardInterrupt:
            self.stdout.write("Доставка остановлена. Неотправленные сообщения сохранены в очереди.")
