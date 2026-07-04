from django.urls import path
from . import views

app_name = 'pwa'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.pwa_login, name='login'),
    path('logout/', views.pwa_logout, name='logout'),
    path('apoiador/novo/', views.cadastro_apoiador, name='cadastro_apoiador'),
    path('replicador/novo/', views.cadastro_replicador, name='cadastro_replicador'),
    path('mobilizacao/novo/', views.cadastro_voluntario, name='cadastro_voluntario'),
    path('api/cidades/<int:regiao_id>/', views.api_cidades, name='api_cidades'),
    path('api/sync/', views.api_sync, name='api_sync'),
    path('api/sync-voluntario/', views.api_sync_voluntario, name='api_sync_voluntario'),
    path('api/transcrever/', views.api_transcrever, name='api_transcrever'),
    path('manifest.json', views.manifest_json, name='manifest'),
    path('sw.js', views.service_worker, name='sw'),
]
