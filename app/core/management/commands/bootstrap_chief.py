import os

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Первичное создание главного оператора без сброса существующего пароля.'

    @transaction.atomic
    def handle(self, *args, **options):
        username = settings.CHIEF_OPERATOR_USERNAME
        chief = User.objects.filter(username=username).first()
        if chief is None:
            password = os.environ.get('CHIEF_OPERATOR_PASSWORD', '')
            if not password:
                raise CommandError('Для первого запуска задайте CHIEF_OPERATOR_PASSWORD.')
            chief = User(username=username, first_name=settings.CHIEF_OPERATOR_NAME,
                is_active=True, is_staff=True, is_superuser=True)
            try:
                chief.full_clean(exclude=['password'])
                validate_password(password, chief)
            except ValidationError:
                raise CommandError('Проверьте CHIEF_OPERATOR_USERNAME и задайте стойкий пароль '
                                   'CHIEF_OPERATOR_PASSWORD длиной не менее 8 символов.') from None
            chief.set_password(password)
            chief.save()
            self.stdout.write('Главный оператор создан. Пароль не выводится в журнал.')
        else:
            chief.is_active = chief.is_staff = chief.is_superuser = True
            chief.first_name = settings.CHIEF_OPERATOR_NAME
            chief.save(update_fields=['is_active', 'is_staff', 'is_superuser', 'first_name'])
            self.stdout.write('Доступ главного оператора подтверждён. Пароль сохранён.')
