# Размещение на Pterodactyl и домене pur3.me

Подготовлен HTTP-сервис на `0.0.0.0:10064`. Внешний узел: `c-pl-2.apexnodes.xyz`, IPv4 на 5 ноября 2026 года — `54.36.168.206`. Публичный адрес приложения: `https://pur3.me`.

## Pterodactyl

Используйте Python egg с Python 3.12 или новее. В Network/Allocation должен быть назначен TCP-порт `10064`. Загрузите проект из ветки `prototype`, установите зависимости `python -m pip install -r requirements.lock` и настройте локальный `.env`. Готовая клиентская сборка уже входит в проект, Node на сервере не требуется.

Команда запуска:

```bash
python run.py
```

Если egg требует имя файла, укажите `run.py`; если он принимает startup command — команду выше. Не запускайте параллельно ещё один runbot с тем же токеном. Polling не требует Telegram webhook. Launcher сам выполняет миграции/bootstrap/collectstatic и запускает сайт, бота и уведомления; настройки подготовки можно отключить соответствующими AUTO_* переменными.

Основные значения `.env`:

```dotenv
HOST=0.0.0.0
PORT=10064
REMOTE_HOST=c-pl-2.apexnodes.xyz
PUBLIC_URL=https://pur3.me
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,c-pl-2.apexnodes.xyz,pur3.me,www.pur3.me
DJANGO_CSRF_TRUSTED_ORIGINS=https://pur3.me,https://www.pur3.me
DJANGO_SECURE_COOKIES=
DJANGO_COOKIE_SAMESITE=None
TELEGRAM_ALLOW_EMBED=1
CHIEF_OPERATOR_USERNAME=admin
```

Задайте собственные `DJANGO_SECRET_KEY`, `CHIEF_OPERATOR_PASSWORD` и `TELEGRAM_BOT_TOKEN`. Bootstrap создаёт главного оператора только при отсутствии аккаунта; существующий пароль не меняет. Переменные, заданные в панели Pterodactyl, имеют приоритет над файлом `.env`.

## DNS через Cloudflare, без сертификата внутри контейнера

Обычная DNS-запись не указывает порт и не превращает HTTP в HTTPS. Для указанной схемы Cloudflare принимает HTTPS от пользователя и передаёт запрос на HTTP allocation `10064`. Понадобятся следующие записи в зоне **pur3.me**:

| Тип | Имя | Значение | Proxy | TTL |
| --- | --- | --- | --- | --- |
| A | @ | 54.36.168.206 | Proxied | Auto |
| CNAME | www | pur3.me | Proxied | Auto |

Вместо A на корне Cloudflare допускает CNAME `@ → c-pl-2.apexnodes.xyz` с flattening. Используйте один вариант корневой записи. Порт `:10064`, `http://` и путь в значение DNS не добавляются. Существующие конфликтующие A/AAAA/CNAME нужно согласовать с выбранным вариантом, не затрагивая почтовые MX/TXT.

Затем в Cloudflare:

1. Дождитесь активного edge-сертификата для `pur3.me`.
2. В SSL/TLS задайте **Flexible** для этой схемы с HTTP на origin. Клиентский участок остаётся HTTPS, участок Cloudflare → контейнер идёт без шифрования.
3. Создайте **Origin Rule** с условием `http.host in {"pur3.me" "www.pur3.me"}` и действием **Destination port: 10064**. Изменять Host header не нужно.
4. Включите перенаправление внешнего HTTP на HTTPS. В Django не включайте SECURE_SSL_REDIRECT при Flexible без корректной передачи схемы через доверенный прокси: это может создать цикл.
5. Откройте `https://pur3.me`, затем вход в панель. Прямой HTTP на allocation не является адресом Mini App.

Стандартный прокси Cloudflare не обслуживает произвольный порт `10064` в URL посетителя: нужен именно Origin Rule. Он меняет порт обращения к origin, а пользователь открывает стандартный HTTPS без порта.

Если DNS обслуживается у другого провайдера, одна A-запись даст только `http://pur3.me:10064`. Для Telegram Mini App потребуется внешний HTTPS-прокси провайдера/хостинга либо отдельный прокси с автоматическим сертификатом; сама DNS эту задачу не решает.

## Telegram

Кнопка «Открыть панель» использует HTTPS-адрес из `PUBLIC_URL`. При необходимости главное меню Mini App можно настроить в BotFather, указав `https://pur3.me`. При входе используются логин и пароль сотрудника, права не выдаются по неподтверждённым данным Telegram.

Для Telegram Web разрешены frame ancestors только Telegram и собственный сайт. В нативном приложении Telegram используется WebView. Cookies для публичного HTTPS настроены Secure и SameSite=None; ограничения сторонних cookies конкретного браузера могут потребовать открыть панель отдельным окном.

## Границы этой настройки

Код и `.env` подготовлены локально. Записи DNS, Cloudflare и файлы удалённого контейнера автоматически не изменялись. Проверка опубликованного `pur3.me` возможна после загрузки проекта и применения настроек владельцем.

Официальные основания: [Telegram WebAppInfo](https://core.telegram.org/bots/api#webappinfo), [Cloudflare Origin Rules](https://developers.cloudflare.com/rules/origin-rules/), [порт назначения](https://developers.cloudflare.com/rules/origin-rules/features/#destination-port), [Flexible SSL](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/flexible/), [CNAME flattening](https://developers.cloudflare.com/dns/cname-flattening/).
