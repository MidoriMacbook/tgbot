# Размещение на Pterodactyl и домене pur3.me

Подготовлен HTTP-сервис на `0.0.0.0:10064`. Внешний узел: `c-pl-2.apexnodes.xyz`, IPv4 на 5 ноября 2026 года — `54.36.168.206`. Публичный адрес без своего сертификата: `http://pur3.me:10064`.

## Pterodactyl

Используйте Python egg с Python 3.12 или новее. В Network/Allocation должен быть назначен TCP-порт `10064`. Загрузите проект из ветки `prototype`, установите зависимости `python -m pip install -r requirements.lock` и настройте локальный `.env`. Готовая клиентская сборка уже входит в проект, Node на сервере не требуется.

Команда запуска:

```bash
python run.py
```

Если egg требует имя файла, укажите `run.py`. Не запускайте параллельно ещё один процесс с тем же токеном. `run.py` сам выполняет миграции, создаёт главного оператора, собирает статику и в одном процессе Python поднимает сайт, polling бота и очередь уведомлений. Отдельные `runbot` и `notify` на этом контейнере не нужны: лишние процессы Python получают сигнал завершения и роняют весь запуск.

Основные значения `.env`:

```dotenv
HOST=0.0.0.0
PORT=10064
REMOTE_HOST=c-pl-2.apexnodes.xyz
PUBLIC_URL=http://pur3.me:10064
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,c-pl-2.apexnodes.xyz,pur3.me,www.pur3.me
DJANGO_CSRF_TRUSTED_ORIGINS=http://pur3.me:10064,http://www.pur3.me:10064,http://c-pl-2.apexnodes.xyz:10064
DJANGO_SECURE_COOKIES=
DJANGO_COOKIE_SAMESITE=None
TELEGRAM_ALLOW_EMBED=1
CHIEF_OPERATOR_USERNAME=admin
```

Задайте собственные `DJANGO_SECRET_KEY`, `CHIEF_OPERATOR_PASSWORD` и `TELEGRAM_BOT_TOKEN`. Bootstrap создаёт главного оператора только при отсутствии аккаунта; существующий пароль не меняет. Переменные, заданные в панели Pterodactyl, имеют приоритет над файлом `.env`.

## DNS без сертификата на контейнере

Запись DNS не содержит порт. Панель открывается как `http://pur3.me:10064`. В зоне **pur3.me**:

| Тип | Имя | Значение | Прокси | TTL |
| --- | --- | --- | --- | --- |
| A | @ | 54.36.168.206 | выключен | Auto |
| A | www | 54.36.168.206 | выключен | Auto |

Порт `:10064`, `http://` и путь в значение DNS не добавляются. Конфликтующие A/AAAA/CNAME для `@` и `www` нужно убрать, почтовые MX/TXT не трогать. После обновления DNS панель открывается по `http://pur3.me:10064` и `http://c-pl-2.apexnodes.xyz:10064`.

Если позже появится HTTPS через Cloudflare, записи можно перевести в Proxied и добавить Origin Rule на порт 10064. Тогда `PUBLIC_URL` меняется на `https://pur3.me`, а CSRF-origins — на `https://`. Пока сертификата нет, прокси домена включать не нужно.

Шаги Cloudflare, если HTTPS всё же понадобится:

1. Дождитесь активного edge-сертификата для `pur3.me`.
2. В SSL/TLS задайте **Flexible** для этой схемы с HTTP на origin. Клиентский участок остаётся HTTPS, участок Cloudflare → контейнер идёт без шифрования.
3. Создайте **Origin Rule** с условием `http.host in {"pur3.me" "www.pur3.me"}` и действием **Destination port: 10064**. Изменять Host header не нужно.
4. Включите перенаправление внешнего HTTP на HTTPS. В Django не включайте SECURE_SSL_REDIRECT при Flexible без корректной передачи схемы через доверенный прокси: это может создать цикл.
5. Откройте `https://pur3.me`, затем вход в панель. Прямой HTTP на allocation не является адресом Mini App.

Стандартный прокси Cloudflare не обслуживает произвольный порт `10064` в URL посетителя: нужен именно Origin Rule. Он меняет порт обращения к origin, а пользователь открывает стандартный HTTPS без порта.

## Telegram

В главном меню кнопка «Открыть панель» открывает `PUBLIC_URL` обычной ссылкой. Вход — логин и пароль, права не выдаются по данным Telegram.

Для Telegram Web разрешены frame ancestors только Telegram и собственный сайт. В нативном приложении Telegram используется WebView. Cookies для публичного HTTPS настроены Secure и SameSite=None; ограничения сторонних cookies конкретного браузера могут потребовать открыть панель отдельным окном.

## Границы этой настройки

Код и `.env` подготовлены локально. Записи DNS, Cloudflare и файлы удалённого контейнера автоматически не изменялись. Проверка опубликованного `pur3.me` возможна после загрузки проекта и применения настроек владельцем.

Официальные основания: [Telegram WebAppInfo](https://core.telegram.org/bots/api#webappinfo), [Cloudflare Origin Rules](https://developers.cloudflare.com/rules/origin-rules/), [порт назначения](https://developers.cloudflare.com/rules/origin-rules/features/#destination-port), [Flexible SSL](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/flexible/), [CNAME flattening](https://developers.cloudflare.com/dns/cname-flattening/).
