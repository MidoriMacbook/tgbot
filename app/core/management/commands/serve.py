import ipaddress
import os
import signal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.wsgi import get_wsgi_application
from waitress import serve

from app.config import env_number


class Command(BaseCommand):
    help = 'Промышленный HTTP-сервер Waitress со статикой WhiteNoise.'

    def handle(self, *args, **options):
        proxy = os.environ.get('WAITRESS_TRUSTED_PROXY', '').strip()
        if proxy:
            try:
                ipaddress.ip_address(proxy)
            except ValueError:
                raise CommandError('WAITRESS_TRUSTED_PROXY: укажите конкретный IP доверенного прокси.') from None
        arguments = {
            'host': settings.HOST, 'port': settings.PORT,
            'threads': env_number('WAITRESS_THREADS', 4, 1, 64, integer=True),
            'clear_untrusted_proxy_headers': True,
        }
        if proxy:
            arguments.update(trusted_proxy=proxy, trusted_proxy_count=1,
                             trusted_proxy_headers={'x-forwarded-proto'})

        def stop(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        self.stdout.write(f'Веб-панель слушает {settings.HOST}:{settings.PORT}.')
        try:
            serve(get_wsgi_application(), **arguments)
        except KeyboardInterrupt:
            self.stdout.write('Веб-панель остановлена.')
