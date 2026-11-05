from functools import wraps
import secrets
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Min, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.utils import timezone

from app.core import services
from app.core.models import History, Ticket
from app.web.context_processors import is_chief
from app.web.forms import CredentialGenerationForm, StaffAuthenticationForm, TicketActionForm, TicketFilterForm


class StaffLoginView(LoginView):
    template_name = 'web/login.html'
    authentication_form = StaffAuthenticationForm


def staff_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or not request.user.is_staff:
            return error_page(request, 'Доступ закрыт', 'Панель доступна только активным сотрудникам.', 403)
        return view(request, *args, **kwargs)
    return wrapped


def error_page(request, title, explanation, status):
    return render(request, 'web/error.html', {'title': title, 'explanation': explanation}, status=status)


def csrf_failure(request, reason=''):
    return error_page(request, 'Не удалось отправить форму',
        'Обновите страницу и повторите действие. Если сессия завершилась, войдите заново.', 403)


def page_not_found(request, exception):
    return error_page(request, 'Страница не найдена', 'Проверьте адрес или вернитесь к списку заявок.', 404)


def permission_denied(request, exception):
    return error_page(request, 'Доступ закрыт', 'У вашей учётной записи нет доступа к этому разделу.', 403)


@staff_required
def ticket_list(request):
    form = TicketFilterForm(request.GET)
    tickets = Ticket.objects.select_related('assignee')
    if form.is_valid():
        filters = form.cleaned_data
        for field, lookup in [('status', 'status'), ('group', 'item__group'), ('assignee', 'assignee'),
                              ('date_from', 'created_at__date__gte'), ('date_to', 'created_at__date__lte')]:
            if filters[field]:
                tickets = tickets.filter(**{lookup: filters[field]})
    else:
        tickets = tickets.none()
    page = Paginator(tickets, 25).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    return render(request, 'web/list.html', {'filter_form': form, 'page_obj': page,
        'query': query.urlencode(), 'has_filters': bool(query), 'total': page.paginator.count})


def detail_context(ticket, *, errors=None, submitted=None):
    return {'ticket': ticket, 'history': ticket.history.all(),
            'employees': User.objects.filter(is_staff=True, is_active=True).order_by('last_name', 'username'),
            'errors': errors, 'submitted': submitted or {}}


@staff_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related('assignee'), pk=pk)
    return render(request, 'web/detail.html', detail_context(ticket))


@staff_required
@require_POST
def ticket_action(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related('assignee'), pk=pk)
    form = TicketActionForm(request.POST)
    errors = []
    status = 400
    if form.is_valid():
        values = form.cleaned_data
        try:
            services.change_ticket(pk, request.user, values['action'],
                assignee_id=values['assignee_id'].pk if values['assignee_id'] else None,
                comment=values['comment'], version=values['version'])
        except services.RuleError as exc:
            errors.append(str(exc))
            ticket.refresh_from_db()
            if ticket.version != values['version']:
                status = 409
        else:
            messages.success(request, 'Изменения сохранены.')
            return redirect('ticket_detail', pk=pk)
    else:
        for field_errors in form.errors.values():
            errors.extend(field_errors)
    return render(request, 'web/detail.html', detail_context(ticket, errors=errors,
                  submitted=request.POST), status=status)


@staff_required
def statistics(request):
    if not request.user.is_superuser:
        return error_page(request, 'Доступ закрыт', 'Статистика доступна только администратору.', 403)
    counts = dict(Ticket.objects.values_list('status').annotate(total=Count('id')))
    statuses = [{'label': label, 'count': counts.get(value, 0), 'value': value}
                for value, label in Ticket.Status.choices]
    categories = Ticket.objects.values('category_label').annotate(total=Count('id')).order_by('-total', 'category_label')
    return render(request, 'web/statistics.html', {'statuses': statuses, 'categories': categories,
                                                'total': Ticket.objects.count()})


@staff_required
@never_cache
def statistics_api(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Статистика доступна только администратору.'}, status=403)
    try:
        days = int(request.GET.get('days', '30'))
    except ValueError:
        days = 0
    if days not in {7, 30, 90}:
        return JsonResponse({'error': 'Выберите период 7, 30 или 90 дней.'}, status=400)
    zone = ZoneInfo('Europe/Moscow')
    today = timezone.localtime(timezone.now(), zone).date()
    first = today - timedelta(days=days - 1)
    start = datetime.combine(first, time.min, tzinfo=zone)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=zone)
    tickets = Ticket.objects.filter(created_at__gte=start, created_at__lt=end)
    closures = History.objects.filter(created_at__gte=start, created_at__lt=end,
        status__in=[Ticket.Status.DONE, Ticket.Status.REJECTED],
        action__in=['Заявка выполнена', 'Заявка отклонена'])
    summary = {value: 0 for value, _ in Ticket.Status.choices}
    summary.update(dict(tickets.order_by().values_list('status').annotate(total=Count('id'))))
    summary.update(total=tickets.count(), closed=closures.count())
    created = {row['date']: row['total'] for row in tickets.order_by().annotate(
        date=TruncDate('created_at', tzinfo=zone)).values('date').annotate(total=Count('id'))}
    closed = {row['date']: row['total'] for row in closures.order_by().annotate(
        date=TruncDate('created_at', tzinfo=zone)).values('date').annotate(total=Count('id'))}
    trend = []
    for offset in range(days):
        date = first + timedelta(days=offset)
        trend.append({'date': date.isoformat(), 'created': created.get(date, 0), 'closed': closed.get(date, 0)})
    operators = []
    rows = closures.order_by().values('actor_id', 'actor__username', 'actor__first_name', 'actor__last_name').annotate(
        fallback_name=Min('actor_label'), completed=Count('id', filter=Q(status=Ticket.Status.DONE)),
        rejected=Count('id', filter=Q(status=Ticket.Status.REJECTED)), total=Count('id')).order_by('-total', 'actor_id')
    for row in rows:
        name = ' '.join(filter(None, [row['actor__first_name'], row['actor__last_name']])).strip()
        operators.append({'name': name or row['actor__username'] or row['fallback_name'],
                          'completed': row['completed'], 'rejected': row['rejected'], 'total': row['total']})
    categories = [{'name': row['category_label'], 'total': row['total']} for row in
        tickets.order_by().values('category_label').annotate(total=Count('id')).order_by('-total', 'category_label')]
    return JsonResponse({'summary': summary, 'trend': trend, 'operators': operators, 'categories': categories})


@staff_required
@never_cache
def team(request):
    if not is_chief(request.user):
        return error_page(request, 'Доступ закрыт', 'Доступами управляет только главный оператор.', 403)
    return render(request, 'web/team.html', {'generation_form': CredentialGenerationForm(),
        'employees': User.objects.filter(is_staff=True).order_by('-is_active', '-is_superuser', 'username')})


@staff_required
@require_POST
@never_cache
def generate_credentials(request):
    if not is_chief(request.user):
        return error_page(request, 'Доступ закрыт', 'Доступами управляет только главный оператор.', 403)
    form = CredentialGenerationForm(request.POST)
    credentials = None
    if form.is_valid():
        username = form.cleaned_data['username'] or f'operator_{secrets.token_hex(6)}'
        password = secrets.token_urlsafe(24)
        role = form.cleaned_data['role']
        try:
            with transaction.atomic():
                User.objects.create_user(username=username, password=password, is_staff=True,
                                         is_active=True, is_superuser=role == 'admin')
        except IntegrityError:
            form.add_error('username', 'Этот логин уже занят. Повторите генерацию.')
        else:
            credentials = {'username': username, 'password': password, 'role': role}
            form = CredentialGenerationForm()
    return render(request, 'web/team.html', {'generation_form': form, 'credentials': credentials,
        'employees': User.objects.filter(is_staff=True).order_by('-is_active', '-is_superuser', 'username')},
        status=200 if credentials else 400)
