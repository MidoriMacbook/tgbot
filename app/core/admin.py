from django import forms
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from app.core.models import CategoryGroup, CategoryItem


class AdministratorAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser:
            raise forms.ValidationError('Вход в этот раздел доступен только администратору.', code='invalid_login')


class AdministrationSite(admin.AdminSite):
    site_header = 'Управление службой заявок'
    site_title = 'Управление'
    index_title = 'Справочники и сотрудники'
    site_url = '/'
    login_form = AdministratorAuthenticationForm

    def has_permission(self, request):
        return request.user.is_active and request.user.is_staff and request.user.is_superuser


site = AdministrationSite(name='admin')


class DisableInsteadOfDelete:
    actions = ['deactivate']
    active_field = 'active'

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='Отключить выбранные записи')
    def deactivate(self, request, queryset):
        count = queryset.update(**{self.active_field: False})
        self.message_user(request, f'Отключено записей: {count}. История заявок сохранена.')


@admin.register(CategoryGroup, site=site)
class CategoryGroupAdmin(DisableInsteadOfDelete, admin.ModelAdmin):
    list_display = ['name', 'active']
    list_filter = ['active']
    search_fields = ['name']


@admin.register(CategoryItem, site=site)
class CategoryItemAdmin(DisableInsteadOfDelete, admin.ModelAdmin):
    list_display = ['name', 'group', 'active']
    list_filter = ['group', 'active']
    search_fields = ['name']


@admin.register(User, site=site)
class EmployeeAdmin(DisableInsteadOfDelete, UserAdmin):
    active_field = 'is_active'
    list_display = ['username', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active']
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Сотрудник', {'fields': ('first_name', 'last_name', 'email')}),
        ('Роль и доступ', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('Даты', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('username', 'first_name', 'last_name',
            'usable_password', 'password1', 'password2', 'is_active', 'is_staff', 'is_superuser')}),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        role_fields = {
            'is_staff': ('Сотрудник (оператор)', 'Доступ к ленте и обработке всех заявок.'),
            'is_superuser': ('Администратор', 'Управление сотрудниками, справочниками и просмотр статистики.'),
        }
        if db_field.name in role_fields:
            kwargs['label'], kwargs['help_text'] = role_fields[db_field.name]
        if db_field.name == 'is_staff':
            kwargs['initial'] = True
        return super().formfield_for_dbfield(db_field, request, **kwargs)
