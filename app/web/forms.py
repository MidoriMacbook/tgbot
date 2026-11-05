from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.validators import UnicodeUsernameValidator

from app.core.models import CategoryGroup, Ticket


class StaffAuthenticationForm(AuthenticationForm):
    error_messages = {
        'invalid_login': 'Введите правильные имя пользователя и пароль активного сотрудника.',
        'inactive': 'Учётная запись отключена. Обратитесь к администратору.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.pop('autofocus', None)
        self.fields['username'].widget.attrs.update({'spellcheck': 'false', 'placeholder': 'Ваш логин…'})
        self.fields['password'].widget.attrs['placeholder'] = 'Введите пароль…'

    def confirm_login_allowed(self, user):
        if not user.is_active or not user.is_staff:
            raise forms.ValidationError(self.error_messages['invalid_login'], code='invalid_login',
                                        params={'username': self.username_field.verbose_name})


class EmployeeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        name = obj.get_full_name() or obj.username
        return name if obj.is_active else f'{name} (отключён)'


class TicketFilterForm(forms.Form):
    status = forms.ChoiceField(label='Статус', required=False,
                               choices=[('', 'Все статусы'), *Ticket.Status.choices])
    group = forms.ModelChoiceField(label='Группа', queryset=CategoryGroup.objects.all(),
                                   required=False, empty_label='Все группы')
    assignee = EmployeeChoiceField(label='Исполнитель', queryset=User.objects.filter(is_staff=True),
                                   required=False, empty_label='Все сотрудники')
    date_from = forms.DateField(label='Дата с', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(label='Дата по', required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        values = super().clean()
        if values.get('date_from') and values.get('date_to') and values['date_from'] > values['date_to']:
            raise forms.ValidationError('Дата начала не может быть позже даты окончания.')
        return values


class TicketActionForm(forms.Form):
    action = forms.ChoiceField(choices=[(x, x) for x in ['take', 'assign', 'done', 'rejected']])
    version = forms.IntegerField(min_value=0)
    assignee_id = EmployeeChoiceField(queryset=User.objects.filter(is_staff=True, is_active=True), required=False)
    comment = forms.CharField(label='Результат', max_length=4000, required=False, strip=True)

    def clean(self):
        values = super().clean()
        if values.get('action') == 'assign' and not values.get('assignee_id'):
            self.add_error('assignee_id', 'Выберите активного сотрудника.')
        if values.get('action') in ('done', 'rejected') and not values.get('comment'):
            self.add_error('comment', 'Заполните поле «Результат».')
        return values


class CredentialGenerationForm(forms.Form):
    username = forms.CharField(label='Логин', max_length=150, required=False,
                               validators=[UnicodeUsernameValidator()],
                               help_text='Оставьте пустым для автоматической генерации.')
    role = forms.ChoiceField(label='Роль', choices=[('operator', 'Оператор'), ('admin', 'Администратор')])

    def clean_username(self):
        username = self.cleaned_data['username']
        if username and User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Этот логин уже занят.')
        return username
