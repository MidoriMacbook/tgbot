# Система обработки заявок

Telegram-бот для заявителей и локальная веб-панель сотрудников учебного заведения. Общая SQLite, история действий, назначение и переназначение, обязательный результат закрытия, долговечная очередь уведомлений. Собственная реализация на Python, Django и aiogram.

## Быстрый запуск в Windows / PowerShell

Нужен Python 3.12 или новее (проверено на 3.12), установленный с доступной командой `python`, и Git. Никакие платные сервисы не требуются.

```powershell
git clone https://github.com/MidoriMacbook/tgbot.git
cd tgbot
git switch prototype
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
notepad .env
```

В `.env` замените `DJANGO_SECRET_KEY` сгенерированной строкой, заполните `TELEGRAM_BOT_TOKEN` токеном от [@BotFather](https://t.me/BotFather). Остальные значения подходят для локального запуска. Не отправляйте `.env`, рабочую БД, контакты и логи в репозиторий. Файл `.env` не загружается Django автоматически: его явно подключают скрипты ниже.

```powershell
. ./scripts/env.ps1
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py createsuperuser
./scripts/start.ps1 web
```

Откройте [веб-панель](http://127.0.0.1:8000/). Войдите администратором, через [управление сотрудниками](http://127.0.0.1:8000/admin/) создайте двух сотрудников и включите им «Статус персонала». Оператор: активен и персонал; администратор: дополнительно суперпользователь. Не выдавайте оператору статус суперпользователя.

В двух дополнительных окнах PowerShell из той же папки:

```powershell
./scripts/start.ps1 bot
```

```powershell
./scripts/start.ps1 notifications
```

В личном чате бота отправьте `/start`, нажмите «Подать заявку». Статус: `/status З-000001`. Команда работает и во время подачи новой заявки. Чаты групп не обслуживаются.

Для Linux/macOS: `python3 -m venv .venv`, `.venv/bin/pip install -r requirements.lock`; задайте переменные через `export`, затем используйте `.venv/bin/python manage.py migrate`, `createsuperuser`, `runserver 127.0.0.1:8000`, `runbot`, `notify` в отдельных терминалах. PowerShell-скрипты нужны только Windows.

## Настройки

| Переменная | Назначение |
| --- | --- |
| DJANGO_SECRET_KEY | Случайный секрет сессий; обязателен для сетевого режима |
| DJANGO_DEBUG | `1` для локальной демонстрации, `0` для сети с HTTPS |
| DJANGO_ALLOWED_HOSTS | Разрешённые хосты через запятую; локально localhost,127.0.0.1 |
| DATABASE_PATH | Путь к общей SQLite; у всех трёх процессов должен совпадать |
| TELEGRAM_BOT_TOKEN | Токен бота, нужен runbot и notify |
| TEST_DATABASE_PATH | Отдельная тестовая БД для параллельных прогонов |

`runserver` предназначен для локальной демонстрации. Для размещения в сети нужны WSGI-сервер, HTTPS, `DJANGO_DEBUG=0`, свой секрет, разрешённый хост и `collectstatic`; сетевое размещение не требуется ТЗ. В режиме без DEBUG включены защищённые cookie, поэтому нужен HTTPS.

Классификатор 3×3 загружается миграцией. Администратор может переименовывать и отключать элементы, группы и сотрудников; удаления через интерфейс запрещены. Категория в старой заявке хранится снимком. Фильтр даты работает по дате создания включительно, Europe/Moscow.

## Демонстрационные данные

Для исследования веб-панели используйте отдельную БД:

```powershell
. ./scripts/env.ps1
$env:DATABASE_PATH = 'demo.sqlite3'
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py createsuperuser
.venv/Scripts/python.exe manage.py seed_demo
.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
```

`seed_demo` запрашивает пароль для operator1/operator2 и создаёт девять заявок без реального владельца Telegram. Повторный вызов не дублирует записи. Для этой БД не запускайте notify. Для живого цикла вернитесь к основной БД из `.env` и подайте новую заявку в настоящем чате.

## Проверки и замер

```powershell
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
.venv/Scripts/python.exe manage.py test tests --noinput
.venv/Scripts/python.exe scripts/benchmark.py --cycles 100 --users 4 --dataset 250 --warmup 5
```

Тестовая БД пересоздаётся только по TEST_DATABASE_PATH (по умолчанию `test.sqlite3`), рабочая БД не затрагивается. Benchmark создаёт отдельную БД и временный HTTP-сервер в `artifacts/`, завершает свой сервер после прогона. Он не отправляет сообщения Telegram. Результат — `docs/demo/performance.json`; методика и интерпретация в [отчёте](docs/demo/performance.md).

## Документы

- [Архитектура, сущности и правила доступа](docs/architecture.md)
- [Требования B/W/I/D/T](docs/requirements.md) и [исходные фотографии](docs/source/)
- [Инструкция оператора](docs/operator.md)
- [Живой сценарий защиты и фактический Telegram-прогон](docs/demo/scenario.md)
- [Матрица приёмки и ограничения](docs/acceptance.md)
- [Эксплуатация и доставка](docs/operations.md)

Репозиторий: [MidoriMacbook/tgbot](https://github.com/MidoriMacbook/tgbot), ветка реализации `prototype`.
