import asyncio
import logging
import ssl

from asgiref.sync import sync_to_async
from django.conf import settings

from app.bot.dialog import keeps_current_screen, normalize_input, opens_fresh_message, process_input
from app.bot.emoji import get_icon
from app.bot.presentation import reply_content
from app.core.models import BotCursor, BotDialog
from app.core.notifications import complete_notification, take_notification


logger = logging.getLogger(__name__)
API = "https://platform-api2.max.ru"
TEXT_LIMIT = 4000


def note(text):
    print(text, flush=True)


def safe_failure(error):
    if isinstance(error, MaxError):
        return str(error)[:180]
    text = str(error).replace("\n", " ")
    return (text[:180] or error.__class__.__name__)


class MaxError(Exception):
    def __init__(self, status, detail=""):
        self.status = status
        self.detail = detail
        message = f"код {status}"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)


def config():
    return getattr(settings, "BOT_CONFIG", {})


# Корневой и промежуточный сертификаты Минцифры. Ими подписан platform-api2.max.ru,
# а в хранилище контейнера Pterodactyl их нет.
RUSSIAN_CA = """
-----BEGIN CERTIFICATE-----
MIIFwjCCA6qgAwIBAgICEAAwDQYJKoZIhvcNAQELBQAwcDELMAkGA1UEBhMCUlUx
PzA9BgNVBAoMNlRoZSBNaW5pc3RyeSBvZiBEaWdpdGFsIERldmVsb3BtZW50IGFu
ZCBDb21tdW5pY2F0aW9uczEgMB4GA1UEAwwXUnVzc2lhbiBUcnVzdGVkIFJvb3Qg
Q0EwHhcNMjIwMzAxMjEwNDE1WhcNMzIwMjI3MjEwNDE1WjBwMQswCQYDVQQGEwJS
VTE/MD0GA1UECgw2VGhlIE1pbmlzdHJ5IG9mIERpZ2l0YWwgRGV2ZWxvcG1lbnQg
YW5kIENvbW11bmljYXRpb25zMSAwHgYDVQQDDBdSdXNzaWFuIFRydXN0ZWQgUm9v
dCBDQTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAMfFOZ8pUAL3+r2n
qqE0Zp52selXsKGFYoG0GM5bwz1bSFtCt+AZQMhkWQheI3poZAToYJu69pHLKS6Q
XBiwBC1cvzYmUYKMYZC7jE5YhEU2bSL0mX7NaMxMDmH2/NwuOVRj8OImVa5s1F4U
zn4Kv3PFlDBjjSjXKVY9kmjUBsXQrIHeaqmUIsPIlNWUnimXS0I0abExqkbdrXbX
YwCOXhOO2pDUx3ckmJlCMUGacUTnylyQW2VsJIyIGA8V0xzdaeUXg0VZ6ZmNUr5Y
Ber/EAOLPb8NYpsAhJe2mXjMB/J9HNsoFMBFJ0lLOT/+dQvjbdRZoOT8eqJpWnVD
U+QL/qEZnz57N88OWM3rabJkRNdU/Z7x5SFIM9FrqtN8xewsiBWBI0K6XFuOBOTD
4V08o4TzJ8+Ccq5XlCUW2L48pZNCYuBDfBh7FxkB7qDgGDiaftEkZZfApRg2E+M9
G8wkNKTPLDc4wH0FDTijhgxR3Y4PiS1HL2Zhw7bD3CbslmEGgfnnZojNkJtcLeBH
BLa52/dSwNU4WWLubaYSiAmA9IUMX1/RpfpxOxd4Ykmhz97oFbUaDJFipIggx5sX
ePAlkTdWnv+RWBxlJwMQ25oEHmRguNYf4Zr/Rxr9cS93Y+mdXIZaBEE0KS2iLRqa
OiWBki9IMQU4phqPOBAaG7A+eP8PAgMBAAGjZjBkMB0GA1UdDgQWBBTh0YHlzlpf
BKrS6badZrHF+qwshzAfBgNVHSMEGDAWgBTh0YHlzlpfBKrS6badZrHF+qwshzAS
BgNVHRMBAf8ECDAGAQH/AgEEMA4GA1UdDwEB/wQEAwIBhjANBgkqhkiG9w0BAQsF
AAOCAgEAALIY1wkilt/urfEVM5vKzr6utOeDWCUczmWX/RX4ljpRdgF+5fAIS4vH
tmXkqpSCOVeWUrJV9QvZn6L227ZwuE15cWi8DCDal3Ue90WgAJJZMfTshN4OI8cq
W9E4EG9wglbEtMnObHlms8F3CHmrw3k6KmUkWGoa+/ENmcVl68u/cMRl1JbW2bM+
/3A+SAg2c6iPDlehczKx2oa95QW0SkPPWGuNA/CE8CpyANIhu9XFrj3RQ3EqeRcS
AQQod1RNuHpfETLU/A2gMmvn/w/sx7TB3W5BPs6rprOA37tutPq9u6FTZOcG1Oqj
C/B7yTqgI7rbyvox7DEXoX7rIiEqyNNUguTk/u3SZ4VXE2kmxdmSh3TQvybfbnXV
4JbCZVaqiZraqc7oZMnRoWrXRG3ztbnbes/9qhRGI7PqXqeKJBztxRTEVj8ONs1d
WN5szTwaPIvhkhO3CO5ErU2rVdUr89wKpNXbBODFKRtgxUT70YpmJ46VVaqdAhOZ
D9EUUn4YaeLaS8AjSF/h7UkjOibNc4qVDiPP+rkehFWM66PVnP1Msh93tc+taIfC
EYVMxjh8zNbFuoc7fzvvrFILLe7ifvEIUqSVIC/AzplM/Jxw7buXFeGP1qVCBEHq
391d/9RAfaZ12zkwFsl+IKwE/OZxW8AHa9i1p4GO0YSNuczzEm4=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIHQjCCBSqgAwIBAgICEAIwDQYJKoZIhvcNAQELBQAwcDELMAkGA1UEBhMCUlUx
PzA9BgNVBAoMNlRoZSBNaW5pc3RyeSBvZiBEaWdpdGFsIERldmVsb3BtZW50IGFu
ZCBDb21tdW5pY2F0aW9uczEgMB4GA1UEAwwXUnVzc2lhbiBUcnVzdGVkIFJvb3Qg
Q0EwHhcNMjIwMzAyMTEyNTE5WhcNMjcwMzA2MTEyNTE5WjBvMQswCQYDVQQGEwJS
VTE/MD0GA1UECgw2VGhlIE1pbmlzdHJ5IG9mIERpZ2l0YWwgRGV2ZWxvcG1lbnQg
YW5kIENvbW11bmljYXRpb25zMR8wHQYDVQQDDBZSdXNzaWFuIFRydXN0ZWQgU3Vi
IENBMIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEA9YPqBKOk19NFymrE
wehzrhBEgT2atLezpduB24mQ7CiOa/HVpFCDRZzdxqlh8drku408/tTmWzlNH/br
HuQhZ/miWKOf35lpKzjyBd6TPM23uAfJvEOQ2/dnKGGJbsUo1/udKSvxQwVHpVv3
S80OlluKfhWPDEXQpgyFqIzPoxIQTLZ0deirZwMVHarZ5u8HqHetRuAtmO2ZDGQn
vVOJYAjls+Hiueq7Lj7Oce7CQsTwVZeP+XQx28PAaEZ3y6sQEt6rL06ddpSdoTMp
BnCqTbxW+eWMyjkIn6t9GBtUV45yB1EkHNnj2Ex4GwCiN9T84QQjKSr+8f0psGrZ
vPbCbQAwNFJjisLixnjlGPLKa5vOmNwIh/LAyUW5DjpkCx004LPDuqPpFsKXNKpa
L2Dm6uc0x4Jo5m+gUTVORB6hOSzWnWDj2GWfomLzzyjG81DRGFBpco/O93zecsIN
3SL2Ysjpq1zdoS01CMYxie//9zWvYwzI25/OZigtnpCIrcd2j1Y6dMUFQAzAtHE+
qsXflSL8HIS+IJEFIQobLlYhHkoE3avgNx5jlu+OLYe0dF0Ykx1PGNjbwqvTX37R
Cn32NMjlotW2QcGEZhDKj+3urZizp5xdTPZitA+aEjZM/Ni71VOdiOP0igbw6asZ
2fxdozZ1TnSSYNYvNATwthNmZysCAwEAAaOCAeUwggHhMBIGA1UdEwEB/wQIMAYB
Af8CAQAwDgYDVR0PAQH/BAQDAgGGMB0GA1UdDgQWBBTR4XENCy2BTm6KSo9MI7NM
XqtpCzAfBgNVHSMEGDAWgBTh0YHlzlpfBKrS6badZrHF+qwshzCBxwYIKwYBBQUH
AQEEgbowgbcwOwYIKwYBBQUHMAKGL2h0dHA6Ly9yb3N0ZWxlY29tLnJ1L2NkcC9y
b290Y2Ffc3NsX3JzYTIwMjIuY3J0MDsGCCsGAQUFBzAChi9odHRwOi8vY29tcGFu
eS5ydC5ydS9jZHAvcm9vdGNhX3NzbF9yc2EyMDIyLmNydDA7BggrBgEFBQcwAoYv
aHR0cDovL3JlZXN0ci1wa2kucnUvY2RwL3Jvb3RjYV9zc2xfcnNhMjAyMi5jcnQw
gbAGA1UdHwSBqDCBpTA1oDOgMYYvaHR0cDovL3Jvc3RlbGVjb20ucnUvY2RwL3Jv
b3RjYV9zc2xfcnNhMjAyMi5jcmwwNaAzoDGGL2h0dHA6Ly9jb21wYW55LnJ0LnJ1
L2NkcC9yb290Y2Ffc3NsX3JzYTIwMjIuY3JsMDWgM6Axhi9odHRwOi8vcmVlc3Ry
LXBraS5ydS9jZHAvcm9vdGNhX3NzbF9yc2EyMDIyLmNybDANBgkqhkiG9w0BAQsF
AAOCAgEARBVzZls79AdiSCpar15dA5Hr/rrT4WbrOfzlpI+xrLeRPrUG6eUWIW4v
Sui1yx3iqGLCjPcKb+HOTwoRMbI6ytP/ndp3TlYua2advYBEhSvjs+4vDZNwXr/D
anbwIWdurZmViQRBDFebpkvnIvru/RpWud/5r624Wp8voZMRtj/cm6aI9LtvBfT9
cfzhOaexI/99c14dyiuk1+6QhdwKaCRTc1mdfNQmnfWNRbfWhWBlK3h4GGE9JK33
Gk8ZS8DMrkdAh0xby4xAQ/mSWAfWrBmfzlOqGyoB1U47WTOeqNbWkkoAP2ys94+s
Jg4NTkiDVtXRF6nr6fYi0bSOvOFg0IQrMXO2Y8gyg9ARdPJwKtvWX8VPADCYMiWH
h4n8bZokIrImVKLDQKHY4jCsND2HHdJfnrdL2YJw1qFskNO4cSNmZydw0Wkgjv9k
F+KxqrDKlB8MZu2Hclph6v/CZ0fQ9YuE8/lsHZ0Qc2HyiSMnvjgK5fDc3TD4fa8F
E8gMNurM+kV8PT8LNIM+4Zs+LKEV8nqRWBaxkIVJGekkVKO8xDBOG/aN62AZKHOe
GcyIdu7yNMMRihGVZCYr8rYiJoKiOzDqOkPkLOPdhtVlgnhowzHDxMHND/E2WA5p
ZHuNM/m0TXt2wTTPL7JH2YC0gPz/BvvSzjksgzU5rLbRyUKQkgU=
-----END CERTIFICATE-----
"""


def max_ssl():
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=RUSSIAN_CA)
    return context


def person_name(user):
    name = str(user.get("name") or "").strip()
    if name:
        return name[:200]
    parts = [str(user.get("first_name") or "").strip(), str(user.get("last_name") or "").strip()]
    return " ".join(part for part in parts if part)[:200] or str(user.get("user_id") or "")


def person_nick(user):
    return str(user.get("username") or "").strip().lstrip("@")[:64]


def chat_number(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def command_text(value):
    if not isinstance(value, str) or not value.startswith("/"):
        return value
    head, _, rest = value.strip().partition(" ")
    head = head.split("@", 1)[0]
    return f"{head} {rest}".strip() if rest else head


def read_event(update):
    kind = update.get("update_type")
    if kind == "bot_started":
        user = update.get("user") or {}
        if user.get("is_bot") or not user.get("user_id"):
            return None
        return {"user_id": int(user["user_id"]), "chat_id": chat_number(update.get("chat_id")),
            "name": person_name(user), "nickname": person_nick(user),
            "text": "/start", "callback": None, "callback_id": "", "message_mid": ""}
    if kind == "message_created":
        message = update.get("message") or {}
        recipient = message.get("recipient") or {}
        sender = message.get("sender") or {}
        if recipient.get("chat_type") in {"chat", "channel"} or sender.get("is_bot") or not sender.get("user_id"):
            return None
        body = message.get("body") or {}
        return {"user_id": int(sender["user_id"]), "chat_id": chat_number(recipient.get("chat_id")),
            "name": person_name(sender), "nickname": person_nick(sender),
            "text": command_text(body.get("text") or ""), "callback": None, "callback_id": "",
            "message_mid": str(body.get("mid") or "")}
    if kind == "message_callback":
        callback = update.get("callback") or {}
        user = callback.get("user") or {}
        message = update.get("message") or {}
        recipient = message.get("recipient") or {}
        if recipient.get("chat_type") in {"chat", "channel"} or user.get("is_bot") or not user.get("user_id"):
            return None
        body = message.get("body") or {}
        return {"user_id": int(user["user_id"]), "chat_id": chat_number(recipient.get("chat_id")),
            "name": person_name(user), "nickname": person_nick(user),
            "text": None, "callback": str(callback.get("payload") or ""),
            "callback_id": str(callback.get("callback_id") or ""), "message_mid": str(body.get("mid") or "")}
    return None


MARKED_BUTTONS = {"new", "status", "back", "confirm", "menu"}


def button_rows(reply):
    rows = []
    for row in reply.keyboard:
        buttons = []
        for button in row:
            kind = button.data.partition(":")[0]
            _, fallback = get_icon(button.icon) if button.icon else ("", "")
            marked = kind in MARKED_BUTTONS and fallback not in {"", "•", "✨"}
            text = f"{fallback} {button.text}" if marked else button.text
            if button.url:
                buttons.append({"type": "link", "text": text[:128], "url": button.url})
            else:
                buttons.append({"type": "callback", "text": text[:128], "payload": button.data[:1024]})
        if buttons:
            rows.append(buttons)
    return rows


def max_idle_text():
    return (
        "🌀 Служба заявок\n\n"
        "▞▟ Это бот, где можно подать заявку на тему оборудования, помещений, обслуживания и узнать её статус.\n\n"
        "► Для возврата из любого меню бота используйте /start"
    )


def message_body(reply):
    stage = config().get("texts", {}).get("idle", {})
    if reply.stage == "idle" and reply.text == stage.get("prompt"):
        text, _entities = max_idle_text(), None
    else:
        text, _entities = reply_content(reply, custom=False).render()
    pieces = []
    start = 0
    while start < len(text):
        end = start
        size = 0
        while end < len(text):
            width = len(text[end].encode("utf-16-le")) // 2
            if size + width > TEXT_LIMIT:
                break
            size += width
            end += 1
        if end == start:
            end += 1
        pieces.append(text[start:end])
        start = end
    return pieces or [""]


def keyboard_attachment(reply):
    rows = button_rows(reply)
    if not rows:
        return []
    return [{"type": "inline_keyboard", "payload": {"buttons": rows}}]


def screen_plan(previous, reply, event, stored_mid):
    raw = (event["text"] or "").strip() if isinstance(event["text"], str) else ""
    command = raw.split(maxsplit=1)[0].split("@", 1)[0] if raw.startswith("/") else ""
    if not config().get("edit_messages", True) or command or opens_fresh_message(previous, reply.stage):
        return "", command in {"", "/start"}
    if event["callback"] is not None and event["message_mid"]:
        return event["message_mid"], True
    if (raw and keeps_current_screen(normalize_input(raw)) or previous in {"group", "item", "description", "name", "contact", "confirm"}):
        return stored_mid, True
    return "", True


class MaxApi:
    def __init__(self, token):
        self.token = token
        self.session = None

    async def __aenter__(self):
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=config().get("poll_timeout", 20) + 15)
        connector = aiohttp.TCPConnector(ssl=max_ssl())
        self.session = aiohttp.ClientSession(timeout=timeout, connector=connector, headers={"Authorization": self.token})
        return self

    async def __aexit__(self, *_args):
        await self.session.close()

    async def call(self, method, path, *, params=None, payload=None, read_timeout=None):
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=read_timeout) if read_timeout else None
        async with self.session.request(method, API + path, params=params, json=payload, timeout=timeout) as response:
            try:
                data = await response.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError):
                data = {}
            if response.status >= 400 or (isinstance(data, dict) and data.get("success") is False):
                detail = ""
                if isinstance(data, dict):
                    detail = str(data.get("message") or data.get("error") or "")
                raise MaxError(response.status if response.status >= 400 else 400, detail.replace("\n", " ")[:120])
            return data if isinstance(data, dict) else {}


def message_mid(data):
    message = data.get("message") or {}
    body = message.get("body") or {}
    return str(body.get("mid") or message.get("mid") or "")


def dialog_step(user_id):
    return BotDialog.objects.filter(platform="max", telegram_id=user_id).values_list("step", flat=True).first() or "idle"


def stored_mid(user_id):
    return BotDialog.objects.filter(platform="max", telegram_id=user_id).values_list("screen_mid", flat=True).first() or ""


def remember_mid(user_id, mid):
    if mid:
        BotDialog.objects.filter(platform="max", telegram_id=user_id).update(screen_mid=mid)


def cursor():
    row, _ = BotCursor.objects.get_or_create(name="max")
    return row


async def send_pieces(api, user_id, pieces, reply, *, edit_mid="", callback_id=""):
    sent = ""
    for index, piece in enumerate(pieces):
        attachments = keyboard_attachment(reply) if index == len(pieces) - 1 else []
        payload = {"text": piece}
        if attachments:
            payload["attachments"] = attachments
        if index == 0 and callback_id and edit_mid:
            await api.call("POST", "/answers", params={"callback_id": callback_id}, payload={"message": payload},
                read_timeout=config().get("request_timeout", 10))
            sent = edit_mid
            continue
        if index == 0 and edit_mid:
            await api.call("PUT", "/messages", params={"message_id": edit_mid}, payload=payload,
                read_timeout=config().get("request_timeout", 10))
            sent = edit_mid
            continue
        data = await api.call("POST", "/messages", params={"user_id": user_id}, payload=payload,
            read_timeout=config().get("request_timeout", 10))
        sent = message_mid(data) or sent
    if callback_id and not edit_mid:
        try:
            await api.call("POST", "/answers", params={"callback_id": callback_id}, payload={},
                read_timeout=config().get("request_timeout", 10))
        except MaxError:
            logger.warning("Не удалось подтвердить нажатие кнопки MAX.")
    return sent


def marker_value(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


async def send_plain(api, user_id):
    rows = [[{"type": "callback", "text": "Подать заявку", "payload": "new"}],
        [{"type": "callback", "text": "Узнать статус", "payload": "status"}]]
    data = await api.call("POST", "/messages", params={"user_id": user_id}, payload={
        "text": "Служба заявок\n\nЧтобы начать, нажмите кнопку или отправьте /start",
        "attachments": [{"type": "inline_keyboard", "payload": {"buttons": rows}}]},
        read_timeout=config().get("request_timeout", 10))
    return message_mid(data)


async def show(api, event, reply, previous):
    stored = await sync_to_async(stored_mid, thread_sensitive=True)(event["user_id"])
    edit_mid, remember = screen_plan(previous, reply, event, stored)
    try:
        mid = await send_pieces(api, event["user_id"], message_body(reply), reply,
            edit_mid=edit_mid, callback_id=event["callback_id"])
    except MaxError as error:
        note(f"MAX не принял сообщение: {safe_failure(error)}")
        try:
            mid = await send_plain(api, event["user_id"])
        except (MaxError, OSError, TimeoutError) as second:
            note(f"MAX не отправил ответ: {safe_failure(second)}")
            return
    if remember:
        await sync_to_async(remember_mid, thread_sensitive=True)(event["user_id"], mid)


async def handle(api, update):
    import aiohttp
    kind = update.get("update_type") if isinstance(update, dict) else ""
    event = read_event(update)
    if event is None:
        if kind:
            note(f"MAX пропустил событие {kind}.")
        return
    note("MAX получил сообщение.")
    previous = await sync_to_async(dialog_step, thread_sensitive=True)(event["user_id"])
    reply = await sync_to_async(process_input, thread_sensitive=True)(
        event["user_id"], event["name"], event["text"], callback=event["callback"],
        platform="max", nickname=event["nickname"], chat_id=event.get("chat_id") or 0)
    try:
        await show(api, event, reply, previous)
    except (MaxError, aiohttp.ClientError, TimeoutError, OSError) as error:
        note(f"MAX не отправил ответ: {safe_failure(error)}")


async def poll(api, stop):
    import aiohttp
    connected = False
    while not stop.is_set():
        try:
            row = await sync_to_async(cursor, thread_sensitive=True)()
            params = [("limit", 100), ("timeout", min(config().get("poll_timeout", 20), 30))]
            marker = marker_value(row.offset)
            if marker:
                params.append(("marker", marker))
            try:
                data = await api.call("GET", "/updates", params=params,
                    read_timeout=config().get("poll_timeout", 20) + 30)
            except (MaxError, aiohttp.ClientError, TimeoutError, OSError) as error:
                note(f"MAX не отдал события: {safe_failure(error)}. Повтор через 2 секунды.")
                await asyncio.sleep(config().get("poll_retry", 2))
                continue
            if not isinstance(data, dict):
                note("MAX прислал пустой ответ. Повтор через 2 секунды.")
                await asyncio.sleep(config().get("poll_retry", 2))
                continue
            if not connected:
                connected = True
                note("MAX подключён и ждёт сообщения.")
            updates = data.get("updates") if isinstance(data.get("updates"), list) else []
            for update in updates:
                kind = update.get("update_type") if isinstance(update, dict) else ""
                try:
                    await handle(api, update)
                except Exception as error:
                    note(f"MAX не обработал событие {kind}: {safe_failure(error)}")
            next_marker = marker_value(data.get("marker"))
            if next_marker is not None and next_marker != row.offset:
                row.offset = next_marker
                await sync_to_async(row.save, thread_sensitive=True)(update_fields=["offset"])
        except Exception as error:
            note(f"MAX прервал ожидание: {safe_failure(error)}. Повтор через 2 секунды.")
            await asyncio.sleep(config().get("poll_retry", 2))


async def deliver(api, stop):
    import aiohttp
    interval = config().get("notification_interval", 2)
    while not stop.is_set():
        payload = await sync_to_async(take_notification, thread_sensitive=True)(platform="max")
        if payload is None:
            try:
                await asyncio.wait_for(stop.wait(), interval)
            except asyncio.TimeoutError:
                pass
            continue
        pk, user_id, text = payload
        error = None
        try:
            await api.call("POST", "/messages", params={"user_id": user_id}, payload={"text": text[:TEXT_LIMIT]},
                read_timeout=config().get("request_timeout", 10))
        except (MaxError, aiohttp.ClientError, TimeoutError, OSError) as exc:
            error = exc
            logger.warning("Уведомление MAX останется в очереди и будет отправлено повторно.")
        await sync_to_async(complete_notification, thread_sensitive=True)(pk, error, platform="max")


async def drop_webhooks(api):
    # Пустой DELETE даёт код 400: MAX ждёт адрес конкретной подписки.
    # Пока подписка есть, события уходят на webhook, и бот в опросе молчит.
    try:
        data = await api.call("GET", "/subscriptions", read_timeout=10)
    except Exception as error:
        note(f"Подписки webhook MAX не прочитаны: {safe_failure(error)}")
        return
    subscriptions = data.get("subscriptions") if isinstance(data, dict) else None
    if not isinstance(subscriptions, list) or not subscriptions:
        note("Подписок webhook MAX нет.")
        return
    for item in subscriptions:
        url = item.get("url") if isinstance(item, dict) else ""
        if not isinstance(url, str) or not url:
            note("Подписка webhook MAX без адреса, снять её не удалось.")
            continue
        try:
            await api.call("DELETE", "/subscriptions", params={"url": url}, read_timeout=10)
        except Exception as error:
            note(f"Подписка webhook MAX не снята: {safe_failure(error)}")
            return
    note("Подписки webhook MAX сняты.")


async def run(token, stop):
    try:
        async with MaxApi(token) as api:
            await drop_webhooks(api)
            tasks = [asyncio.create_task(poll(api, stop)), asyncio.create_task(deliver(api, stop))]
            try:
                await stop.wait()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as error:
        note(f"Бот MAX остановился: {safe_failure(error)}")
