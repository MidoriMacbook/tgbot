import os
import signal
import subprocess
import sys
import threading
import time

from app.config import BASE_DIR, env_bool, load_environment


def stop_children(children):
    for _, process in reversed(children):
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 15
    for _, process in reversed(children):
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    load_environment()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
    os.environ.setdefault('PYTHONUNBUFFERED', '1')
    from django.conf import settings

    commands = [('веб-панель', 'serve', 'RUN_WEB'), ('бот', 'runbot', 'RUN_BOT'),
                ('уведомления', 'notify', 'RUN_NOTIFICATIONS')]
    commands = [(name, command) for name, command, flag in commands if env_bool(flag, True)]
    if not commands:
        print('Включите хотя бы один процесс RUN_WEB, RUN_BOT или RUN_NOTIFICATIONS.', file=sys.stderr)
        return 1
    if any(command in {'runbot', 'notify'} for _, command in commands) and not settings.BOT_CONFIG['token']:
        print('Для бота и уведомлений задайте TELEGRAM_BOT_TOKEN.', file=sys.stderr)
        return 1
    stopping = threading.Event()
    children = []

    def stop(signum, frame):
        stopping.set()

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}

    def start(name, command, *args):
        process = subprocess.Popen([sys.executable, str(BASE_DIR / 'manage.py'), command, *args],
                                   cwd=BASE_DIR, shell=False)
        children.append((name, process))
        return process

    try:
        for flag, command, args in [
            ('AUTO_MIGRATE', 'migrate', ['--noinput']),
            ('AUTO_BOOTSTRAP_CHIEF', 'bootstrap_chief', []),
            ('AUTO_COLLECTSTATIC', 'collectstatic', ['--noinput']),
        ]:
            if env_bool(flag, True):
                process = start(command, command, *args)
                while process.poll() is None and not stopping.wait(0.2):
                    pass
                if stopping.is_set():
                    return 0
                if process.returncode:
                    print(f'Подготовка «{command}» завершилась с ошибкой.', file=sys.stderr)
                    return 1
                children.remove((command, process))
        for name, command in commands:
            if stopping.is_set():
                return 0
            start(name, command)
            print(f'Запущен процесс: {name}.', flush=True)
        while not stopping.wait(0.5):
            for name, process in children:
                code = process.poll()
                if code is not None:
                    print(f'Процесс «{name}» завершился (код {code}); останавливаем остальные.', file=sys.stderr)
                    return 1
        return 0
    finally:
        stop_children(children)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
