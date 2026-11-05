import os
from urllib.parse import urlsplit

from app.config import BASE_DIR, env_bool, env_dict, env_json, env_list, env_number, load_environment, validate_bot_config

load_environment()
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-only-change-before-network-use")
DEBUG = env_bool('DJANGO_DEBUG', True)
TELEGRAM_CUSTOM_EMOJI = env_bool('TELEGRAM_CUSTOM_EMOJI', True)
if not DEBUG and SECRET_KEY in {"", "local-only-change-before-network-use", "replace-with-random-secret"}:
    raise RuntimeError("Задайте DJANGO_SECRET_KEY перед сетевым запуском")
HOST = os.environ.get('HOST', '0.0.0.0').strip()
PORT = env_number('PORT', 10064, 1, 65535, integer=True)
REMOTE_HOST = os.environ.get('REMOTE_HOST', 'c-pl-2.apexnodes.xyz').strip()
PUBLIC_URL = os.environ.get('PUBLIC_URL', f'http://{REMOTE_HOST}:{PORT}').strip().rstrip('/')
_public_parts = urlsplit(PUBLIC_URL)
if (_public_parts.scheme not in {'http', 'https'} or not _public_parts.hostname
        or _public_parts.username or _public_parts.password or _public_parts.query or _public_parts.fragment):
    raise ValueError('PUBLIC_URL: задайте полный HTTP или HTTPS адрес без пароля, параметров и фрагмента.')
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', f'localhost,127.0.0.1,testserver,{REMOTE_HOST},{_public_parts.hostname}')
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS',
                              f'{_public_parts.scheme}://{_public_parts.netloc}')
APP_BRAND = os.environ.get('APP_BRAND', 'Служба заявок').strip() or 'Служба заявок'
CHIEF_OPERATOR_USERNAME = os.environ.get('CHIEF_OPERATOR_USERNAME', 'admin').strip()
CHIEF_OPERATOR_NAME = os.environ.get('CHIEF_OPERATOR_NAME', 'Главный оператор').strip()
if not CHIEF_OPERATOR_USERNAME:
    raise ValueError('CHIEF_OPERATOR_USERNAME: укажите логин главного оператора.')
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "app.core"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "app.web.context_processors.FramePolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "app.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "app/web/templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request",
    "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages",
    "app.web.context_processors.application"]}}]
WSGI_APPLICATION = "app.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
    "NAME": BASE_DIR / os.environ.get("DATABASE_PATH", "data.sqlite3"),
    "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    "TEST": {"NAME": BASE_DIR / os.environ.get("TEST_DATABASE_PATH", "test.sqlite3")}}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "app/web/static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = env_bool('DJANGO_SECURE_COOKIES', _public_parts.scheme == 'https')
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', False)
SECURE_PROXY_SSL_HEADER = None
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
TELEGRAM_ALLOW_EMBED = env_bool('TELEGRAM_ALLOW_EMBED', False)
SESSION_COOKIE_SAMESITE = os.environ.get('DJANGO_COOKIE_SAMESITE',
    'None' if TELEGRAM_ALLOW_EMBED and SESSION_COOKIE_SECURE else 'Lax').strip()
if SESSION_COOKIE_SAMESITE not in {'Lax', 'Strict', 'None'}:
    raise ValueError('DJANGO_COOKIE_SAMESITE: допустимы Lax, Strict или None.')
if SESSION_COOKIE_SAMESITE == 'None' and not SESSION_COOKIE_SECURE:
    SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE
CSRF_FAILURE_VIEW = "app.web.views.csrf_failure"

BOT_CONFIG = {
    'token': os.environ.get('TELEGRAM_BOT_TOKEN', '').strip(),
    'username': os.environ.get('TELEGRAM_BOT_USERNAME', '').strip().lstrip('@'),
    'custom_emoji': TELEGRAM_CUSTOM_EMOJI,
    'public_url': PUBLIC_URL,
    'request_timeout': env_number('TELEGRAM_REQUEST_TIMEOUT', 35, 1, 300),
    'poll_timeout': env_number('TELEGRAM_POLL_TIMEOUT', 25, 1, 120, integer=True),
    'poll_retry': env_number('TELEGRAM_POLL_RETRY', 3, 0.1, 60),
    'notification_interval': env_number('TELEGRAM_NOTIFY_INTERVAL', 2, 0.1, 30),
    'notification_timeout': env_number('TELEGRAM_NOTIFY_TIMEOUT', 25, 1, 120),
    'notification_batch_size': env_number('TELEGRAM_NOTIFY_BATCH_SIZE', 30, 1, 1000, integer=True),
    'lease_seconds': env_number('TELEGRAM_LEASE_SECONDS', 60, 5, 600, integer=True),
    'retry_max_seconds': env_number('TELEGRAM_RETRY_MAX_SECONDS', 3600, 1, 86400, integer=True),
    'chunk_size': env_number('TELEGRAM_CHUNK_SIZE', 4000, 256, 4096, integer=True),
    'edit_messages': env_bool('TELEGRAM_EDIT_MESSAGES', True),
    'show_reply_keyboard': env_bool('TELEGRAM_SHOW_REPLY_KEYBOARD', True),
    'miniapp_enabled': env_bool('TELEGRAM_MINIAPP_ENABLED', True),
    'button_styles': env_dict('TELEGRAM_BUTTON_STYLES'),
    'button_labels': env_dict('TELEGRAM_BUTTON_LABELS'),
    'emojis': env_dict('TELEGRAM_EMOJI'),
    'category_icons': env_dict('TELEGRAM_CATEGORY_ICONS'),
    'texts': env_dict('TELEGRAM_TEXTS'),
    'lower_buttons': env_json('TELEGRAM_LOWER_BUTTONS', container=list),
}
validate_bot_config(BOT_CONFIG)
