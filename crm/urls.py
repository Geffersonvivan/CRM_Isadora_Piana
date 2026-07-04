from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from dashboard.views import home_view
from core.views import ajuda


urlpatterns = [
    path('admin/', admin.site.urls),
    path('ajuda/', ajuda, name='ajuda'),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('usuarios/', include('usuarios.urls')),
    path('liderancas/', include('liderancas.urls')),
    path('agenda/', include('agenda.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('tarefas/', include('tarefas.urls')),
    path('notificacoes/', include('notificacoes.urls')),
    path('mapa/', include('mapa.urls')),
    path('oportunidades/', include('oportunidades.urls')),
    path('app/', include('pwa.urls')),
    path('', login_required(home_view), name='home'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
