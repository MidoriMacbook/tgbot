import asyncio
import os
from aiogram import Bot
from django.core.management.base import BaseCommand, CommandError
from app.bot.telegram import poll


class Command(BaseCommand):
    help = "Приём заявок в личном чате Telegram через polling."

    def handle(self, *args, **options):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
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
        try:
            asyncio.run(run())
        except KeyboardInterrupt:
            self.stdout.write("Бот остановлен.")
