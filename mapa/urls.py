from django.urls import path
from . import views

app_name = 'mapa'

urlpatterns = [
    # Páginas
    path('', views.mapa_home, name='index'),
    path('regiao/<slug:slug>/', views.mapa_regiao, name='regiao'),
    path('cidade/<slug:slug>/', views.mapa_cidade, name='cidade'),

    # API: Mapas base
    path('api/state/', views.StateMapAPI.as_view(), name='api_state'),
    path('api/state-cities/', views.StateCitiesMapAPI.as_view(), name='api_state_cities'),
    path('api/region/<slug:slug>/', views.RegionMapAPI.as_view(), name='api_region'),
    path('api/city/<slug:slug>/', views.CityMapAPI.as_view(), name='api_city'),
    path('api/heatmap/<str:metric>/', views.HeatmapAPI.as_view(), name='api_heatmap'),

    # API: Dashboard
    path('api/overview/', views.DashboardOverviewAPI.as_view(), name='api_overview'),
    path('api/dashboard/region/<slug:slug>/', views.RegionDashboardAPI.as_view(), name='api_dashboard_region'),
    path('api/dashboard/city/<slug:slug>/', views.CityDashboardAPI.as_view(), name='api_dashboard_city'),

    # API: Análises
    path('api/strategic/', views.StrategicAnalysisAPI.as_view(), name='api_strategic'),
    path('api/pl-network/', views.PLNetworkAPI.as_view(), name='api_pl_network'),
    path('api/doacoes/', views.DoacoesMapAPI.as_view(), name='api_doacoes'),
    path('api/demandas/', views.DemandasMapAPI.as_view(), name='api_demandas'),
    path('api/roteiros/', views.RoteirosMapAPI.as_view(), name='api_roteiros'),
    path('api/zone-ranking/', views.ZoneRankingAPI.as_view(), name='api_zone_ranking'),
    path('api/vote-transfer/', views.VoteTransferAPI.as_view(), name='api_vote_transfer'),
    path('api/elections-2022/', views.Elections2022API.as_view(), name='api_elections_2022'),
    path('api/neighbor-deputies/', views.NeighborDeputiesAPI.as_view(), name='api_neighbor_deputies'),
    path('api/competicao/', views.CompeticaoMapAPI.as_view(), name='api_competicao'),
    path('api/perfil-ideologico/', views.PerfilIdeologicoAPI.as_view(), name='api_perfil_ideologico'),
    path('api/urgencia-visita/', views.VisitUrgencyAPI.as_view(), name='api_urgencia_visita'),
    path('api/cidade-acao/<slug:slug>/', views.CityActionAPI.as_view(), name='api_cidade_acao'),
    path('api/vitoria/', views.VictoryMapAPI.as_view(), name='api_vitoria'),
    path('api/calor-camadas/', views.HeatLayersAPI.as_view(), name='api_calor_camadas'),
]
