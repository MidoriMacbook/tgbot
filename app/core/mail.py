import json
import urllib.error
import urllib.request

from django.conf import settings


class MailError(Exception):
    pass


def mail_ready():
    return bool(settings.RESEND_API_KEY and settings.RESEND_FROM)


def send_login_code(email, code):
    if not mail_ready():
        raise MailError("Почта для кодов не настроена.")
    payload = json.dumps({
        "from": settings.RESEND_FROM,
        "to": [email],
        "subject": "Код входа в службу заявок",
        "text": f"Код входа: {code}\nОн действует 10 минут. Если вы не запрашивали код, проигнорируйте письмо.",
    }).encode()
    request = urllib.request.Request(
        "https://api.resend.com/emails", data=payload, method="POST",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}", "Content-Type": "application/json",
                 "User-Agent": "ticket-service"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise MailError("Не удалось отправить письмо. Повторите попытку позже.") from error
