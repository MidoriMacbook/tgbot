import json
import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


def load_environment():
    load_dotenv(BASE_DIR / '.env', override=False, interpolate=False, encoding='utf-8-sig')


def env_bool(name, default=False):
    raw = os.environ.get(name, '').strip()
    value = raw.lower() if raw else ('1' if default else '0')
    if value not in {'1', '0', 'true', 'false', 'yes', 'no', 'on', 'off'}:
        raise ValueError(f'{name}: используйте 1 или 0.')
    return value in {'1', 'true', 'yes', 'on'}


def env_number(name, default, minimum, maximum, *, integer=False):
    try:
        value = (int if integer else float)(os.environ.get(name, str(default)))
    except ValueError:
        raise ValueError(f'{name}: требуется число.') from None
    if not minimum <= value <= maximum:
        raise ValueError(f'{name}: допустимый диапазон от {minimum} до {maximum}.')
    return value


def env_list(name, default=''):
    return [value.strip() for value in os.environ.get(name, default).split(',') if value.strip()]


def env_json(name, *, container=dict):
    try:
        value = json.loads(os.environ.get(name, '{}' if container is dict else '[]'))
    except (ValueError, TypeError):
        raise ValueError(f'{name}: требуется корректный JSON.') from None
    if not isinstance(value, container):
        label = 'объект' if container is dict else 'массив'
        raise ValueError(f'{name}: требуется JSON-{label}.')
    return value


def env_dict(name):
    return env_json(name)


def validate_bot_config(config):
    styles = ('primary', 'success', 'danger', None)
    if any(value not in styles for value in config['button_styles'].values()):
        raise ValueError('TELEGRAM_BUTTON_STYLES: допустимы primary, success и danger.')
    for item in config['emojis'].values():
        if not isinstance(item, dict) or not isinstance(item.get('fallback'), str) or not item['fallback']:
            raise ValueError('TELEGRAM_EMOJI: каждой иконке нужен текст fallback.')
        identifier = item.get('id', '')
        if not isinstance(identifier, str) or identifier and not identifier.isdecimal():
            raise ValueError('TELEGRAM_EMOJI: id должен быть строкой из цифр или пустой строкой.')
    for item in config['lower_buttons']:
        if (not isinstance(item, dict) or item.get('action') not in {'new', 'status', 'menu', 'panel'}
                or not isinstance(item.get('text'), str) or not item['text']
                or item.get('style') not in styles):
            raise ValueError('TELEGRAM_LOWER_BUTTONS: проверьте action, text и style кнопки.')
    if any(not isinstance(stage, dict) for stage in config['texts'].values()):
        raise ValueError('TELEGRAM_TEXTS: каждый этап должен быть JSON-объектом.')
    if config['lease_seconds'] <= config['notification_timeout']:
        raise ValueError('TELEGRAM_LEASE_SECONDS должен быть больше TELEGRAM_NOTIFY_TIMEOUT.')
