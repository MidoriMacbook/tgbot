import asyncio
import os
import signal
import sys
import threading

from app.config import env_bool, load_environment


def prepare():
    from django.core.management import call_command
    if env_bool('AUTO_MIGRATE', True):
        call_command('migrate', '--noinput')
    if env_bool('AUTO_BOOTSTRAP_CHIEF', True):
        call_command('bootstrap_chief')
    if env_bool('AUTO_COLLECTSTATIC', True):
        call_command('collectstatic', '--noinput')


async def run_tasks(stop, run_bot, run_notifications):
    if not run_bot and not run_notifications:
        await stop.wait()
        return
    from aiogram import Bot
    from django.conf import settings
    from app.bot.telegram import deliver_forever, poll

    bot = Bot(token=settings.BOT_CONFIG['token'])
    async with bot.context():
        tasks = []
        if run_bot:
            tasks.append(asyncio.create_task(poll(bot)))
            print('Бот принимает сообщения.', flush=True)
        if run_notifications:
            tasks.append(asyncio.create_task(deliver_forever(bot, stop)))
            print('Уведомления подключены.', flush=True)
        await stop.wait()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def serve_forever(run_web, run_bot, run_notifications):
    from django.conf import settings

    server = None
    thread = None
    if run_web:
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
        loop.run_until_complete(run_tasks(stop, run_bot, run_notifications))
    finally:
        if server is not None:
            server.close()
        if thread is not None:
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

    run_web = env_bool('RUN_WEB', True)
    run_bot = env_bool('RUN_BOT', True)
    run_notifications = env_bool('RUN_NOTIFICATIONS', True)
    if not (run_web or run_bot or run_notifications):
        print('Включите хотя бы один процесс RUN_WEB, RUN_BOT или RUN_NOTIFICATIONS.', file=sys.stderr)
        return 1
    if (run_bot or run_notifications) and not settings.BOT_CONFIG['token']:
        print('Для бота и уведомлений задайте TELEGRAM_BOT_TOKEN.', file=sys.stderr)
        return 1
    try:
        prepare()
    except CommandError:
        print('Подготовка завершилась с ошибкой.', file=sys.stderr)
        return 1
    print('Сервер, бот и уведомления работают в одном процессе.', flush=True)
    return serve_forever(run_web, run_bot, run_notifications)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
