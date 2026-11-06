from django.conf import settings
from django.urls import reverse


def user_is_chief_account(user):
    email = (getattr(user, 'email', '') or '').strip().lower()
    return bool(user is not None and settings.CHIEF_OPERATOR_EMAIL and email == settings.CHIEF_OPERATOR_EMAIL)


def is_chief(user):
    return bool(getattr(user, 'is_authenticated', False) and user.is_active and user.is_staff
                and user.is_superuser and user_is_chief_account(user))


def admin_back(request):
    match = getattr(request, 'resolver_match', None)
    if match is None or match.namespace != 'admin' or match.url_name in {'logout'}:
        return {}
    index = reverse('admin:index')
    if match.url_name == 'index':
        return {'admin_back_url': reverse('ticket_list'), 'admin_back_label': 'К заявкам'}
    if match.url_name == 'login':
        return {'admin_back_url': reverse('ticket_list'), 'admin_back_label': 'К заявкам'}
    parts = [part for part in request.path.split('/') if part]
    if len(parts) <= 2:
        url = index
    else:
        url = f"/{'/'.join(parts[:3])}/"
        if request.path.rstrip('/') + '/' == url:
            url = index
    return {'admin_back_url': url, 'admin_back_label': 'К управлению' if url == index else 'Назад'}


def application(request):
    return {'is_chief_operator': is_chief(request.user), 'app_brand': settings.APP_BRAND,
            'public_url': settings.PUBLIC_URL, **admin_back(request)}


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
