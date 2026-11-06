import base64
import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from app.core.models import LoginGuard, StaffSecret

LOCK_MINUTES = 30
LOCK_AFTER = 3


def _key():
    return hashlib.sha256(settings.SECRET_KEY.encode()).digest()


def seal(value):
    raw = str(value).encode()
    key = _key()
    stream = b""
    counter = 0
    while len(stream) < len(raw):
        stream += hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
        counter += 1
    cipher = bytes(left ^ right for left, right in zip(raw, stream))
    mac = hmac.new(key, cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac + cipher).decode()


def open_seal(value):
    try:
        packed = base64.urlsafe_b64decode(value.encode())
        mac, cipher = packed[:32], packed[32:]
        key = _key()
        if not hmac.compare_digest(mac, hmac.new(key, cipher, hashlib.sha256).digest()):
            raise ValueError
        stream = b""
        counter = 0
        while len(stream) < len(cipher):
            stream += hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
            counter += 1
        return bytes(left ^ right for left, right in zip(cipher, stream)).decode()
    except (ValueError, UnicodeError):
        return ""


def remember_password(user, password):
    StaffSecret.objects.update_or_create(user=user, defaults={"sealed": seal(password)})


def reveal_password(user):
    secret = getattr(user, "secret", None)
    if secret is None:
        secret = StaffSecret.objects.filter(user=user).first()
    return open_seal(secret.sealed) if secret else ""


def login_locked(username):
    guard = LoginGuard.objects.filter(username=username).first()
    return bool(guard and guard.locked_until and guard.locked_until > timezone.now())


@transaction.atomic
def note_login_failure(username):
    guard, _ = LoginGuard.objects.select_for_update().get_or_create(username=username[:150])
    now = timezone.now()
    if guard.locked_until and guard.locked_until > now:
        return
    if guard.locked_until and guard.locked_until <= now:
        guard.failures = 0
        guard.locked_until = None
    guard.failures += 1
    if guard.failures >= LOCK_AFTER:
        guard.failures = 0
        guard.locked_until = now + timedelta(minutes=LOCK_MINUTES)
    guard.save()


@transaction.atomic
def note_login_success(username):
    LoginGuard.objects.filter(username=username).update(failures=0, locked_until=None)
