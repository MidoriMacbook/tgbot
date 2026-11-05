"""Воспроизводимый полный автоматизированный цикл в отдельной БД."""
import argparse
import ctypes
import http.cookiejar
import json
import math
import os
from pathlib import Path
import platform
import re
import secrets
import socket
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def hardware():
    result = {'os': platform.platform(), 'python': platform.python_version(),
              'logical_cpus': os.cpu_count(), 'cpu': platform.processor()}
    if sys.platform == 'win32':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            result['cpu'] = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()

        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
                        *[(name, ctypes.c_ulonglong) for name in
                          ['total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended']]]
        info = Memory()
        info.length = ctypes.sizeof(info)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
            result['memory_gib'] = round(info.total / 1024**3, 1)
    return result


class Browser:
    def __init__(self, base, username, password):
        self.base = base
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))
        self.get('/login/')
        self.post('/login/', {'username': username, 'password': password})

    def get(self, path):
        with self.opener.open(self.base + path, timeout=30) as response:
            data = response.read().decode('utf-8')
            if response.status != 200:
                raise RuntimeError(f'HTTP {response.status}')
            return data

    def post(self, path, values):
        csrf = next(c.value for c in self.cookies if c.name == 'csrftoken')
        values = {**values, 'csrfmiddlewaretoken': csrf}
        req = Request(self.base + path, urlencode(values).encode(),
                      headers={'Referer': self.base + path}, method='POST')
        with self.opener.open(req, timeout=30) as response:
            data = response.read().decode('utf-8')
            if response.status != 200:
                raise RuntimeError(f'HTTP {response.status}')
            return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycles', type=int, default=100)
    parser.add_argument('--users', type=int, default=4)
    parser.add_argument('--dataset', type=int, default=250)
    parser.add_argument('--warmup', type=int, default=5)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--output', default='docs/demo/performance.json')
    options = parser.parse_args()
    if min(options.cycles, options.users) < 1 or min(options.dataset, options.warmup) < 0:
        parser.error('Количество циклов и пользователей должно быть положительным')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', options.port))
    run_dir = ROOT / 'artifacts' / f'benchmark-{time.time_ns()}'
    run_dir.mkdir(parents=True)
    os.environ['DATABASE_PATH'] = str(run_dir / 'benchmark.sqlite3')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'app.settings'
    os.environ['DJANGO_ALLOWED_HOSTS'] = '127.0.0.1,localhost'
    os.environ['DJANGO_DEBUG'] = '1'
    import django
    django.setup()
    from django.core.management import call_command
    from django.contrib.auth.models import User
    from django.db import close_old_connections
    from app.core.models import Ticket, Notification, CategoryItem
    from app.core.services import create_ticket, owner_status
    from app.bot.dialog import process_input
    from app.core.notifications import deliver_pending
    import uuid

    call_command('migrate', verbosity=0)
    password = secrets.token_urlsafe(24)
    operators = [User.objects.create_user(f'bench{i}', password=password, is_staff=True)
                 for i in range(options.users + 1)]
    item = CategoryItem.objects.first()
    for index in range(options.dataset):
        create_ticket(telegram_id=800000000000 + index, applicant='Нагрузочный заявитель',
                      item_id=item.pk, description='Начальный набор данных',
                      contact='Локальный замер', key=uuid.uuid4())
    base = f'http://127.0.0.1:{options.port}'
    with (run_dir / 'server.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable, str(ROOT / 'manage.py'), 'runserver',
            f'127.0.0.1:{options.port}', '--noreload'], cwd=ROOT, env=os.environ.copy(),
            stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(('127.0.0.1', options.port), timeout=.2):
                        break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('Сервер не запустился; смотрите artifacts/server.log')
                    time.sleep(.1)
            else:
                raise RuntimeError('Сервер не ответил за 15 секунд')

            def cycle(browser, telegram_id, assignee_id):
                started = time.perf_counter()
                for text in ['/start', 'Подать заявку', 'Оборудование', 'Проектор',
                             'Не работает проектор в кабинете 101', 'Кабинет 101', 'Подтвердить']:
                    reply = process_input(telegram_id, 'Нагрузочный заявитель', text)
                ticket = Ticket.objects.get(telegram_id=telegram_id)
                if ticket.number not in reply.text:
                    raise RuntimeError('Бот не подтвердил номер заявки')
                listing = browser.get('/')
                if ticket.number not in listing:
                    raise RuntimeError('Заявка отсутствует в ленте')
                card = browser.get(f'/tickets/{ticket.pk}/')
                if ticket.description not in card:
                    raise RuntimeError('Описание отсутствует в карточке')
                for values in [dict(action='take', version=0),
                               dict(action='assign', version=1, assignee_id=assignee_id),
                               dict(action='done', version=2, comment='Восстановлено питание')]:
                    browser.post(f'/tickets/{ticket.pk}/action/', values)
                delivery_deadline = time.perf_counter() + 10
                while Notification.objects.filter(ticket=ticket, sent_at__isnull=False).count() != 2:
                    deliver_pending(lambda chat_id, text: None, limit=100)
                    if time.perf_counter() > delivery_deadline:
                        raise RuntimeError('Не выполнена локальная доставка за 10 секунд')
                    time.sleep(.005)
                ticket.refresh_from_db()
                if ticket.status != 'done' or ticket.history.count() != 4:
                    raise RuntimeError('Неверное состояние или история')
                if Notification.objects.filter(ticket=ticket, sent_at__isnull=False).count() != 2:
                    raise RuntimeError('Не выполнена локальная доставка')
                if 'Выполнена' not in owner_status(telegram_id, ticket.number):
                    raise RuntimeError('Владелец не получил статус')
                return time.perf_counter() - started

            warm = Browser(base, operators[0].username, password)
            for i in range(options.warmup):
                cycle(warm, 810000000000 + i, operators[-1].pk)
            # Вход и подготовка сессий не входят в измеряемый цикл заявки.
            browsers = [Browser(base, user.username, password) for user in operators[:-1]]

            def worker(worker_id):
                close_old_connections()
                latencies, errors = [], []
                try:
                    for index in range(worker_id, options.cycles, options.users):
                        try:
                            latencies.append(cycle(browsers[worker_id], 820000000000 + index, operators[-1].pk))
                        except Exception as exc:
                            errors.append({'cycle': index, 'error': type(exc).__name__, 'message': str(exc)[:200]})
                    return latencies, errors
                finally:
                    close_old_connections()

            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=options.users) as pool:
                results = list(pool.map(worker, range(options.users)))
            elapsed = time.perf_counter() - started
            latencies = sorted(value for times, _ in results for value in times)
            errors = [error for _, items in results for error in items]
            report = {
                'measured_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'hardware': hardware(),
                'django': django.get_version(), 'database': 'SQLite, IMMEDIATE, файловая БД',
                'server': 'Django runserver --noreload, реальный HTTP localhost',
                'initial_tickets': options.dataset, 'warmup_cycles': options.warmup,
                'concurrent_users': options.users, 'attempted_cycles': options.cycles,
                'successful_cycles': len(latencies), 'duration_seconds': round(elapsed, 3),
                'throughput_tickets_hour': round(len(latencies) / elapsed * 3600, 1),
                'latency_seconds': {'mean': round(statistics.mean(latencies), 4) if latencies else None,
                    'p50': round(statistics.median(latencies), 4) if latencies else None,
                    'p95': round(latencies[max(0, math.ceil(len(latencies) * .95) - 1)], 4) if latencies else None,
                    'max': round(max(latencies), 4) if latencies else None},
                'errors': errors,
                'scope': 'Диалог бота → БД → HTTP лента/карточка → взять → переназначить → закрыть → очередь → локальный транспорт → статус владельца',
                'exclusions': ['Сеть Telegram API', 'время ввода заявителя', 'время работы оператора',
                               'вход сотрудников', 'подготовка данных и прогрев'],
                'delivery': 'Инъецированный локальный транспорт без сети, реальные задания очереди',
            }
            target = ROOT / options.output
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if errors:
                raise SystemExit(1)
        finally:
            server.terminate()
            server.wait(timeout=15)


if __name__ == '__main__':
    main()
