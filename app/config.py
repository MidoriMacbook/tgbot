import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


def load_environment():
    load_dotenv(BASE_DIR / '.env', override=False, interpolate=False, encoding='utf-8-sig')


def validate_bot_config(config):
    styles = ('primary', 'success', 'danger', None)
    if any(value not in styles for value in config['button_styles'].values()):
        raise ValueError('Стили кнопок: допустимы primary, success и danger.')
    for item in config['emojis'].values():
        if not isinstance(item, dict) or not isinstance(item.get('fallback'), str) or not item['fallback']:
            raise ValueError('Каждой иконке бота нужен текст fallback.')
        identifier = item.get('id', '')
        if not isinstance(identifier, str) or identifier and not identifier.isdecimal():
            raise ValueError('Идентификатор иконки должен быть строкой из цифр или пустой строкой.')
    for item in config['lower_buttons']:
        if (not isinstance(item, dict) or item.get('action') not in {'new', 'status', 'menu', 'panel'}
                or not isinstance(item.get('text'), str) or not item['text']
                or item.get('style') not in styles):
            raise ValueError('Проверьте action, text и style нижней кнопки.')
    if any(not isinstance(stage, dict) for stage in config['texts'].values()):
        raise ValueError('Каждый этап диалога должен быть объектом с текстами.')
    if config['lease_seconds'] <= config['notification_timeout']:
        raise ValueError('Аренда уведомления должна быть дольше таймаута отправки.')
