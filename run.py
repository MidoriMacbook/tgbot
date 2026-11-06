import asyncio
import os
import signal
import sys
import threading

from app.config import load_environment


def prepare():
    from django.core.management import call_command
    call_command('migrate', '--noinput')
    call_command('bootstrap_chief')
    call_command('collectstatic', '--noinput')


async def run_tasks(stop):
    from aiogram import Bot
    from django.conf import settings
    from app.bot.telegram import deliver_forever, poll

    bot = Bot(token=settings.BOT_CONFIG['token'])
    async with bot.context():
        tasks = [
            asyncio.create_task(poll(bot)),
            asyncio.create_task(deliver_forever(bot, stop)),
        ]
        print('Бот принимает сообщения.', flush=True)
        print('Уведомления подключены.', flush=True)
        await stop.wait()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def serve_forever():
    from django.conf import settings

    from app.core.management.commands.serve import build_server
    server = build_server()
    thread = threading.Thread(target=server.run, name='web', daemon=True)
    thread.start()
    print(f'Веб-панель слушает {settings.HOST}:{settings.PORT}.', flush=True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop = asyncio.Event()

    def request_stop(*_args):
        if not stop.is_set():
            loop.call_soon_threadsafe(stop.set)

    handled = []
    for sig in (signal.SIGINT, getattr(signal, 'SIGTERM', None)):
        if sig is None:
            continue
        try:
            signal.signal(sig, request_stop)
            handled.append(sig)
        except (ValueError, OSError):
            pass
    try:
        loop.run_until_complete(run_tasks(stop))
    finally:
        server.close()
        thread.join(timeout=5)
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        for sig in handled:
            signal.signal(sig, signal.SIG_DFL)
    return 0


def main():
    load_environment()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
    os.environ.setdefault('PYTHONUNBUFFERED', '1')
    import django
    django.setup()
    from django.conf import settings
    from django.core.management.base import CommandError

    if not settings.BOT_CONFIG['token']:
        print('Задайте TELEGRAM_BOT_TOKEN.', file=sys.stderr)
        return 1
    try:
        prepare()
    except CommandError:
        print('Подготовка завершилась с ошибкой.', file=sys.stderr)
        return 1
    print('Сервер, бот и уведомления работают в одном процессе.', flush=True)
    return serve_forever()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
