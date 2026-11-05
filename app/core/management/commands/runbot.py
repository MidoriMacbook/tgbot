import asyncio
import signal
from aiogram import Bot
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from app.bot.telegram import poll


class Command(BaseCommand):
    help = "Приём заявок в личном чате Telegram через polling."

    def handle(self, *args, **options):
        token = settings.BOT_CONFIG.get("token", "").strip()
        if not token:
            raise CommandError("Задайте переменную TELEGRAM_BOT_TOKEN.")
        try:
            bot = Bot(token=token)
        except Exception:
            raise CommandError("Некорректная настройка TELEGRAM_BOT_TOKEN.") from None

        async def run():
            async with bot.context():
                await poll(bot)
        self.stdout.write("Бот запущен. Остановка: Ctrl+C.")
        def stop(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop)
        try:
            asyncio.run(run())
        except KeyboardInterrupt:
            self.stdout.write("Бот остановлен.")
