from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from app.core import services
from app.core.models import Ticket
from app.web.forms import StaffAuthenticationForm, TicketActionForm, TicketFilterForm


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
