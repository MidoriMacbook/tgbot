import ipaddress
import os
import signal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.wsgi import get_wsgi_application
from waitress.server import create_server

from app.config import env_number


def build_server():
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
    return create_server(get_wsgi_application(), **arguments)


class Command(BaseCommand):
    help = 'Промышленный HTTP-сервер Waitress со статикой WhiteNoise.'

    def handle(self, *args, **options):
        def stop(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        server = build_server()
        self.stdout.write(f'Веб-панель слушает {settings.HOST}:{settings.PORT}.')
        try:
            server.run()
        except KeyboardInterrupt:
            server.close()
            self.stdout.write('Веб-панель остановлена.')
