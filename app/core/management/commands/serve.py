import signal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.wsgi import get_wsgi_application
from waitress.server import create_server


def build_server():
    return create_server(
        get_wsgi_application(),
        host=settings.HOST,
        port=settings.PORT,
        threads=settings.WAITRESS_THREADS,
        clear_untrusted_proxy_headers=True,
    )


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
