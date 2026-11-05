import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-only-change-before-network-use")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
if not DEBUG and SECRET_KEY == "local-only-change-before-network-use":
    raise RuntimeError("Задайте DJANGO_SECRET_KEY перед сетевым запуском")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "app.core"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "app.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "app/web/templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request",
    "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "app.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
    "NAME": os.environ.get("DATABASE_PATH", str(BASE_DIR / "data.sqlite3")),
    "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    "TEST": {"NAME": os.environ.get("TEST_DATABASE_PATH", str(BASE_DIR / "test.sqlite3"))}}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "app/web/static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
