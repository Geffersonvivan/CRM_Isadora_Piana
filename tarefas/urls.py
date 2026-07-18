from django.urls import path
from . import views

app_name = 'tarefas'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('nova/', views.tarefa_create, name='tarefa_create'),
    path('<int:pk>/', views.tarefa_detail, name='tarefa_detail'),
    path('<int:pk>/editar/', views.tarefa_edit, name='tarefa_edit'),
    path('<int:pk>/excluir/', views.tarefa_delete, name='tarefa_delete'),
    path('excluidas/', views.excluidas, name='excluidas'),
    path('concluidas/', views.concluidas, name='concluidas'),
    # APIs
    path('api/mover/', views.api_mover, name='api_mover'),
    path('api/<int:pk>/comentar/', views.api_comentar, name='api_comentar'),
    path('api/comentario/<int:pk>/editar/', views.api_comentario_editar, name='api_comentario_editar'),
    path('api/comentario/<int:pk>/excluir/', views.api_comentario_excluir, name='api_comentario_excluir'),
    path('api/<int:pk>/detail/', views.api_tarefa_detail, name='api_tarefa_detail'),
    path('api/<int:pk>/save/', views.api_tarefa_save, name='api_tarefa_save'),
    path('api/<int:pk>/patch/', views.api_tarefa_patch, name='api_tarefa_patch'),
    path('api/<int:pk>/patch-cabos/', views.api_tarefa_patch_cabos, name='api_tarefa_patch_cabos'),
    path('api/<int:pk>/patch-participantes/', views.api_tarefa_patch_participantes, name='api_tarefa_patch_participantes'),
    path('api/<int:pk>/clear-cabos/', views.api_tarefa_clear_cabos, name='api_tarefa_clear_cabos'),
    path('api/cidades/<int:regiao_id>/', views.api_cidades, name='api_cidades'),
    path('api/cabos/<int:cidade_id>/', views.api_cabos_por_cidade, name='api_cabos_por_cidade'),
    path('api/criar-inline/', views.api_tarefa_create_inline, name='api_tarefa_create_inline'),
    path('api/excluir/', views.api_tarefa_excluir, name='api_tarefa_excluir'),
    path('api/duplicar/', views.api_tarefa_duplicar, name='api_tarefa_duplicar'),
    path('api/mover-fase/', views.api_tarefa_mover_fase, name='api_tarefa_mover_fase'),
    path('api/restaurar/', views.api_tarefa_restaurar, name='api_tarefa_restaurar'),
    path('api/excluir-permanente/', views.api_tarefa_excluir_permanente, name='api_tarefa_excluir_permanente'),
    path('api/<int:pk>/agendar/', views.api_tarefa_agendar, name='api_tarefa_agendar'),
    path('api/<int:pk>/desagendar/', views.api_tarefa_desagendar, name='api_tarefa_desagendar'),
    # Checklist da tarefa
    path('api/<int:pk>/checklist/', views.api_checklist_listar, name='api_checklist_listar'),
    path('api/<int:pk>/checklist/criar/', views.api_checklist_criar, name='api_checklist_criar'),
    path('api/<int:pk>/checklist/reordenar/', views.api_checklist_reordenar, name='api_checklist_reordenar'),
    path('api/checklist-item/<int:item_id>/toggle/', views.api_checklist_toggle, name='api_checklist_toggle'),
    path('api/checklist-item/<int:item_id>/editar/', views.api_checklist_editar, name='api_checklist_editar'),
    path('api/checklist-item/<int:item_id>/excluir/', views.api_checklist_excluir, name='api_checklist_excluir'),
    path('api/checklist-item/<int:item_id>/virar-tarefa/', views.api_checklist_virar_tarefa, name='api_checklist_virar_tarefa'),
]
