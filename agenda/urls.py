from django.urls import path
from . import views

app_name = 'agenda'

urlpatterns = [
    # Compromissos
    path('compromissos/', views.compromisso_list, name='compromisso_list'),
    path('compromissos/novo/', views.compromisso_create, name='compromisso_create'),
    path('compromissos/imprimir/', views.compromisso_print, name='compromisso_print'),
    path('compromissos/<int:pk>/editar/', views.compromisso_edit, name='compromisso_edit'),
    path('compromissos/<int:pk>/excluir/', views.compromisso_delete, name='compromisso_delete'),

    # Roteiros
    path('roteiros/', views.roteiro_list, name='roteiro_list'),
    path('roteiros/novo/', views.roteiro_create, name='roteiro_create'),
    path('roteiros/<int:pk>/', views.roteiro_detail, name='roteiro_detail'),
    path('roteiros/<int:pk>/editar/', views.roteiro_edit, name='roteiro_edit'),
    path('roteiros/<int:pk>/excluir/', views.roteiro_delete, name='roteiro_delete'),
    path('roteiros/<int:pk>/imprimir/', views.roteiro_print, name='roteiro_print'),
    path('roteiros/<int:pk>/otimizar/', views.roteiro_otimizar, name='roteiro_otimizar'),

    # Eventos
    path('eventos/', views.evento_list, name='evento_list'),
    path('eventos/novo/', views.evento_create, name='evento_create'),
    path('eventos/<int:pk>/editar/', views.evento_edit, name='evento_edit'),
    path('eventos/<int:pk>/excluir/', views.evento_delete, name='evento_delete'),

    # API
    path('api/eventos-calendario/', views.api_eventos_calendario, name='api_eventos_calendario'),
    path('api/eventos/<int:pk>/', views.api_evento_detalhe, name='api_evento_detalhe'),
    path('api/roteiro-dia/', views.api_roteiro_dia, name='api_roteiro_dia'),
    path('api/roteiro-salvar/', views.api_salvar_roteiro, name='api_salvar_roteiro'),
    path('api/compromissos/', views.api_compromissos_json, name='api_compromissos_json'),
    path('api/coordenadores/<int:regiao_id>/', views.api_coordenadores_regiao, name='api_coordenadores_regiao'),
    path('api/cabos/<int:cidade_id>/', views.api_cabos_cidade, name='api_cabos_cidade'),
    path('api/apoiadores/<int:cidade_id>/', views.api_apoiadores_cidade, name='api_apoiadores_cidade'),
    path('api/compromissos-por-data/', views.api_compromissos_por_data, name='api_compromissos_por_data'),
    path('api/tarefas-calendario/', views.api_tarefas_calendario, name='api_tarefas_calendario'),
    path('api/tarefas-por-dia/', views.api_tarefas_por_dia, name='api_tarefas_por_dia'),
    path('api/compromissos/<int:pk>/tarefas/', views.api_tarefas_compromisso, name='api_tarefas_compromisso'),
    path('api/compromissos/<int:pk>/tarefas/criar/', views.api_criar_tarefa_compromisso, name='api_criar_tarefa_compromisso'),
    path('api/tarefas/<int:tarefa_id>/toggle/', views.api_toggle_tarefa_compromisso, name='api_toggle_tarefa_compromisso'),
    path('api/compromissos/<int:pk>/followup/', views.api_followup_compromisso, name='api_followup_compromisso'),
]
