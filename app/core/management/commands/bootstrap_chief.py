from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Создаёт главного оператора по почте из конфига. Пароль ему не задаётся.'

    @transaction.atomic
    def handle(self, *args, **options):
        email = settings.CHIEF_OPERATOR_EMAIL
        if not email:
            self.stdout.write('CHIEF_OPERATOR_EMAIL не задан. Вход главного оператора по почте недоступен.')
            return
        chief = User.objects.filter(email__iexact=email).first()
        if chief is None:
            chief = User.objects.filter(username='admin', is_superuser=True).first()
        if chief is None:
            chief = User(username='chief', first_name='Главный оператор')
            chief.set_unusable_password()
        chief.email = email
        chief.is_active = chief.is_staff = chief.is_superuser = True
        chief.save()
        self.stdout.write('Главный оператор привязан к почте из конфига. Пароль не используется.')
