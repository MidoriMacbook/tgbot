from django.conf import settings


def is_chief(user):
    return bool(user.is_authenticated and user.is_active and user.is_staff
                and user.is_superuser and user.username == settings.CHIEF_OPERATOR_USERNAME)


def application(request):
    return {'is_chief_operator': is_chief(request.user), 'app_brand': settings.APP_BRAND,
            'public_url': settings.PUBLIC_URL}


class FramePolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.TELEGRAM_ALLOW_EMBED:
            response.headers.pop('X-Frame-Options', None)
            response['Content-Security-Policy'] = (
                "frame-ancestors 'self' https://web.telegram.org https://telegram.org https://*.telegram.org")
        else:
            response['Content-Security-Policy'] = "frame-ancestors 'none'"
        return response
