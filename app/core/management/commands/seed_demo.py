import getpass
import os
import uuid
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from app.core.models import CategoryItem, Ticket
from app.core.services import create_ticket


class Command(BaseCommand):
    help = "Создать двух операторов и девять заявок для отдельной демонстрационной БД"

    @transaction.atomic
    def handle(self, *args, **options):
        new_users = [name for name in ('operator1', 'operator2') if not User.objects.filter(username=name).exists()]
        if new_users:
            password = os.environ.get('DEMO_PASSWORD') or getpass.getpass('Пароль демонстрационных операторов: ')
            try:
                validate_password(password)
            except ValidationError as exc:
                raise CommandError('; '.join(exc.messages))
            for index, name in enumerate(new_users, 1):
                User.objects.create_user(name, password=password, is_staff=True, first_name=f'Оператор {index}')
        for item in CategoryItem.objects.filter(active=True, group__active=True):
            key = uuid.uuid5(uuid.NAMESPACE_URL, f'local-demo-ticket/{item.pk}')
            if not Ticket.objects.filter(key=key).exists():
                create_ticket(telegram_id=0, applicant='Демонстрационный заявитель', item_id=item.pk,
                    description=f'Требуется проверить: {item.name}. Кабинет 101.',
                    contact='Демонстрация, кабинет 101', key=key)
        self.stdout.write(self.style.SUCCESS('Демонстрационные данные готовы. Операторы: operator1, operator2.'))
        self.stdout.write('Telegram ID = 0: эти записи предназначены только для веб-демонстрации. Не запускайте notify на этой БД.')
