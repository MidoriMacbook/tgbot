from functools import wraps
import hashlib
import re
import secrets
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, update_session_auth_hash
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
from django.conf import settings
from django.utils import timezone

from app.core import services
from app.core.mail import MailError, mail_ready, send_login_code
from app.core.models import EmailCode, History, Ticket
from app.web.context_processors import is_chief
from app.core.vault import remember_password, reveal_password
from app.web.forms import (CredentialGenerationForm, ProfilePasswordForm, StaffAuthenticationForm,
    TicketActionForm, TicketFilterForm)


def operator_account(email):
    existing = User.objects.filter(email__iexact=email).order_by('-is_superuser').first()
    if existing:
        if existing.is_superuser or not existing.is_staff:
            return None
        return existing
    base = re.sub(r'[^a-z0-9_]+', '', email.split('@', 1)[0].lower())[:20] or 'operator'
    username, number = base, 1
    while User.objects.filter(username=username).exists():
        number += 1
        username = f'{base}{number}'[:150]
    user = User.objects.create(username=username, email=email, is_staff=True, is_active=True)
    user.set_unusable_password()
    user.save(update_fields=['password'])
    return user


@never_cache
def operator_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('ticket_list')
    stage = request.session.get('operator_stage', 'email')
    email = request.session.get('operator_email', '')
    error = ''
    if request.method == 'POST' and request.POST.get('action') == 'restart':
        for key in ('operator_stage', 'operator_email', 'operator_code'):
            request.session.pop(key, None)
        return redirect('operator_login')
    if request.method == 'POST' and stage != 'code':
        email = (request.POST.get('email') or '').strip().lower()
        if not mail_ready():
            error = 'Отправка кодов ещё не подключена.'
        elif '@' not in email or len(email) > 254 or ' ' in email:
            error = 'Укажите почту.'
        elif EmailCode.objects.filter(email=email, created_at__gte=timezone.now() - timedelta(seconds=60)).exists():
            error = 'Код уже отправлен. Подождите минуту.'
        else:
            code = f'{secrets.randbelow(1000000):06d}'
            digest = hashlib.sha256(f'{settings.SECRET_KEY}:{email}:{code}'.encode()).hexdigest()
            row = EmailCode.objects.create(email=email, digest=digest,
                expires_at=timezone.now() + timedelta(minutes=10))
            try:
                send_login_code(email, code)
            except MailError as exc:
                row.delete()
                error = str(exc)
            else:
                request.session['operator_stage'] = 'code'
                request.session['operator_email'] = email
                request.session['operator_code'] = row.pk
                return redirect('operator_login')
    elif request.method == 'POST':
        entered = (request.POST.get('code') or '').strip()
        row = EmailCode.objects.filter(pk=request.session.get('operator_code'), email=email).first()
        if not row or row.expires_at < timezone.now() or row.attempts >= 5:
            error = 'Код устарел. Запросите новый.'
            request.session['operator_stage'] = 'email'
            stage = 'email'
        else:
            digest = hashlib.sha256(f'{settings.SECRET_KEY}:{email}:{entered}'.encode()).hexdigest()
            if digest != row.digest:
                row.attempts += 1
                row.save(update_fields=['attempts'])
                error = 'Неверный код.'
            else:
                user = operator_account(email)
                if user is None:
                    error = 'Этот адрес принадлежит администратору. Войдите логином и паролем.'
                elif not user.is_active:
                    error = 'Учётная запись отключена.'
                else:
                    row.delete()
                    for key in ('operator_stage', 'operator_email', 'operator_code'):
                        request.session.pop(key, None)
                    login(request, user)
                    return redirect(request.POST.get('next') or 'ticket_list')
    return render(request, 'web/operator_login.html', {
        'stage': request.session.get('operator_stage', 'email'), 'email': email, 'error': error,
        'mail_ready': mail_ready(), 'next': request.GET.get('next', ''),
    })


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
            'employees': services.assignable_staff(),
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


def person_name(user):
    return user.get_full_name() or user.username


@staff_required
def workload(request):
    if not is_chief(request.user):
        return error_page(request, 'Доступ закрыт', 'Нагрузку сотрудников видит только главный оператор.', 403)
    work = list(Ticket.objects.filter(status=Ticket.Status.WORK).select_related('assignee').order_by('-updated_at'))
    by_assignee = {}
    for ticket in work:
        by_assignee.setdefault(ticket.assignee_id, []).append(ticket)
    people = list(User.objects.filter(is_staff=True).exclude(
        username=settings.CHIEF_OPERATOR_USERNAME).order_by('-is_active', 'last_name', 'username'))
    seen = {person.pk for person in people}
    rows = []
    for person in people:
        rows.append({'name': person_name(person), 'active': person.is_active,
            'role': 'Администратор' if person.is_superuser else 'Оператор',
            'tickets': by_assignee.get(person.pk, [])})
    for assignee_id, tickets in by_assignee.items():
        if assignee_id in seen or not tickets or tickets[0].assignee_id is None:
            continue
        assignee = tickets[0].assignee
        rows.append({'name': person_name(assignee) if assignee else 'Не назначен',
            'active': bool(assignee and assignee.is_active),
            'role': 'Главный оператор' if assignee and assignee.username == settings.CHIEF_OPERATOR_USERNAME else 'Сотрудник',
            'tickets': tickets})
    fresh = Ticket.objects.filter(status=Ticket.Status.NEW).count()
    return render(request, 'web/workload.html', {'rows': rows, 'fresh': fresh, 'in_work': len(work)})


@staff_required
@never_cache
def profile(request):
    if not request.user.is_superuser:
        return render(request, 'web/profile.html', {'form': None})
    form = ProfilePasswordForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, 'Пароль изменён.')
        return redirect('profile')
    status = 400 if request.method == 'POST' else 200
    return render(request, 'web/profile.html', {'form': form}, status=status)


@staff_required
@never_cache
def administrators(request):
    if not is_chief(request.user):
        return error_page(request, 'Доступ закрыт', 'Список администраторов видит только главный оператор.', 403)
    people = User.objects.filter(is_superuser=True).exclude(
        username=settings.CHIEF_OPERATOR_USERNAME).order_by('-is_active', 'username')
    rows = [{'user': person, 'password': reveal_password(person)} for person in people]
    response = render(request, 'web/administrators.html', {'rows': rows})
    response['Cache-Control'] = 'no-store'
    return response


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
                user = User.objects.create_user(username=username, password=password, is_staff=True,
                                         is_active=True, is_superuser=role == 'admin')
                remember_password(user, password)
        except IntegrityError:
            form.add_error('username', 'Этот логин уже занят. Повторите генерацию.')
        else:
            credentials = {'username': username, 'password': password, 'role': role}
            form = CredentialGenerationForm()
    return render(request, 'web/team.html', {'generation_form': form, 'credentials': credentials,
        'employees': User.objects.filter(is_staff=True).order_by('-is_active', '-is_superuser', 'username')},
        status=200 if credentials else 400)
