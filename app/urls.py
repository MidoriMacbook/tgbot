from django.contrib.auth.views import LogoutView
from django.urls import path

from app.web import views

urlpatterns = [
    path('', views.ticket_list, name='ticket_list'),
    path('login/', views.StaffLoginView.as_view(), name='login'),
    path('login/operator/', views.operator_login, name='operator_login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('tickets/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/<int:pk>/action/', views.ticket_action, name='ticket_action'),
    path('statistics/', views.statistics, name='statistics'),
    path('api/statistics/', views.statistics_api, name='statistics_api'),
    path('team/', views.team, name='team'),
    path('workload/', views.workload, name='workload'),
    path('team/generate/', views.generate_credentials, name='team_generate'),
    path('profile/', views.profile, name='profile'),
    path('administrators/', views.administrators, name='administrators'),
    path('administrators/<int:pk>/delete/', views.delete_administrator, name='administrator_delete'),
]

handler403 = views.permission_denied
handler404 = views.page_not_found
