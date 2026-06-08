from django.contrib import admin
from .models import Eleicao, ResultadoCandidato, IndicadorMunicipal


@admin.register(Eleicao)
class EleicaoAdmin(admin.ModelAdmin):
    list_display = ('ano', 'tipo', 'turno')
    list_filter = ('ano', 'tipo')


@admin.register(ResultadoCandidato)
class ResultadoCandidatoAdmin(admin.ModelAdmin):
    list_display = ('candidato_nome', 'partido', 'cidade', 'votos', 'eleicao')
    list_filter = ('eleicao__ano', 'eleicao__tipo', 'is_sorgatto')
    search_fields = ('candidato_nome', 'partido', 'cidade__nome')


@admin.register(IndicadorMunicipal)
class IndicadorMunicipalAdmin(admin.ModelAdmin):
    list_display = ('cidade', 'ano_referencia', 'pib', 'renda_per_capita', 'familias_bolsa_familia', 'meis_ativos')
    list_filter = ('ano_referencia',)
    search_fields = ('cidade__nome',)
    raw_id_fields = ('cidade',)
