import os
from urllib.parse import urlsplit

from app.bot.content import BUTTON_LABELS, BUTTON_STYLES, CATEGORY_ICONS, EMOJIS, LOWER_BUTTONS, TEXTS
from app.config import BASE_DIR, load_environment, validate_bot_config

load_environment()
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'local-only-change-before-network-use')
DEBUG = False
if SECRET_KEY in {'', 'local-only-change-before-network-use', 'replace-with-random-secret'}:
    raise RuntimeError('Задайте DJANGO_SECRET_KEY перед запуском')
HOST = '0.0.0.0'
PORT = 10064
WAITRESS_THREADS = 8
PUBLIC_URL = 'http://pur3.me:10064'
_public_parts = urlsplit(PUBLIC_URL)
if (_public_parts.scheme not in {'http', 'https'} or not _public_parts.hostname
        or _public_parts.username or _public_parts.password or _public_parts.query or _public_parts.fragment):
    raise ValueError('PUBLIC_URL: задайте полный HTTP или HTTPS адрес без пароля, параметров и фрагмента.')
ALLOWED_HOSTS = [
    'localhost', '127.0.0.1', 'testserver',
    'c-pl-2.apexnodes.xyz', _public_parts.hostname, 'www.pur3.me',
]
CSRF_TRUSTED_ORIGINS = [
    f'{_public_parts.scheme}://{_public_parts.netloc}',
    f'{_public_parts.scheme}://www.pur3.me:{PORT}',
    f'{_public_parts.scheme}://c-pl-2.apexnodes.xyz:{PORT}',
]
APP_BRAND = 'Служба заявок'
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '').strip()
RESEND_FROM = os.environ.get('RESEND_FROM', '').strip()
CHIEF_OPERATOR_EMAIL = os.environ.get('CHIEF_OPERATOR_EMAIL', '').strip().lower()
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'app.core']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'app.web.context_processors.FramePolicyMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'app.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'app/web/templates'], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': ['django.template.context_processors.request',
    'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages',
    'app.web.context_processors.application']}}]
WSGI_APPLICATION = 'app.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
    'NAME': BASE_DIR / 'data.sqlite3',
    'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'},
    'TEST': {'NAME': BASE_DIR / 'test.sqlite3'}}}
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'app/web/static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = _public_parts.scheme == 'https'
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = None
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
TELEGRAM_CUSTOM_EMOJI = True
TELEGRAM_ALLOW_EMBED = True
SESSION_COOKIE_SAMESITE = 'None' if TELEGRAM_ALLOW_EMBED and SESSION_COOKIE_SECURE else 'Lax'
CSRF_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE
CSRF_FAILURE_VIEW = 'app.web.views.csrf_failure'

BOT_CONFIG = {
    'token': os.environ.get('TELEGRAM_BOT_TOKEN', '').strip(),
    'username': os.environ.get('TELEGRAM_BOT_USERNAME', 'obrabotka68_bot').strip().lstrip('@'),
    'custom_emoji': TELEGRAM_CUSTOM_EMOJI,
    'public_url': PUBLIC_URL,
    'request_timeout': 10,
    'poll_timeout': 20,
    'poll_retry': 2,
    'notification_interval': 2,
    'notification_timeout': 25,
    'notification_batch_size': 100,
    'lease_seconds': 30,
    'retry_max_seconds': 30,
    'chunk_size': 3800,
    'edit_messages': True,
    'show_reply_keyboard': True,
    'miniapp_enabled': True,
    'button_styles': BUTTON_STYLES,
    'button_labels': BUTTON_LABELS,
    'emojis': EMOJIS,
    'category_icons': CATEGORY_ICONS,
    'texts': TEXTS,
    'lower_buttons': LOWER_BUTTONS,
}
validate_bot_config(BOT_CONFIG)
