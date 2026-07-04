from django.urls import path
from . import views

app_name = 'notificacoes'

urlpatterns = [
    path('api/count/', views.api_count, name='api_count'),
    path('api/list/', views.api_list, name='api_list'),
    path('api/mark-read/', views.api_mark_read, name='api_mark_read'),
    path('api/dismiss/', views.api_dismiss, name='api_dismiss'),
    path('api/clear-read/', views.api_clear_read, name='api_clear_read'),
]
