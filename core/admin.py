from django.contrib import admin

from .models import Configuracao


@admin.register(Configuracao)
class ConfiguracaoAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'meta_votos', 'meta_doacoes')

    def has_add_permission(self, request):
        return not Configuracao.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
