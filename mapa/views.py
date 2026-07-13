import math
from collections import defaultdict

from django.conf import settings

from django.db import connection
from django.db.models import Count, Sum, Q, F, Avg
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.views import APIView
from rest_framework.response import Response

from liderancas.models import (
    Regiao, Cidade, Lideranca, Bairro, q_apoiadores_aprovados,
)
from tarefas.models import Tarefa
from agenda.models import Compromisso, Roteiro, RoteiroPonto, Evento
from usuarios.models import Usuario
from usuarios.views import secao_required
from mapa.models import Eleicao, ResultadoCandidato, ResultadoZona, IndicadorMunicipal

ALLIED_PARTIES = {'PL', 'PP', 'REPUBLICANOS', 'UNIÃO', 'UNIÃO BRASIL'}
ADVERSARY_PARTIES = {'PT', 'PSOL', 'PCdoB', 'REDE', 'PV', 'SOLIDARIEDADE'}


def _politicos_por_cidade():
    """Ativos políticos aliados por cidade, AO VIVO do Apoiador.cargo."""
    from collections import defaultdict
    pol = defaultdict(lambda: {'prefeito': 0, 'vice': 0, 'vereador': 0,
                               'presidente': 0, 'votos_maquina': 0, 'meta_transferir': 0})
    cargo_map = {'prefeito': 'prefeito', 'vice_prefeito': 'vice',
                 'vereador': 'vereador', 'presidente_diretorio': 'presidente'}
    for ap in Lideranca.objects.apoiadores_aprovados().filter(tipo='politico').values(
        'cidade_id', 'cargo', 'votos_referencia', 'meta_votos_transferir',
    ):
        d = pol[ap['cidade_id']]
        k = cargo_map.get(ap['cargo'])
        if k:
            d[k] += 1
        d['votos_maquina'] += ap['votos_referencia'] or 0
        d['meta_transferir'] += ap['meta_votos_transferir'] or 0
    return pol


def _forca_politica(d):
    """Placar de força política da cidade: prefeito pesa mais, vereador por
    cabeça, diretório = estrutura partidária."""
    return d['prefeito'] * 50 + d['vice'] * 25 + d['vereador'] * 15 + d['presidente'] * 20


# ─── PÁGINAS ───────────────────────────────────────────────────────

@secao_required('mapa')
def mapa_home(request):
    mapa_param = request.GET.get('mapa', 'eleicoes_2022')
    return render(request, 'mapa/index.html', {'mapa_param': mapa_param})


@secao_required('mapa')
def mapa_regiao(request, slug):
    return render(request, 'mapa/regiao.html', {'region_slug': slug})


@secao_required('mapa')
def mapa_cidade(request, slug):
    return render(request, 'mapa/cidade.html', {'city_slug': slug})


# ─── API: MAPAS BASE ──────────────────────────────────────────────

# Nível de regionalização → (FK da Cidade, related_name das cidades). O seletor do
# mapa escolhe o nível; cada um agrega pela sua relação (não misturar os 3, senão o
# mapa desenha 47 regiões sobrepostas).
NIVEL_REL = {
    'associacao': ('regiao', 'cidades'),
    'micro': ('microrregiao', 'cidades_micro'),
    'meso': ('mesorregiao', 'cidades_meso'),
}


def _nivel_param(request):
    n = request.GET.get('nivel', 'associacao')
    return n if n in NIVEL_REL else 'associacao'


class StateMapAPI(APIView):
    """GeoJSON do estado com as regiões do nível pedido (assoc/micro/meso)."""
    def get(self, request):
        nivel = _nivel_param(request)
        cidade_fk, cidades_rel = NIVEL_REL[nivel]
        # Apoiadores por região numa ÚNICA agregação (dict) — não pode ir junto dos
        # Sum no annotate, senão o JOIN de liderancas multiplica os Sum
        # (eleitores/votos). Antes era Subquery correlacionada (uma por região).
        ap_por_regiao = dict(
            Lideranca.objects.apoiadores_aprovados()
            .values(f'cidade__{cidade_fk}')
            .annotate(c=Count('id'))
            .values_list(f'cidade__{cidade_fk}', 'c')
        )
        regions = Regiao.objects.filter(nivel=nivel).annotate(
            total_votos_2022=Sum(f'{cidades_rel}__votos_referencia_2022'),
            total_eleitores=Sum(f'{cidades_rel}__eleitores'),
            # População/meta somadas dos municípios: no meso/micro o campo da própria
            # região é 0 (não semeado); a soma é a informação que faz sentido.
            total_populacao=Sum(f'{cidades_rel}__populacao'),
            total_meta_votos=Sum(f'{cidades_rel}__meta_votos'),
        )
        features = []
        for r in regions:
            if r.geojson:
                # Associações têm o campo próprio preenchido (histórico); meso/micro
                # usam a soma. Preferir a soma quando existir (> 0).
                populacao = r.total_populacao or r.populacao or 0
                meta = r.total_meta_votos or r.meta_votos or 0
                features.append({
                    'type': 'Feature',
                    'properties': {
                        'name': r.sigla,
                        'full_name': r.nome_completo or r.nome,
                        'slug': r.slug,
                        'population': populacao,
                        'color': r.cor,
                        'meta_votes': meta,
                        'total_apoiadores': ap_por_regiao.get(r.pk, 0),
                        'total_votes_2022': r.total_votos_2022 or 0,
                        'registered_voters': r.total_eleitores or 0,
                    },
                    'geometry': r.geojson,
                })
        return Response({'type': 'FeatureCollection', 'features': features})


class RegionMapAPI(APIView):
    """GeoJSON de uma região com suas cidades."""
    def get(self, request, slug):
        region = Regiao.objects.get(slug=slug)
        # As cidades da região vêm da relação do NÍVEL dela (assoc/micro/meso).
        _fk, cidades_rel = NIVEL_REL.get(region.nivel, NIVEL_REL['associacao'])
        cities = getattr(region, cidades_rel).annotate(
            total_apoiadores=Count(
                'liderancas', filter=q_apoiadores_aprovados('liderancas'),
            ),
        )
        features = []
        for city in cities:
            if city.geojson:
                features.append({
                    'type': 'Feature',
                    'properties': {
                        'name': city.nome,
                        'slug': city.slug,
                        'population': city.populacao,
                        'votes_2022': city.votos_referencia_2022,
                        'registered_voters': city.eleitores,
                        'meta_votes': city.meta_votos,
                        'total_apoiadores': city.total_apoiadores,
                        'mayor': city.prefeito_nome,
                    },
                    'geometry': city.geojson,
                })
        # População agregada dos municípios (meso/micro têm o campo próprio zerado).
        pop = getattr(region, cidades_rel).aggregate(s=Sum('populacao'))['s']
        return Response({
            'type': 'FeatureCollection',
            'features': features,
            'region': {
                'name': region.sigla,
                'full_name': region.nome_completo or region.nome,
                'population': pop or region.populacao or 0,
            },
        })


class CityMapAPI(APIView):
    """GeoJSON de uma cidade com seus bairros."""
    def get(self, request, slug):
        city = Cidade.objects.get(slug=slug)
        bairros = city.bairros.all()
        features = []
        for b in bairros:
            if b.geojson:
                features.append({
                    'type': 'Feature',
                    'properties': {
                        'name': b.nome,
                        'slug': b.slug,
                        'population': b.populacao,
                        'meta_votes': b.meta_votos,
                    },
                    'geometry': b.geojson,
                })
        return Response({
            'type': 'FeatureCollection',
            'features': features,
            'city': {
                'name': city.nome,
                'population': city.populacao,
                'geojson': city.geojson,
            },
        })


class StateCitiesMapAPI(APIView):
    """GeoJSON de todas as 295 cidades."""
    def get(self, request):
        cities = (
            Cidade.objects
            .select_related('regiao')
            .annotate(
                total_apoiadores=Count(
                    'liderancas', filter=q_apoiadores_aprovados('liderancas'),
                ),
            )
            .exclude(geojson__isnull=True)
        )
        features = []
        for city in cities:
            features.append({
                'type': 'Feature',
                'properties': {
                    'name': city.nome,
                    'slug': city.slug,
                    'region_name': city.regiao.sigla,
                    'region_slug': city.regiao.slug,
                    'population': city.populacao,
                    'votes_2022': city.votos_referencia_2022,
                    'registered_voters': city.eleitores,
                    'meta_votes': city.meta_votos,
                    'total_apoiadores': city.total_apoiadores,
                },
                'geometry': city.geojson,
            })
        return Response({'type': 'FeatureCollection', 'features': features})


class HeatmapAPI(APIView):
    """Dados para choropleth baseado em métrica. ?level=city para granularidade por cidade."""
    @method_decorator(cache_page(60 * 15))
    def get(self, request, metric):
        level = request.GET.get('level', 'region')

        if level == 'city':
            return self._city_level(metric)

        # Apoiadores e demandas vencidas por região em dicts (agregação isolada):
        # dois Count sobre relações distintas + Sum no mesmo annotate inflariam
        # tudo (join cartesiano). Antes eram Subqueries correlacionadas por região.
        hoje_hm = timezone.now().date()
        # Nível (assoc/micro/meso): agrega pela relação certa — senão meso/micro dão 0.
        nivel = _nivel_param(request)
        cidade_fk, cidades_rel = NIVEL_REL[nivel]
        ap_por_regiao = dict(
            Lideranca.objects.apoiadores_aprovados()
            .values(f'cidade__{cidade_fk}').annotate(c=Count('id'))
            .values_list(f'cidade__{cidade_fk}', 'c')
        )
        venc_por_regiao = dict(
            Tarefa.objects.filter(excluida_em__isnull=True, prazo__lt=hoje_hm)
            .exclude(fase='concluida')
            .values(f'cidade__{cidade_fk}').annotate(c=Count('id'))
            .values_list(f'cidade__{cidade_fk}', 'c')
        )
        regions = Regiao.objects.filter(nivel=nivel).annotate(
            total_votos_2022=Sum(f'{cidades_rel}__votos_referencia_2022'),
            total_populacao=Sum(f'{cidades_rel}__populacao'),
            total_meta=Sum(f'{cidades_rel}__meta_votos'),
        )
        data = []
        for r in regions:
            value = 0
            populacao = r.total_populacao or r.populacao or 0
            meta = r.total_meta or r.meta_votos or 0
            total_apoiadores = ap_por_regiao.get(r.pk, 0)
            demandas_vencidas = venc_por_regiao.get(r.pk, 0)
            if metric == 'apoiadores':
                value = total_apoiadores
            elif metric == 'votes_2022':
                value = r.total_votos_2022 or 0
            elif metric == 'meta_progress':
                if meta > 0:
                    value = round((total_apoiadores / meta) * 100, 2)
            elif metric == 'saturation':
                if populacao > 0:
                    value = round((total_apoiadores / populacao) * 100, 4)
            elif metric == 'demandas_vencidas':
                value = demandas_vencidas
            elif metric == 'gap':
                # Gap = votos 2022 - apoiadores atuais (onde tem voto mas não tem trabalho)
                value = (r.total_votos_2022 or 0) - total_apoiadores
            data.append({
                'slug': r.slug,
                'name': r.sigla,
                'value': value,
            })
        return Response(data)

    def _city_level(self, metric):
        today = timezone.now().date()
        cities = Cidade.objects.select_related('regiao').annotate(
            # distinct: dois Count sobre relações to-many diferentes (liderancas/tarefas)
            total_apoiadores=Count(
                'liderancas', filter=q_apoiadores_aprovados('liderancas'), distinct=True,
            ),
            demandas_vencidas=Count(
                'tarefas',
                filter=Q(tarefas__excluida_em__isnull=True, tarefas__prazo__lt=today)
                & ~Q(tarefas__fase='concluida'), distinct=True,
            ),
        )
        data = []
        for c in cities:
            value = 0
            voters = c.eleitores or 0
            pop = c.populacao or 0
            if metric == 'apoiadores':
                value = c.total_apoiadores
            elif metric == 'votes_2022':
                value = c.votos_referencia_2022 or 0
            elif metric == 'meta_progress':
                if c.meta_votos > 0:
                    value = round((c.total_apoiadores / c.meta_votos) * 100, 2)
            elif metric == 'saturation':
                if pop > 0:
                    value = round((c.total_apoiadores / pop) * 100, 4)
            elif metric == 'demandas_vencidas':
                value = c.demandas_vencidas
            elif metric == 'gap':
                value = (c.votos_referencia_2022 or 0) - c.total_apoiadores
            elif metric == 'penetration':
                if voters > 0:
                    value = round((c.votos_referencia_2022 or 0) / voters * 100, 2)
            data.append({
                'slug': c.slug,
                'name': c.nome,
                'region_slug': c.regiao.slug,
                'value': value,
            })
        return Response(data)


# ─── API: DASHBOARD ───────────────────────────────────────────────

class DashboardOverviewAPI(APIView):
    def get(self, request):
        ativos = Lideranca.objects.apoiadores_aprovados()
        total_apoiadores = ativos.count()
        total_coordenadores = Lideranca.objects.filter(papel='coordenador').count()
        total_cabos = Lideranca.objects.filter(papel='cabo').count()
        total_parceiros = ativos.filter(tipo='empresarial').count()
        total_liderancas = ativos.filter(tipo='politico').count()
        total_empresas = ativos.filter(tipo='empresarial').count()
        total_contatos = total_apoiadores + total_coordenadores + total_cabos

        # Separate queries to avoid JOIN multiplication
        votos_by_region = dict(
            Cidade.objects.values('regiao_id')
            .annotate(total=Sum('votos_referencia_2022'))
            .values_list('regiao_id', 'total')
        )
        apoiadores_by_region = dict(
            Lideranca.objects.apoiadores_aprovados()
            .values('cidade__regiao_id')
            .annotate(total=Count('id'))
            .values_list('cidade__regiao_id', 'total')
        )

        regions = []
        # Overview geral é por associação (as 21 históricas); meso/micro não entram
        # aqui (seriam cards zerados — cidade.regiao_id é a associação).
        for r in Regiao.objects.filter(nivel='associacao').select_related('macro_regiao').order_by('nome'):
            regions.append({
                'nome': r.nome,
                'slug': r.slug,
                'sigla': r.sigla,
                'populacao': r.populacao,
                'meta_votos': r.meta_votos,
                'cor': r.cor,
                'eleitores': r.eleitores,
                'macro_regiao': r.macro_regiao.nome if r.macro_regiao else '',
                'total_apoiadores': apoiadores_by_region.get(r.id, 0),
                'total_votos_2022': votos_by_region.get(r.id, 0) or 0,
            })

        return Response({
            'total_apoiadores': total_apoiadores,
            'total_coordenadores': total_coordenadores,
            'total_cabos': total_cabos,
            'total_parceiros': total_parceiros,
            'total_liderancas': total_liderancas,
            'total_empresas': total_empresas,
            'total_contatos': total_contatos,
            'regions': regions,
        })


class RegionDashboardAPI(APIView):
    def get(self, request, slug):
        region = Regiao.objects.get(slug=slug)
        # Relação das cidades pelo nível da região (assoc/micro/meso).
        _fk, cidades_rel = NIVEL_REL.get(region.nivel, NIVEL_REL['associacao'])
        total_apoiadores = Lideranca.objects.apoiadores_aprovados().filter(
            **{f'cidade__{_fk}': region},
        ).count()
        # Coordenador é vínculo de associação (Lideranca.regiao); em meso/micro fica 0.
        total_coordenadores = Lideranca.objects.filter(papel='coordenador', regiao=region).count()
        total_cabos = Lideranca.objects.filter(papel='cabo', **{f'cidade__{_fk}': region}).count()

        cities = getattr(region, cidades_rel).annotate(
            total_apoiadores=Count(
                'liderancas', filter=q_apoiadores_aprovados('liderancas'),
            ),
        )
        # População/meta somadas dos municípios (meso/micro têm o campo próprio zerado).
        agg = getattr(region, cidades_rel).aggregate(
            pop=Sum('populacao'), meta=Sum('meta_votos'))

        return Response({
            'region': {
                'name': region.sigla,
                'full_name': region.nome_completo or region.nome,
                'population': agg['pop'] or region.populacao or 0,
                'meta_votes': agg['meta'] or region.meta_votos or 0,
            },
            'total_apoiadores': total_apoiadores,
            'total_coordenadores': total_coordenadores,
            'total_cabos': total_cabos,
            'cities': list(cities.values(
                'nome', 'slug', 'populacao', 'votos_referencia_2022',
                'meta_votos', 'total_apoiadores',
            )),
        })


class CityDashboardAPI(APIView):
    def get(self, request, slug):
        city = Cidade.objects.select_related('regiao').get(slug=slug)
        today = timezone.now().date()

        apoiadores_ativos = Lideranca.objects.apoiadores_aprovados().filter(cidade=city).count()

        # Doações (módulo removido — métrica neutralizada)
        total_doacoes = 0

        # Tarefas
        tarefas_city = Tarefa.objects.filter(cidade=city).exclude(excluida_em__isnull=False)
        tarefas_total = tarefas_city.count()
        tarefas_concluidas = tarefas_city.filter(fase='concluida').count()
        tarefas_vencidas = tarefas_city.filter(prazo__lt=today).exclude(fase='concluida').count()

        # Compromissos
        compromissos = Compromisso.objects.filter(cidade=city).count()

        # Análise estratégica
        strategic = self._build_strategic(city, apoiadores_ativos, today)

        return Response({
            'city': {
                'name': city.nome,
                'slug': city.slug,
                'region': city.regiao.sigla,
                'region_slug': city.regiao.slug,
                'population': city.populacao,
                'registered_voters': city.eleitores,
                'mayor_name': city.prefeito_nome,
                'mayor_party': city.prefeito_partido,
                'num_vereadores': city.num_vereadores,
                'num_vereadores_partido': city.num_vereadores_partido,
                'diretorio_presidente': city.presidente_diretorio,
                'votes_referencia_2022': city.votos_referencia_2022,
                'meta_votes': city.meta_votos,
            },
            'total_apoiadores': apoiadores_ativos,
            'total_coordenadores': Lideranca.objects.filter(papel='coordenador', regiao=city.regiao).count(),
            'total_cabos': Lideranca.objects.filter(papel='cabo', cidade=city).count(),
            'total_doacoes': float(total_doacoes),
            'tarefas_total': tarefas_total,
            'tarefas_concluidas': tarefas_concluidas,
            'tarefas_vencidas': tarefas_vencidas,
            'compromissos': compromissos,
            'strategic': strategic,
        })

    def _build_strategic(self, city, apoiadores_count, today):
        votes_2022 = city.votos_referencia_2022 or 0
        meta = city.meta_votos or 0
        voters = city.eleitores or 0
        penetration = round((votes_2022 / voters * 100), 2) if voters > 0 else 0

        state = Cidade.objects.aggregate(
            total_votes=Sum('votos_referencia_2022'),
            total_voters=Sum('eleitores'),
        )
        avg_penetration = round(
            (state['total_votes'] or 0) / max(state['total_voters'] or 1, 1) * 100, 2
        )

        mayor_party = (city.prefeito_partido or '').upper().strip()
        if mayor_party in ALLIED_PARTIES:
            alignment = 'allied'
        elif mayor_party in ADVERSARY_PARTIES:
            alignment = 'adversary'
        else:
            alignment = 'neutral'

        good_performance = penetration >= avg_penetration

        if alignment == 'allied' and good_performance:
            classification = 'base_forte'
        elif alignment == 'adversary' and good_performance:
            classification = 'potencial_oculto'
        elif alignment == 'allied' and not good_performance:
            classification = 'aliado_fraco'
        elif alignment == 'adversary' and not good_performance:
            classification = 'territorio_hostil'
        else:
            classification = 'potencial_oculto' if good_performance else 'neutro'

        classification_labels = {
            'base_forte': 'Base Forte',
            'aliado_fraco': 'Aliado Fraco',
            'potencial_oculto': 'Potencial Oculto',
            'territorio_hostil': 'Território Hostil',
            'neutro': 'Neutro',
        }

        align_score = {'allied': 100, 'neutral': 50, 'adversary': 0}[alignment]
        ver_pct = (city.num_vereadores_partido / city.num_vereadores * 100) if city.num_vereadores else 0
        pen_normalized = min(penetration / max(avg_penetration * 2, 0.01) * 100, 100)
        has_structure = 100 if city.presidente_diretorio else 0
        total_score = round(
            align_score * 0.30 + ver_pct * 0.20 + pen_normalized * 0.35 + has_structure * 0.15
        )

        has_coordinator = Lideranca.objects.filter(papel='coordenador', regiao=city.regiao).exists()
        tarefas_vencidas = Tarefa.objects.filter(
            cidade=city, prazo__lt=today,
        ).exclude(fase='concluida').exclude(excluida_em__isnull=False).count()

        recommendations = []
        if not has_coordinator:
            recommendations.append({
                'priority': 'urgent', 'icon': 'alert',
                'text': 'Designar coordenador regional — região sem representante.',
            })
        if classification == 'potencial_oculto':
            recommendations.append({
                'priority': 'high', 'icon': 'target',
                'text': 'Prioridade alta — bom desempenho sem apoio político local.',
            })
        if classification == 'aliado_fraco':
            recommendations.append({
                'priority': 'high', 'icon': 'trending-up',
                'text': 'Aliado fraco — intensificar articulação.',
            })
        if tarefas_vencidas > 0:
            recommendations.append({
                'priority': 'urgent', 'icon': 'alert',
                'text': f'{tarefas_vencidas} tarefa(s) em atraso nesta cidade.',
            })

        return {
            'classification': classification,
            'classification_label': classification_labels[classification],
            'alignment': alignment,
            'penetration': penetration,
            'avg_penetration': avg_penetration,
            'score': total_score,
            'recommendations': recommendations,
            'potential': {
                'votes_2022': votes_2022,
                'meta_2026': meta,
                'votes_needed': max(meta - votes_2022, 0),
                'penetration': penetration,
            },
            'structure': {
                'alignment': alignment,
                'mayor_name': city.prefeito_nome or '',
                'mayor_party': city.prefeito_partido or '',
                'num_vereadores': city.num_vereadores,
                'num_vereadores_partido': city.num_vereadores_partido,
                'diretorio_presidente': city.presidente_diretorio or '',
                'has_coordinator': has_coordinator,
            },
        }


class StrategicAnalysisAPI(APIView):
    """Análise estratégica: classificação de cidades com IBGE + Rede PL + CRM."""
    @method_decorator(cache_page(60))  # cache curto: reflete cadastros de políticos quase na hora
    def get(self, request):
        today = timezone.now().date()
        cities = (
            Cidade.objects
            .select_related('regiao')
            .annotate(
                # distinct=True é obrigatório: são vários Count() sobre relações
                # to-many diferentes (liderancas, tarefas, compromissos) na mesma
                # query — sem distinct, o JOIN cartesiano multiplica as contagens
                # (ex.: 1 apoiador virava 53). CLAUDE.md §12/§3.
                total_apoiadores=Count(
                    'liderancas', filter=q_apoiadores_aprovados('liderancas'), distinct=True,
                ),
                total_demandas=Count(
                    'tarefas',
                    filter=Q(tarefas__excluida_em__isnull=True), distinct=True,
                ),
                demandas_vencidas=Count(
                    'tarefas',
                    filter=Q(tarefas__excluida_em__isnull=True, tarefas__prazo__lt=today)
                    & ~Q(tarefas__fase='concluida'), distinct=True,
                ),
                demandas_concluidas=Count(
                    'tarefas',
                    filter=Q(tarefas__excluida_em__isnull=True, tarefas__fase='concluida'), distinct=True,
                ),
                total_compromissos=Count('compromissos', distinct=True),
                cabo_count=Count('liderancas', filter=Q(liderancas__papel='cabo'), distinct=True),
                coord_count=Count('regiao__liderancas', filter=Q(regiao__liderancas__papel='coordenador'), distinct=True),
            )
            .order_by('regiao__nome', 'nome')
        )

        # Ativos políticos AO VIVO a partir do Apoiador.cargo (fonte da verdade:
        # o cadastro). Quem é cadastrado como prefeito/vereador/etc. já conta aqui.
        from collections import defaultdict
        politicos = defaultdict(lambda: {
            'prefeito': 0, 'vice': 0, 'vereador': 0, 'presidente': 0,
            'votos_maquina': 0, 'meta_transferir': 0,
        })
        for ap in Lideranca.objects.apoiadores_aprovados().filter(tipo='politico').values(
            'cidade_id', 'cargo', 'votos_referencia', 'meta_votos_transferir',
        ):
            d = politicos[ap['cidade_id']]
            mapa_cargo = {'prefeito': 'prefeito', 'vice_prefeito': 'vice',
                          'vereador': 'vereador', 'presidente_diretorio': 'presidente'}
            chave = mapa_cargo.get(ap['cargo'])
            if chave:
                d[chave] += 1
            d['votos_maquina'] += ap['votos_referencia'] or 0
            d['meta_transferir'] += ap['meta_votos_transferir'] or 0

        TARGET_PEN, GROWTH = 0.012, 1.4

        totals = Cidade.objects.aggregate(
            total_votes=Sum('votos_referencia_2022'),
            total_voters=Sum('eleitores'),
        )
        avg_penetration = 0
        if totals['total_voters']:
            avg_penetration = (totals['total_votes'] or 0) / totals['total_voters'] * 100

        # IBGE indicators indexed by city_id
        indicadores = {
            ind.cidade_id: ind
            for ind in IndicadorMunicipal.objects.all().order_by('-ano_referencia')
        }

        # State-level PL network density for normalization.
        # Count e Sum em queries separadas: juntos, o join de liderancas inflaria
        # o Sum('eleitores').
        state_apoiadores = Lideranca.objects.apoiadores_aprovados().count()
        state_voters = Cidade.objects.aggregate(v=Sum('eleitores'))['v'] or 0
        state_density = (state_apoiadores / state_voters * 100) if state_voters else 0

        result = []
        summary = {
            'maquina_voto': 0, 'aliado_ativar': 0, 'construir': 0,
            'disputa': 0, 'hostil': 0, 'neutro': 0,
        }

        for city in cities:
            voters = city.eleitores or 0
            votes = city.votos_referencia_2022 or 0
            penetration = (votes / voters * 100) if voters > 0 else 0
            mayor_party = (city.prefeito_partido or '').upper().strip()

            # ativos políticos aliados desta cidade (do cadastro)
            pol = politicos.get(city.id, {'prefeito': 0, 'vice': 0, 'vereador': 0,
                                          'presidente': 0, 'votos_maquina': 0, 'meta_transferir': 0})
            tem_diretorio = pol['presidente'] > 0 or bool(city.presidente_diretorio)
            aliados = pol['prefeito'] + pol['vice'] + pol['vereador'] + (1 if tem_diretorio else 0)
            cabos = city.cabo_count or 0
            meta = city.meta_votos or int(round(max(votes * GROWTH, voters * TARGET_PEN) / 10) * 10)
            gap = max(0, meta - votes)

            # alinhamento (aliado = temos políticos; adversário = controle marcado/auto)
            controle = city.controle or ''
            if controle == 'adversario' or mayor_party in ADVERSARY_PARTIES:
                alignment = 'adversary'
            elif aliados > 0 or mayor_party in ALLIED_PARTIES:
                alignment = 'allied'
            else:
                alignment = 'neutral'

            # classificação pelo CAMINHO POLÍTICO até o voto
            # (controle adversário/disputa sobrepõe — é o terreno do oponente)
            if controle == 'adversario':
                cls = 'hostil'
            elif controle == 'disputado':
                cls = 'disputa'
            elif aliados > 0:
                cls = 'maquina_voto' if cabos > 0 else 'aliado_ativar'
            elif gap >= 120:
                cls = 'construir'
            else:
                cls = 'neutro'

            ver_pct = (pol['vereador'] * 20)  # aproximação de cobertura
            pen_norm = min(penetration / max(avg_penetration * 2, 0.01) * 100, 100)
            has_struct = 100 if tem_diretorio else 0
            align_score = {'allied': 100, 'neutral': 50, 'adversary': 0}[alignment]
            score = round(align_score * 0.30 + min(ver_pct, 100) * 0.20 + pen_norm * 0.35 + has_struct * 0.15)

            summary[cls] += 1

            # PL Network score (same formula as PLNetworkAPI)
            coord_s = 100 if (city.coord_count or 0) > 0 else 0
            ver_s = min(ver_pct * 2, 100)
            dir_s = 100 if city.presidente_diretorio else 0
            density = ((city.total_apoiadores or 0) / max(voters, 1)) * 100
            contact_s = min(density / max(state_density * 2, 0.01) * 100, 100)
            cabo_s = min((city.cabo_count or 0) * 25, 100)
            pl_network_score = round(
                coord_s * 0.25 + ver_s * 0.25 + dir_s * 0.20 + contact_s * 0.15 + cabo_s * 0.15
            )

            # IBGE indicators
            ind = indicadores.get(city.id)
            ibge = {}
            if ind and ind.populacao > 0:
                pop = ind.populacao
                ibge = {
                    'renda_per_capita': float(ind.renda_per_capita),
                    'pib_per_capita': round(ind.pib_per_capita) if ind.pib_per_capita is not None else None,
                    'bf_pct': round(ind.familias_bolsa_familia / pop * 100, 2),
                    'meis_pct': round(ind.meis_ativos / pop * 100, 2),
                    'pop_urbana_pct': round(ind.populacao_urbana / pop * 100, 1) if ind.populacao_urbana else None,
                    'idosos_pct': round(ind.idosos_60_mais / pop * 100, 1) if ind.idosos_60_mais else None,
                    'jovens_pct': round(ind.jovens_18_29 / pop * 100, 1) if ind.jovens_18_29 else None,
                    'escolaridade': float(ind.taxa_alfabetizacao),
                }

            # CRM activity
            crm = {
                'demandas_total': city.total_demandas,
                'demandas_vencidas': city.demandas_vencidas,
                'demandas_concluidas': city.demandas_concluidas,
                'compromissos': city.total_compromissos,
                'cabos': city.cabo_count or 0,
                'has_coordinator': (city.coord_count or 0) > 0,
            }

            # Alertas estratégicos
            alertas = []
            if cls == 'aliado_ativar':
                alertas.append('aliado_dormindo')   # tem político aliado mas sem cabo
            if cls == 'maquina_voto' and pol['meta_transferir'] == 0:
                alertas.append('sem_meta_transferencia')
            if cls == 'construir':
                alertas.append('recrutar_lideranca')
            if pl_network_score >= 40 and penetration < avg_penetration:
                alertas.append('estrutura_sem_conversao')
            if city.demandas_vencidas > 0:
                alertas.append('demandas_atrasadas')
            if not (city.coord_count or 0) > 0:
                alertas.append('sem_coordenador')

            entry = {
                'slug': city.slug,
                'name': city.nome,
                'region_name': city.regiao.sigla,
                'region_slug': city.regiao.slug,
                'population': city.populacao,
                'registered_voters': voters,
                'mayor_name': city.prefeito_nome or '',
                'mayor_party': city.prefeito_partido or '',
                'num_vereadores': city.num_vereadores or 0,
                'num_vereadores_partido': city.num_vereadores_partido or 0,
                'votes_2022': votes,
                'penetration': round(penetration, 2),
                'classification': cls,
                'alignment': alignment,
                'score': score,
                'apoiadores': city.total_apoiadores,
                'pl_network_score': pl_network_score,
                'crm': crm,
                'alertas': alertas,
                'gap': gap,
                'controle': controle,
                'adversario_nome': city.adversario_nome or '',
                'adversario_partido': city.adversario_partido or '',
                'politicos': {
                    'prefeito': pol['prefeito'], 'vice': pol['vice'],
                    'vereador': pol['vereador'], 'presidente': pol['presidente'],
                    'aliados': aliados, 'cabos': cabos,
                    'votos_maquina': pol['votos_maquina'],
                    'meta_transferir': pol['meta_transferir'],
                },
            }
            if ibge:
                entry['ibge'] = ibge
            result.append(entry)

        votos_maquina_total = sum(p['votos_maquina'] for p in politicos.values())
        meta_transferir_total = sum(p['meta_transferir'] for p in politicos.values())
        return Response({
            'avg_penetration': round(avg_penetration, 2),
            'summary': summary,
            'totais_politicos': {
                'votos_maquina': votos_maquina_total,
                'meta_transferir': meta_transferir_total,
                'aliados': sum(1 for p in politicos.values() if (p['prefeito'] + p['vice'] + p['vereador'] + p['presidente']) > 0),
            },
            'cities': result,
        })


class PLNetworkAPI(APIView):
    """Força da rede PL por cidade + resultados eleitorais + demandas."""
    @method_decorator(cache_page(60 * 15))
    def get(self, request):
        today = timezone.now().date()
        # Contagens por cidade em queries ISOLADAS (uma relação to-many por query) —
        # antes eram 6 Count sobre 3 relações no MESMO annotate, gerando fan-out
        # cartesiano corrigido por distinct (~1s). Mesmas expressões Count → idêntico.
        lid_counts = {
            row['id']: row for row in Cidade.objects.values('id').annotate(
                ap=Count('liderancas', filter=q_apoiadores_aprovados('liderancas'), distinct=True),
                cabo=Count('liderancas', filter=Q(liderancas__papel='cabo'), distinct=True),
            )
        }
        tar_counts = {
            row['id']: row for row in Cidade.objects.values('id').annotate(
                total=Count('tarefas', filter=Q(tarefas__excluida_em__isnull=True), distinct=True),
                vencidas=Count(
                    'tarefas',
                    filter=Q(tarefas__excluida_em__isnull=True, tarefas__prazo__lt=today)
                    & ~Q(tarefas__fase='concluida'), distinct=True,
                ),
                concluidas=Count(
                    'tarefas',
                    filter=Q(tarefas__excluida_em__isnull=True, tarefas__fase='concluida'), distinct=True,
                ),
            )
        }
        coord_counts = dict(
            Cidade.objects.values_list('id').annotate(
                c=Count('regiao__liderancas', filter=Q(regiao__liderancas__papel='coordenador'), distinct=True),
            ).values_list('id', 'c')
        )
        cities = (
            Cidade.objects
            .select_related('regiao')
            .order_by('regiao__nome', 'nome')
        )

        # Totais de estado: Count e Sum em queries separadas (join inflaria os Sum).
        total_apoiadores_st = Lideranca.objects.apoiadores_aprovados().count()
        sums_st = Cidade.objects.aggregate(
            total_voters=Sum('eleitores'), total_votes=Sum('votos_referencia_2022'),
        )
        total_voters_st = sums_st['total_voters'] or 0
        total_votes_st = sums_st['total_votes'] or 0
        state_density = (total_apoiadores_st / total_voters_st * 100) if total_voters_st else 0
        avg_penetration = (total_votes_st / total_voters_st * 100) if total_voters_st else 0

        politicos = _politicos_por_cidade()   # ativos do cadastro (Apoiador.cargo)
        raw_results = []

        for city in cities:
            lc = lid_counts.get(city.id, {})
            tc = tar_counts.get(city.id, {})
            total_apoiadores = lc.get('ap', 0)
            cabo_count = lc.get('cabo', 0)
            coord_count = coord_counts.get(city.id, 0)
            total_demandas = tc.get('total', 0)
            demandas_vencidas = tc.get('vencidas', 0)
            demandas_concluidas = tc.get('concluidas', 0)
            pol = politicos.get(city.id, {'prefeito': 0, 'vice': 0, 'vereador': 0,
                                          'presidente': 0, 'votos_maquina': 0, 'meta_transferir': 0})
            voters = city.eleitores or 0
            votes_2022 = city.votos_referencia_2022 or 0
            penetration = (votes_2022 / voters * 100) if voters > 0 else 0

            coord_score = 100 if (coord_count or 0) > 0 else 0
            ver_score = min(pol['vereador'] * 30, 100)        # cada vereador aliado = 30 pts
            pref_score = 100 if pol['prefeito'] > 0 else 0
            dir_score = 100 if (pol['presidente'] > 0 or city.presidente_diretorio) else 0
            density = ((total_apoiadores or 0) / max(voters, 1)) * 100
            contact_score = min(density / max(state_density * 2, 0.01) * 100, 100)
            cabo_score = min((cabo_count or 0) * 25, 100)

            total_score = round(
                coord_score * 0.18
                + ver_score * 0.25
                + pref_score * 0.17
                + dir_score * 0.15
                + contact_score * 0.10
                + cabo_score * 0.15
            )

            # Diagnostic: structure vs performance
            good_perf = penetration >= avg_penetration
            has_structure = total_score > 30
            if has_structure and not good_perf:
                diagnostic = 'estrutura_sem_conversao'
            elif not has_structure and good_perf:
                diagnostic = 'voto_organico'
            elif has_structure and good_perf:
                diagnostic = 'maquina_funcionando'
            else:
                diagnostic = 'sem_presenca'

            raw_results.append({
                'slug': city.slug,
                'name': city.nome,
                'region_name': city.regiao.sigla,
                'region_slug': city.regiao.slug,
                'population': city.populacao,
                'registered_voters': voters,
                'mayor_party': city.prefeito_partido or '',
                'num_vereadores': city.num_vereadores or 0,
                'num_vereadores_partido': pol['vereador'],
                'prefeito_aliado': pol['prefeito'] > 0,
                'has_coordinator': (coord_count or 0) > 0,
                'diretorio_presidente': city.presidente_diretorio or ('Diretório' if pol['presidente'] else ''),
                'votos_maquina': pol['votos_maquina'],
                'apoiadores': total_apoiadores or 0,
                'cabos': cabo_count or 0,
                'raw_score': total_score,
                # Electoral performance
                'votes_2022': votes_2022,
                'penetration': round(penetration, 2),
                # Demands
                'demandas_total': total_demandas,
                'demandas_vencidas': demandas_vencidas,
                'demandas_concluidas': demandas_concluidas,
                # Diagnostic
                'diagnostic': diagnostic,
            })

        # Normalizar scores em percentis para gerar variação real de cores
        non_zero = sorted(r['raw_score'] for r in raw_results if r['raw_score'] > 0)
        if non_zero:
            p25 = non_zero[len(non_zero) // 4]
            p50 = non_zero[len(non_zero) // 2]
            p75 = non_zero[len(non_zero) * 3 // 4]
        else:
            p25 = p50 = p75 = 0

        result = []
        levels = {'forte': 0, 'moderada': 0, 'fraca': 0, 'ausente': 0}
        diagnostics = {'estrutura_sem_conversao': 0, 'voto_organico': 0, 'maquina_funcionando': 0, 'sem_presenca': 0}

        for r in raw_results:
            raw = r['raw_score']
            if raw == 0:
                level = 'ausente'
                score = 0
            elif raw <= p25:
                level = 'fraca'
                score = round(raw / max(p25, 1) * 34)
            elif raw <= p50:
                level = 'moderada'
                score = 35 + round((raw - p25) / max(p50 - p25, 1) * 24)
            elif raw <= p75:
                level = 'moderada'
                score = 50 + round((raw - p50) / max(p75 - p50, 1) * 9)
            else:
                level = 'forte'
                max_raw = non_zero[-1] if non_zero else 1
                score = 60 + round((raw - p75) / max(max_raw - p75, 1) * 40)

            levels[level] += 1
            diagnostics[r['diagnostic']] += 1
            r['score'] = min(score, 100)
            r['level'] = level
            del r['raw_score']
            result.append(r)

        return Response({
            'state_density': round(state_density, 2),
            'avg_penetration': round(avg_penetration, 2),
            'summary': levels,
            'diagnostics': diagnostics,
            'cities': result,
        })


class DoacoesMapAPI(APIView):
    """Doações por região/cidade — módulo de doações removido.

    A rota é mantida por compatibilidade com o front (setDoacoes), mas não há
    mais fonte de dados: retorna lista vazia (métrica neutralizada)."""
    def get(self, request):
        return Response([])


class DemandasMapAPI(APIView):
    """Demandas/tarefas por região e cidade, cruzadas com a oportunidade de
    votos (esforço × oportunidade), com filtro por tipo e lista de urgentes.

    Mantém compatibilidade: a resposta tem 'regions' (lista, formato antigo) +
    'cities', 'urgentes', 'summary', 'tipos'."""

    def get(self, request):
        from tarefas.models import Tarefa
        today = timezone.now().date()
        tipo = request.GET.get('tipo', '')

        base = Tarefa.objects.filter(excluida_em__isnull=True)
        if tipo:
            base = base.filter(tipo=tipo)

        # contagens por cidade
        from collections import defaultdict
        cdata = defaultdict(lambda: {'total': 0, 'active': 0, 'overdue': 0, 'completed': 0})
        for t in base.values('cidade_id', 'fase', 'prazo'):
            if not t['cidade_id']:
                continue
            d = cdata[t['cidade_id']]
            d['total'] += 1
            if t['fase'] == 'concluida':
                d['completed'] += 1
            else:
                d['active'] += 1
                if t['prazo'] and t['prazo'] < today:
                    d['overdue'] += 1

        # tipos disponíveis (contagem global, sem filtro)
        tipos_count = dict(
            Tarefa.objects.filter(excluida_em__isnull=True)
            .values_list('tipo').annotate(n=Count('id'))
        )
        tipos = [{'value': v, 'label': l, 'count': tipos_count.get(v, 0)}
                 for v, l in Tarefa.TIPO_CHOICES]

        # meta sugerida p/ oportunidade (mesma fórmula do Vitória)
        TARGET_PEN, GROWTH = 0.012, 1.4

        cities, regions = {}, {}
        for cid in Cidade.objects.select_related('regiao'):
            d = cdata.get(cid.id, {'total': 0, 'active': 0, 'overdue': 0, 'completed': 0})
            v = cid.votos_referencia_2022 or 0
            elei = cid.eleitores or 0
            meta = cid.meta_votos or int(round(max(v * GROWTH, elei * TARGET_PEN) / 10) * 10)
            gap = max(0, meta - v)
            status = 'overdue' if d['overdue'] > 0 else ('ok' if d['active'] > 0 else 'empty')
            cities[cid.slug] = {
                'id': cid.id, 'name': cid.nome, 'region_slug': cid.regiao.slug,
                'total': d['total'], 'active': d['active'], 'overdue': d['overdue'],
                'completed': d['completed'], 'status': status,
                'gap': gap, 'lat': cid.latitude, 'lng': cid.longitude,
            }
            rg = regions.setdefault(cid.regiao.slug, {
                'slug': cid.regiao.slug, 'name': cid.regiao.sigla, 'nome': cid.regiao.nome,
                'total': 0, 'active': 0, 'overdue': 0, 'completed': 0, 'gap': 0,
            })
            for k in ('total', 'active', 'overdue', 'completed'):
                rg[k] += d[k]
            rg['gap'] += gap

        # esforço × oportunidade: normaliza e calcula mismatch por região
        max_esf = max((r['active'] for r in regions.values()), default=0) or 1
        max_gap = max((r['gap'] for r in regions.values()), default=0) or 1
        for r in regions.values():
            esf = r['active'] / max_esf
            opo = r['gap'] / max_gap
            r['mismatch'] = round((opo - esf) * 100)   # >0 oportunidade ignorada; <0 esforço sobrando
            r['status'] = 'overdue' if r['overdue'] > 0 else ('ok' if r['active'] > 0 else 'empty')
            if r['active'] == 0 and opo >= 0.5:
                r['alerta'] = 'negligencia'
            elif esf >= 0.5 and opo <= 0.25:
                r['alerta'] = 'desperdicio'
            else:
                r['alerta'] = None

        # mesma lógica de mismatch por cidade (para a cor no nível de cidade)
        max_esf_c = max((c['active'] for c in cities.values()), default=0) or 1
        max_gap_c = max((c['gap'] for c in cities.values()), default=0) or 1
        for c in cities.values():
            esf = c['active'] / max_esf_c
            opo = c['gap'] / max_gap_c
            c['mismatch'] = round((opo - esf) * 100)
            c['alerta'] = 'negligencia' if (c['active'] == 0 and opo >= 0.4) else None

        # urgentes (mais vencidas primeiro)
        urgentes = []
        for t in base.exclude(fase='concluida').filter(prazo__lt=today).select_related('cidade', 'responsavel').order_by('prazo')[:20]:
            urgentes.append({
                'id': t.id, 'titulo': t.titulo, 'tipo': t.get_tipo_display(),
                'cidade': t.cidade.nome if t.cidade else '—',
                'cidade_slug': t.cidade.slug if t.cidade else '',
                'prazo': t.prazo.strftime('%d/%m') if t.prazo else '',
                'dias_atraso': (today - t.prazo).days if t.prazo else 0,
                'prioridade': t.get_prioridade_display(),
                'responsavel': t.responsavel.get_full_name() if t.responsavel else '',
            })

        regions_list = sorted(regions.values(), key=lambda r: -r['overdue'])
        summary = {
            'total': sum(r['total'] for r in regions.values()),
            'active': sum(r['active'] for r in regions.values()),
            'overdue': sum(r['overdue'] for r in regions.values()),
            'completed': sum(r['completed'] for r in regions.values()),
            'negligencia': sum(1 for r in regions.values() if r['alerta'] == 'negligencia'),
            'desperdicio': sum(1 for r in regions.values() if r['alerta'] == 'desperdicio'),
        }
        return Response({
            'regions': regions_list,
            'regions_map': {r['slug']: r for r in regions.values()},
            'cities': cities,
            'urgentes': urgentes,
            'summary': summary,
            'tipos': tipos,
            'tipo_ativo': tipo,
        })


def _coords_cidade(city):
    """lat/lng da cidade; cai no centróide do geojson se faltar coordenada."""
    lat, lng = city.latitude, city.longitude
    if (not lat or not lng) and city.geojson:
        geo = city.geojson
        coords = geo.get('coordinates', [])
        ring = coords[0] if geo.get('type') == 'Polygon' else (coords[0][0] if coords else [])
        if ring:
            lng = sum(p[0] for p in ring) / len(ring)
            lat = sum(p[1] for p in ring) / len(ring)
    return lat, lng


def _stop_from_compromisso(comp, ordem, is_origin, observacao=''):
    """Monta um ponto de roteiro a partir de um Compromisso (com cidade)."""
    city = comp.cidade
    lat, lng = _coords_cidade(city)
    if not lat or not lng:
        return None
    # Converter para horário local antes de extrair data/hora (DB guarda em UTC).
    ini = timezone.localtime(comp.data_hora_inicio) if comp.data_hora_inicio else None
    fim = timezone.localtime(comp.data_hora_fim) if comp.data_hora_fim else None
    dur = int((fim - ini).total_seconds() // 60) if (ini and fim) else None
    return {
        'city_name': city.nome,
        'city_slug': city.slug,
        'lat': lat,
        'lng': lng,
        'date': ini.date().isoformat() if ini else '',
        'time': ini.strftime('%H:%M:%S') if ini else '',
        'end_time': fim.strftime('%H:%M:%S') if fim else '',
        'duration_min': dur,
        'task_title': comp.titulo or '',
        'compromisso_id': comp.id,
        'observacao': observacao or '',
        'is_overnight': False,
        'is_origin': is_origin,
        'order': ordem,
    }


def _stop_from_evento(ev):
    """Monta um ponto de roteiro a partir de um Evento (com cidade)."""
    city = ev.cidade
    lat, lng = _coords_cidade(city)
    if not lat or not lng:
        return None
    return {
        'city_name': city.nome,
        'city_slug': city.slug,
        'lat': lat,
        'lng': lng,
        'date': ev.data.isoformat() if ev.data else '',
        'time': ev.horario_inicio.strftime('%H:%M:%S') if ev.horario_inicio else '',
        'end_time': ev.horario_fim.strftime('%H:%M:%S') if ev.horario_fim else '',
        'duration_min': None,
        'task_title': ev.nome,
        'compromisso_id': None,
        'observacao': ev.local or '',
        'publico': ev.publico_estimado,
        'is_overnight': False,
        'is_origin': True,
        'order': 0,
    }


class RoteirosMapAPI(APIView):
    """Roteiros/itinerários com lat/lng para cada parada.

    Três fontes (CLAUDE.md — "ambos" + eventos):
      1. Roteiro/RoteiroPonto — caravanas multi-parada do construtor de roteiros.
      2. Compromisso tipo='roteiro' avulso — vira um roteiro de uma parada só.
      3. Evento (com cidade) — também é "onde o candidato passou/vai"; entra como
         ponto único, com `kind='evento'` para o front diferenciar e filtrar.
    """
    # status do Roteiro → o que o sc-map.js entende
    _STATUS_ROTEIRO = {
        'planejado': 'planned',
        'em_andamento': 'in_progress',
        'concluido': 'completed',
    }
    # status do Compromisso → idem (avulsos tipo roteiro)
    _STATUS_COMP = {
        'pendente': 'planned',
        'confirmado': 'confirmed',
        'realizado': 'completed',
    }
    # status do Evento → idem (participou = onde passei; demais = onde vou)
    _STATUS_EVENTO = {
        'participou': 'completed',
        'confirmado': 'confirmed',
        'identificado': 'planned',
        'avaliando': 'planned',
    }

    def get(self, request):
        show_completed = request.GET.get('completed', 'false') == 'true'
        roteiros = []

        qs = Roteiro.objects.select_related('regiao').prefetch_related(
            'pontos__compromisso__cidade',
        )
        if not show_completed:
            qs = qs.exclude(status='concluido')

        usados_comp = set()
        for roteiro in qs:
            stops = []
            for ponto in roteiro.pontos.select_related('compromisso__cidade').order_by('ordem'):
                comp = ponto.compromisso
                if not comp or not comp.cidade:
                    continue
                usados_comp.add(comp.id)
                st = _stop_from_compromisso(comp, ponto.ordem, ponto.ordem == 0, ponto.observacao_ponto)
                if st:
                    stops.append(st)
            if stops:
                roteiros.append({
                    'id': roteiro.id,
                    'name': roteiro.titulo,
                    'date': roteiro.data.isoformat() if roteiro.data else '',
                    'status': self._STATUS_ROTEIRO.get(roteiro.status, roteiro.status),
                    'kind': 'roteiro',
                    'single': False,
                    'stops': stops,
                })

        # Compromissos tipo 'roteiro' que NÃO estão em nenhum Roteiro → parada única.
        avulsos = (
            Compromisso.objects.filter(tipo='roteiro')
            .exclude(status='cancelado')
            .exclude(id__in=usados_comp)
            .select_related('cidade')
            .order_by('data_hora_inicio')
        )
        if not show_completed:
            avulsos = avulsos.exclude(status='realizado')
        for comp in avulsos:
            if not comp.cidade:
                continue
            st = _stop_from_compromisso(comp, 0, True)
            if st:
                roteiros.append({
                    'id': f'c{comp.id}',
                    'name': comp.titulo,
                    'date': timezone.localtime(comp.data_hora_inicio).date().isoformat() if comp.data_hora_inicio else '',
                    'status': self._STATUS_COMP.get(comp.status, 'planned'),
                    'kind': 'compromisso',
                    'single': True,
                    'stops': [st],
                })

        # Eventos com cidade → também são "onde o candidato passa/vai".
        eventos = (
            Evento.objects.exclude(status='descartado')
            .select_related('cidade').order_by('data')
        )
        if not show_completed:
            eventos = eventos.exclude(status='participou')
        for ev in eventos:
            if not ev.cidade:
                continue
            st = _stop_from_evento(ev)
            if st:
                roteiros.append({
                    'id': f'e{ev.id}',
                    'name': ev.nome,
                    'date': ev.data.isoformat() if ev.data else '',
                    'status': self._STATUS_EVENTO.get(ev.status, 'planned'),
                    'kind': 'evento',
                    'relevancia': ev.relevancia,
                    'single': True,
                    'stops': [st],
                })

        return Response(roteiros)


class RoteiroDiaAPI(APIView):
    """Roteiro do dia: agrupa por DATA tudo que tem cidade + horário
    (compromissos com cidade + eventos) e encadeia por ordem de horário, num
    trajeto único por dia — o "por onde o candidato passou/vai naquele dia"."""
    def get(self, request):
        from collections import defaultdict
        show_completed = request.GET.get('completed', 'false') == 'true'
        hoje = timezone.localdate()
        dias = defaultdict(list)

        comps = (
            Compromisso.objects.exclude(status='cancelado')
            .select_related('cidade')
            .filter(cidade__isnull=False, data_hora_inicio__isnull=False)
        )
        for c in comps:
            st = _stop_from_compromisso(c, 0, False)
            if st:
                st['kind'] = 'compromisso'
                dias[timezone.localtime(c.data_hora_inicio).date()].append(st)

        evs = (
            Evento.objects.exclude(status='descartado')
            .select_related('cidade')
            .filter(cidade__isnull=False, data__isnull=False)
        )
        for e in evs:
            st = _stop_from_evento(e)
            if st:
                st['kind'] = 'evento'
                dias[e.data].append(st)

        roteiros = []
        for d in sorted(dias.keys()):
            if not show_completed and d < hoje:
                continue
            stops = sorted(dias[d], key=lambda s: s['time'] or '99:99:99')
            for i, s in enumerate(stops):
                s['order'] = i
                s['is_origin'] = (i == 0)
            status = 'completed' if d < hoje else 'in_progress' if d == hoje else 'planned'
            roteiros.append({
                'id': f'd{d.isoformat()}',
                'name': f'Dia {d.strftime("%d/%m/%Y")}',
                'date': d.isoformat(),
                'status': status,
                'kind': 'dia',
                'single': len(stops) == 1,
                'stops': stops,
            })
        return Response(roteiros)


class RoteiroOportunidadesAPI(APIView):
    """Cidades candidatas a parada extra ao longo de um roteiro: têm voto REAL
    de 2022 (votos_referencia_2022, fonte TSE) mas poucos/nenhum apoiador
    cadastrado — ou seja, voto que existe e ainda não está sendo trabalhado.
    Só dado real (CLAUDE.md §5); a proximidade ao traçado é calculada no front."""
    @method_decorator(cache_page(60 * 15))
    def get(self, request):
        apoiadores = dict(
            Lideranca.objects.apoiadores_aprovados()
            .values('cidade__slug').annotate(t=Count('id'))
            .values_list('cidade__slug', 't')
        )
        out = []
        for c in Cidade.objects.only(
            'slug', 'nome', 'latitude', 'longitude', 'votos_referencia_2022',
            'eleitores', 'geojson',
        ):
            votos = c.votos_referencia_2022 or 0
            if votos <= 0:
                continue
            lat, lng = _coords_cidade(c)
            if not lat or not lng:
                continue
            out.append({
                'slug': c.slug, 'name': c.nome, 'lat': lat, 'lng': lng,
                'votos': votos, 'apoiadores': apoiadores.get(c.slug, 0),
                'eleitores': c.eleitores or 0,
            })
        return Response(out)


class ZoneRankingAPI(APIView):
    """Ranking por zonas eleitorais + estrutura PL + eficiência."""
    @method_decorator(cache_page(60 * 15))
    def get(self, request):
        eleicao_dep = Eleicao.objects.filter(
            ano=2022, tipo=settings.CAMPANHA['TSE_CARGO_BASE'],
        ).first()

        cities = Cidade.objects.select_related('regiao').exclude(zona_eleitoral='')

        # Apoiadores e cabos por cidade
        apoiadores_map = dict(
            Lideranca.objects.apoiadores_aprovados()
            .values('cidade__slug')
            .annotate(total=Count('id'))
            .values_list('cidade__slug', 'total')
        )
        cabos_map = dict(
            Lideranca.objects.filter(papel='cabo').values('cidade__slug')
            .annotate(total=Count('id'))
            .values_list('cidade__slug', 'total')
        )
        # Coordinators by region slug
        coord_regions = set(
            Lideranca.objects.filter(papel='coordenador').values_list('regiao__slug', flat=True)
        )

        # Agrupar cidades por zona
        zone_cities = defaultdict(list)
        for city in cities:
            zone_cities[city.zona_eleitoral].append(city)

        # Ranking do candidato-base por zona. Antes era 1 query por zona (N+1, §12);
        # agora UMA agregação por (zona, candidato) e a posição sai em Python.
        zone_ls_positions = {}
        if eleicao_dep:
            por_zona = defaultdict(list)
            for cv in (
                ResultadoZona.objects
                .filter(eleicao=eleicao_dep)
                .values('zona', 'candidato_nome', 'is_candidato')
                .annotate(total_votos=Sum('votos'))
                .order_by('zona', '-total_votos')
            ):
                por_zona[cv['zona']].append(cv)
            for zone_number in zone_cities.keys():
                for i, cv in enumerate(por_zona.get(zone_number, []), 1):
                    if cv['is_candidato']:
                        zone_ls_positions[zone_number] = i
                        break

            # Fallback para zonas sem is_candidato no ResultadoZona: uma agregação
            # por (zona da cidade, candidato) no ResultadoCandidato (não N+1).
            faltantes = [z for z in zone_cities.keys() if z not in zone_ls_positions]
            if faltantes:
                fb_por_zona = defaultdict(list)
                for cv in (
                    ResultadoCandidato.objects
                    .filter(eleicao=eleicao_dep, cidade__zona_eleitoral__in=faltantes)
                    .values('cidade__zona_eleitoral', 'candidato_nome', 'is_candidato')
                    .annotate(total_votos=Sum('votos'))
                    .order_by('cidade__zona_eleitoral', '-total_votos')
                ):
                    fb_por_zona[cv['cidade__zona_eleitoral']].append(cv)
                for zone_number in faltantes:
                    for i, cv in enumerate(fb_por_zona.get(zone_number, []), 1):
                        if cv['is_candidato']:
                            zone_ls_positions[zone_number] = i
                            break

        zones = []
        city_zone_map = {}

        for zone_number, zone_cities_list in sorted(zone_cities.items()):
            city_infos = []
            zone_ls_votes = 0
            zone_total_voters = 0
            zone_apoiadores = 0
            zone_cabos = 0
            zone_has_coord = False
            zone_has_diretorio = False

            for city in zone_cities_list:
                voters = city.eleitores or 0
                ls_votes = city.votos_referencia_2022 or 0
                zone_total_voters += voters
                zone_ls_votes += ls_votes
                ap = apoiadores_map.get(city.slug, 0)
                cb = cabos_map.get(city.slug, 0)
                zone_apoiadores += ap
                zone_cabos += cb
                if city.regiao.slug in coord_regions:
                    zone_has_coord = True
                if city.presidente_diretorio:
                    zone_has_diretorio = True

                city_infos.append({
                    'slug': city.slug,
                    'name': city.nome,
                    'region': city.regiao.sigla,
                    'region_slug': city.regiao.slug,
                    'ls_votes': ls_votes,
                    'voters': voters,
                    'apoiadores': ap,
                })

            zone_ls_pct = round(zone_ls_votes / max(zone_total_voters, 1) * 100, 2)
            ls_position = zone_ls_positions.get(zone_number, 99)

            if ls_position == 1:
                performance = 'lider'
            elif ls_position <= 3:
                performance = 'competitivo'
            elif ls_position <= 5:
                performance = 'medio'
            elif ls_position < 99:
                performance = 'baixo'
            else:
                performance = 'ausente'

            # Efficiency: votes per apoiador
            efficiency = round(zone_ls_votes / max(zone_apoiadores, 1), 1)

            # PL structure summary for zone
            pl_structure = {
                'apoiadores': zone_apoiadores,
                'cabos': zone_cabos,
                'has_coordinator': zone_has_coord,
                'has_diretorio': zone_has_diretorio,
            }

            # Alertas
            alertas = []
            if performance in ('competitivo', 'lider') and not zone_has_coord:
                alertas.append('competitiva_sem_coordenador')
            if zone_apoiadores > 0 and efficiency > 50:
                alertas.append('alta_eficiencia')
            if zone_apoiadores == 0 and zone_ls_votes > 0:
                alertas.append('votos_sem_estrutura')

            zone_data = {
                'zone_number': zone_number,
                'cities': city_infos,
                'city_slugs': [c['slug'] for c in city_infos],
                'total_votes_2022': zone_ls_votes,
                'total_voters': zone_total_voters,
                'ls_position': ls_position,
                'ls_votes': zone_ls_votes,
                'ls_percentage': zone_ls_pct,
                'performance': performance,
                'city_names': ', '.join(c['name'] for c in city_infos),
                'pl_structure': pl_structure,
                'efficiency': efficiency,
                'alertas': alertas,
            }
            zones.append(zone_data)

            for ci in city_infos:
                city_zone_map[ci['slug']] = {
                    'zone_number': zone_number,
                    'performance': performance,
                    'ls_position': ls_position,
                    'ls_votes': ci['ls_votes'],
                    'ls_percentage': round(ci['ls_votes'] / max(ci['voters'], 1) * 100, 2),
                }

        zones.sort(key=lambda z: z['total_votes_2022'], reverse=True)
        for i, z in enumerate(zones, 1):
            z['ranking'] = i

        # Efficiency ranking (separate sort)
        zones_with_apoiadores = [z for z in zones if z['pl_structure']['apoiadores'] > 0]
        zones_with_apoiadores.sort(key=lambda z: z['efficiency'], reverse=True)
        for i, z in enumerate(zones_with_apoiadores, 1):
            z['efficiency_ranking'] = i

        return Response({
            'total_zones': len(zones),
            'zones': zones,
            'city_zone_map': city_zone_map,
        })


class VoteTransferAPI(APIView):
    """Carona de chapa — redutos dos aliados cruzados com a agenda e o LS."""
    @method_decorator(cache_page(60))  # cache curto: reflete toggles de aliado e agenda
    def get(self, request):
        cities = (
            Cidade.objects
            .select_related('regiao')
            .exclude(geojson__isnull=True)
            .order_by('nome')
        )

        # Aliados de chapa ATIVOS (selecionáveis no admin) e seus votos de 2022
        from mapa.models import AliadoChapa
        aliados_obj = list(AliadoChapa.objects.filter(ativo=True))
        aliados_votes = {a.id: {} for a in aliados_obj}
        for a in aliados_obj:
            qs = ResultadoCandidato.objects.filter(eleicao__ano=2022).select_related('cidade')
            if a.candidato_numero:
                # casamento exato por número da urna (+ cargo, pois números repetem entre cargos)
                qs = qs.filter(candidato_numero=a.candidato_numero)
                if a.cargo_2022:
                    qs = qs.filter(eleicao__tipo=a.cargo_2022)
            else:
                # fallback: termos no nome (cadastros antigos sem número)
                for t in [t for t in a.termos_busca.upper().split() if t]:
                    qs = qs.filter(candidato_nome__icontains=t)
            for r in qs:
                slug = r.cidade.slug
                cur = aliados_votes[a.id].get(slug)
                if not cur or r.votos > cur['votes']:
                    aliados_votes[a.id][slug] = {'votes': r.votos, 'pct': float(r.percentual)}
        avg_aliado = {}
        for a in aliados_obj:
            vals = [v['pct'] for v in aliados_votes[a.id].values() if v['pct']]
            avg_aliado[a.id] = sum(vals) / len(vals) if vals else 0

        # Deputados aliados eleitos por cidade (best dep + total)
        allied_dep_map = {}
        dep_elections = Eleicao.objects.filter(
            ano=2022, tipo__in=['deputado_estadual', 'deputado_federal'],
        )
        for eleicao in dep_elections:
            results = (
                ResultadoCandidato.objects
                .filter(eleicao=eleicao, eleito=True, partido__in=ALLIED_PARTIES)
                .select_related('cidade')
            )
            for r in results:
                if r.votos > 0:
                    slug = r.cidade.slug
                    if slug not in allied_dep_map:
                        allied_dep_map[slug] = {'best_name': '', 'best_pct': 0, 'total_votes': 0, 'count': 0}
                    allied_dep_map[slug]['total_votes'] += r.votos
                    allied_dep_map[slug]['count'] += 1
                    if float(r.percentual) > allied_dep_map[slug]['best_pct']:
                        allied_dep_map[slug]['best_name'] = r.candidato_nome
                        allied_dep_map[slug]['best_pct'] = float(r.percentual)

        # IBGE indicators
        indicadores = {
            ind.cidade_id: ind
            for ind in IndicadorMunicipal.objects.all().order_by('-ano_referencia')
        }
        # Index city_id -> slug for indicator lookup
        city_id_slug = {}

        city_data = {}
        for city in cities:
            city_id_slug[city.id] = city.slug
            geo = city.geojson
            if not geo or 'coordinates' not in geo:
                continue

            # Usar lat/lng se disponível
            lat = city.latitude
            lng = city.longitude
            if not lat or not lng:
                coords = geo['coordinates']
                ring = coords[0] if geo['type'] == 'Polygon' else (coords[0][0] if coords else [])
                if not ring:
                    continue
                lng = sum(p[0] for p in ring) / len(ring)
                lat = sum(p[1] for p in ring) / len(ring)

            voters = city.eleitores or 0
            votes = city.votos_referencia_2022 or 0
            penetration = (votes / voters * 100) if voters > 0 else 0

            dep = allied_dep_map.get(city.slug)

            entry = {
                'slug': city.slug,
                'name': city.nome,
                'region_name': city.regiao.sigla,
                'region_slug': city.regiao.slug,
                'cx': lng, 'cy': lat,
                'voters': voters,
                'votes': votes,
                'penetration': round(penetration, 2),
                'meta': city.meta_votos or 0,
                'population': city.populacao or 0,
                'aliados': [{
                    'id': a.id, 'nome': a.nome, 'cor': a.cor, 'cargo': a.cargo_2026,
                    'votes': aliados_votes[a.id].get(city.slug, {}).get('votes', 0),
                    'pct': aliados_votes[a.id].get(city.slug, {}).get('pct', 0),
                } for a in aliados_obj],
            }

            # Allied deputies
            if dep:
                entry['dep_aliado'] = dep['best_name']
                entry['dep_aliado_pct'] = dep['best_pct']
                entry['dep_aliados_count'] = dep['count']
                entry['has_dep_aliado'] = True
            else:
                entry['has_dep_aliado'] = False

            # Socioeconomic profile tag
            ind = indicadores.get(city.id)
            if ind and ind.populacao > 0:
                pop = ind.populacao
                renda = float(ind.renda_per_capita)
                bf_pct = ind.familias_bolsa_familia / pop * 100
                rural_pct = (ind.populacao_rural / pop * 100) if ind.populacao_rural else 0
                mei_pct = ind.meis_ativos / pop * 100
                entry['perfil_socioeconomico'] = {
                    'renda': renda,
                    'bf_pct': round(bf_pct, 2),
                    'rural_pct': round(rural_pct, 1),
                    'mei_pct': round(mei_pct, 2),
                }
                # Discourse tag
                if renda > 1500 and mei_pct > 3:
                    entry['discurso_sugerido'] = 'economico'
                elif rural_pct > 40:
                    entry['discurso_sugerido'] = 'agro'
                elif bf_pct > 10:
                    entry['discurso_sugerido'] = 'social'
                else:
                    entry['discurso_sugerido'] = 'geral'

            city_data[city.slug] = entry

        all_pens = [c['penetration'] for c in city_data.values() if c['voters'] > 0]
        avg_pen = sum(all_pens) / len(all_pens) if all_pens else 0

        def dist_km(c1, c2):
            dx = (c1['cx'] - c2['cx']) * 111 * math.cos(math.radians((c1['cy'] + c2['cy']) / 2))
            dy = (c1['cy'] - c2['cy']) * 111
            return math.sqrt(dx * dx + dy * dy)

        MAX_DIST = 50
        MIN_SOURCE_PEN = avg_pen
        opportunities = []
        slugs = list(city_data.keys())

        for src_slug in slugs:
            src = city_data[src_slug]
            if src['penetration'] < MIN_SOURCE_PEN or src['voters'] < 100:
                continue
            for tgt_slug in slugs:
                if src_slug == tgt_slug:
                    continue
                tgt = city_data[tgt_slug]
                if tgt['penetration'] >= src['penetration'] or tgt['voters'] < 100:
                    continue
                d = dist_km(src, tgt)
                if d > MAX_DIST:
                    continue
                pen_diff = src['penetration'] - tgt['penetration']
                potential_votes = round(pen_diff / 100 * tgt['voters'])
                if potential_votes < 10:
                    continue
                proximity_factor = max(0, 1 - d / MAX_DIST)
                score = round(min(
                    (pen_diff * 10) * 0.4 + (potential_votes / 50) * 0.3 + proximity_factor * 100 * 0.3,
                    100
                ))
                priority = 'alta' if score >= 60 else 'media'
                opportunities.append({
                    'source': {
                        'slug': src['slug'], 'name': src['name'],
                        'region': src['region_name'],
                        'penetration': src['penetration'], 'votes': src['votes'],
                        'cx': src['cx'], 'cy': src['cy'],
                    },
                    'target': {
                        'slug': tgt['slug'], 'name': tgt['name'],
                        'region': tgt['region_name'],
                        'penetration': tgt['penetration'], 'votes': tgt['votes'],
                        'voters': tgt['voters'],
                        'cx': tgt['cx'], 'cy': tgt['cy'],
                    },
                    'distance_km': round(d, 1),
                    'pen_diff': round(pen_diff, 2),
                    'potential_votes': potential_votes,
                    'score': score,
                    'priority': priority,
                })

        opportunities.sort(key=lambda o: o['score'], reverse=True)
        opportunities = opportunities[:200]

        # Classificação de cidades em 6 classes
        # Presença de aliados na agenda REAL (compromissos + eventos futuros com
        # aliado de chapa marcado) — fonte única, sem agenda paralela.
        from agenda.models import Compromisso as _Comp, Evento as _Ev
        agenda_por_cidade = defaultdict(list)
        hoje = timezone.localdate()
        agora = timezone.now()
        for comp in (_Comp.objects.filter(data_hora_inicio__gte=agora)
                     .exclude(status='cancelado')
                     .prefetch_related('aliados').select_related('cidade')):
            for a in comp.aliados.all():
                agenda_por_cidade[comp.cidade.slug].append({
                    'aliado': a.nome, 'cor': a.cor,
                    'data': timezone.localtime(comp.data_hora_inicio).strftime('%d/%m'),
                    'titulo': comp.titulo, 'tipo': 'compromisso',
                })
        for ev in (_Ev.objects.filter(data__gte=hoje)
                   .exclude(status='descartado')
                   .prefetch_related('aliados').select_related('cidade')):
            for a in ev.aliados.all():
                agenda_por_cidade[ev.cidade.slug].append({
                    'aliado': a.nome, 'cor': a.cor,
                    'data': ev.data.strftime('%d/%m'),
                    'titulo': ev.nome, 'tipo': 'evento',
                })

        cities_list = []
        for c in city_data.values():
            ls_pen = c['penetration']
            ls_forte = ls_pen >= avg_pen

            # aliados fortes nesta cidade (acima da média do próprio aliado)
            fortes = [a for a in c['aliados']
                      if a['pct'] > 0 and avg_aliado.get(a['id'], 0) > 0
                      and a['pct'] >= avg_aliado[a['id']]]
            n_fortes = len(fortes)
            votos_carona = sum(a['votes'] for a in fortes)   # base transferível (votos do aliado)

            agenda = agenda_por_cidade.get(c['slug'], [])
            if n_fortes >= 2:
                opp_class = 'palanque_conjunto'
            elif n_fortes == 1:
                opp_class = 'reduto_aliado'
            elif ls_forte:
                opp_class = 'polo_ls'
            else:
                opp_class = 'sem_carona'
            nivel = min(n_fortes, 3)

            if ls_pen >= avg_pen * 1.5:
                level = 'polo'
            elif ls_forte:
                level = 'acima'
            elif ls_pen > 0:
                level = 'abaixo'
            else:
                level = 'zero'

            cities_list.append({
                **c, 'level': level, 'opp_class': opp_class, 'nivel': nivel,
                'aliados_fortes': [a['nome'] for a in fortes],
                'votos_carona': votos_carona,
                'ls_forte': ls_forte,
                'agenda_aliados': agenda,
                'palanque_pronto': bool(agenda) and n_fortes >= 1,
            })

        return Response({
            'avg_penetration': round(avg_pen, 2),
            'aliados': [{'id': a.id, 'nome': a.nome, 'cargo': a.cargo_2026, 'cor': a.cor}
                        for a in aliados_obj],
            'summary': {
                'palanque_conjunto': sum(1 for c in cities_list if c['opp_class'] == 'palanque_conjunto'),
                'reduto_aliado': sum(1 for c in cities_list if c['opp_class'] == 'reduto_aliado'),
                'polo_ls': sum(1 for c in cities_list if c['opp_class'] == 'polo_ls'),
                'sem_carona': sum(1 for c in cities_list if c['opp_class'] == 'sem_carona'),
                'palanques_prontos': sum(1 for c in cities_list if c['palanque_pronto']),
                'votos_carona_total': sum(c['votos_carona'] for c in cities_list),
            },
            'total_opportunities': len(opportunities),
            'total_potential_votes': sum(o['potential_votes'] for o in opportunities),
            'opportunities': opportunities,
            'cities': cities_list,
        })


class Elections2022API(APIView):
    """Dados eleitorais 2022 por cidade com posição do candidato (cargo-base)."""
    @method_decorator(cache_page(60 * 60 * 24))  # dados eleitorais 2022 são estáticos
    def get(self, request):
        eleicao = Eleicao.objects.filter(
            ano=2022, tipo=settings.CAMPANHA['TSE_CARGO_BASE'],
        ).first()

        if not eleicao:
            return Response({'summary': {}, 'perf_summary': {}, 'cities': [], 'zones': []})

        # Ranking por cidade em UMA passada no banco (funções de janela): posição
        # do candidato-base, total de concorrentes e 1º colocado saem calculados no
        # Postgres; só ~295 linhas (uma por cidade) voltam ao Python (pico ~0,2MB).
        # Substitui o .iterator()+groupby anterior, que dependia de server-side
        # cursor — este QUEBRA atrás do pooler do Railway (transaction mode) e
        # derrubava o endpoint em prod (500); a alternativa sem cursor carregava os
        # ~171k resultados de uma vez (pico ~142MB → OOM). A janela resolve ambos.
        sql_ranking = """
            SELECT c.slug, c.nome, r.sigla, r.slug, c.eleitores,
                   t.votos, t.pct, t.posicao, t.total, t.first_name, t.first_votes
            FROM (
              SELECT rc.cidade_id AS cid, rc.votos AS votos, rc.percentual AS pct,
                     rc.is_candidato AS is_cand,
                     ROW_NUMBER() OVER (PARTITION BY rc.cidade_id ORDER BY rc.votos DESC) AS posicao,
                     COUNT(*)     OVER (PARTITION BY rc.cidade_id) AS total,
                     FIRST_VALUE(rc.candidato_nome)
                        OVER (PARTITION BY rc.cidade_id ORDER BY rc.votos DESC) AS first_name,
                     MAX(rc.votos) OVER (PARTITION BY rc.cidade_id) AS first_votes
              FROM mapa_resultadocandidato rc
              WHERE rc.eleicao_id = %s
            ) t
            JOIN liderancas_cidade c ON c.id = t.cid
            LEFT JOIN liderancas_regiao r ON r.id = c.regiao_id
            WHERE t.is_cand
            ORDER BY t.posicao
        """
        with connection.cursor() as cur:
            cur.execute(sql_ranking, [eleicao.id])
            rows = cur.fetchall()

        cities = []
        total_ls_votes = 0
        positions = []

        for (slug, nome, sigla, region_slug, eleitores,
             ls_votes, ls_pct, ls_pos, total_cand, first_name, first_votes) in rows:
            ls_votes = ls_votes or 0
            ls_pct = float(ls_pct or 0)
            total_ls_votes += ls_votes
            positions.append(ls_pos)

            if ls_pos == 1:
                perf = 'primeiro'
            elif ls_pos <= 3:
                perf = 'top3'
            elif ls_pos <= 5:
                perf = 'top5'
            elif ls_pos <= 10:
                perf = 'top10'
            else:
                perf = 'abaixo'

            cities.append({
                'slug': slug,
                'name': nome,
                'region': sigla,
                'region_slug': region_slug,
                'voters': eleitores or 0,
                'ls_votes': ls_votes,
                'ls_position': ls_pos,
                'ls_pct': ls_pct,
                'total_candidates': total_cand,
                # Percentil da candidata na cidade: posição relativa ao total de
                # concorrentes (1º de 400 = top 0,25%). Comparável entre cidades de
                # portes diferentes, ao contrário da posição absoluta. Badge CONTA.
                'percentil': round(ls_pos / total_cand * 100, 1) if total_cand else None,
                'first_name': first_name,
                'first_votes': first_votes or 0,
                'performance': perf,
            })

        cities.sort(key=lambda c: c['ls_position'])

        # Zonas — resumo
        zone_agg = (
            ResultadoZona.objects
            .filter(
                eleicao=eleicao,
                is_candidato=True,
            )
            .values('zona')
            .annotate(total_votes=Sum('votos'))
            .order_by('-total_votes')
        )
        zones = [
            {'zone_number': z['zona'], 'votes': z['total_votes']}
            for z in zone_agg
        ]

        # Posição da candidata no conjunto das cidades.
        # A média aritmética simples de posições é distorcida por outliers e ignora
        # o porte das cidades (3º numa capital ≠ 3º num vilarejo). Expomos duas
        # medidas robustas — ambas são CONTA (derivadas de FATOs do TSE):
        #   • mediana — robusta a outliers;
        #   • média ponderada pelo eleitorado — onde há mais eleitores pesa mais.
        avg_pos = round(sum(positions) / len(positions), 1) if positions else 0  # legado

        if positions:
            ordenadas = sorted(positions)
            n = len(ordenadas)
            meio = n // 2
            median_pos = (
                ordenadas[meio] if n % 2
                else round((ordenadas[meio - 1] + ordenadas[meio]) / 2, 1)
            )
            peso_total = sum(c['voters'] for c in cities)
            weighted_pos = (
                round(sum(c['ls_position'] * c['voters'] for c in cities) / peso_total, 1)
                if peso_total else avg_pos
            )
        else:
            median_pos = 0
            weighted_pos = 0

        perf_summary = {
            'primeiro': sum(1 for c in cities if c['performance'] == 'primeiro'),
            'top3': sum(1 for c in cities if c['performance'] == 'top3'),
            'top5': sum(1 for c in cities if c['performance'] == 'top5'),
            'top10': sum(1 for c in cities if c['performance'] == 'top10'),
            'abaixo': sum(1 for c in cities if c['performance'] == 'abaixo'),
        }

        return Response({
            'summary': {
                'total_cities': len(cities),
                'total_ls_votes': total_ls_votes,
                'avg_position': avg_pos,
                'median_position': median_pos,
                'weighted_position': weighted_pos,
                'total_zones': len(zones),
            },
            'perf_summary': perf_summary,
            'cities': cities,
            'zones': zones,
        })


class NeighborDeputiesAPI(APIView):
    """Deputados aliados — classificação + competição + agenda/visitas."""
    @method_decorator(cache_page(60 * 15))
    def get(self, request):
        # Buscar deputados estaduais e federais aliados (PL e partidos aliados)
        dep_elections = Eleicao.objects.filter(
            ano=2022, tipo__in=['deputado_estadual', 'deputado_federal'],
        )

        # Coletar votos dos deputados aliados por cidade
        allied_dep_votes = defaultdict(list)  # city_slug -> [{name, votes, pct, party}]

        for eleicao in dep_elections:
            results = (
                ResultadoCandidato.objects
                .filter(
                    eleicao=eleicao,
                    eleito=True,
                    partido__in=['PL', 'PP', 'REPUBLICANOS', 'UNIÃO BRASIL', 'UNIÃO'],
                )
                .select_related('cidade')
            )
            for r in results:
                if r.votos > 0:
                    allied_dep_votes[r.cidade.slug].append({
                        'name': r.candidato_nome,
                        'votes': r.votos,
                        'pct': float(r.percentual),
                        'party': r.partido,
                    })

        # Top adversary candidates per city (strongest non-allied)
        adversary_top = defaultdict(list)
        for eleicao in dep_elections:
            results = (
                ResultadoCandidato.objects
                .filter(eleicao=eleicao, eleito=True)
                .exclude(partido__in=ALLIED_PARTIES)
                .select_related('cidade')
            )
            for r in results:
                if r.votos > 0:
                    adversary_top[r.cidade.slug].append({
                        'name': r.candidato_nome,
                        'votes': r.votos,
                        'pct': float(r.percentual),
                        'party': r.partido,
                    })

        # Compromissos (visits) per city
        visits_map = dict(
            Compromisso.objects.values('cidade__slug')
            .annotate(total=Count('id'))
            .values_list('cidade__slug', 'total')
        )
        # Upcoming visits
        today = timezone.now().date()
        upcoming_visits = dict(
            Compromisso.objects.filter(data_hora_inicio__date__gte=today)
            .values('cidade__slug')
            .annotate(total=Count('id'))
            .values_list('cidade__slug', 'total')
        )

        cities = Cidade.objects.select_related('regiao').order_by('nome')
        cities_list = []

        for city in cities:
            ls_votes = city.votos_referencia_2022 or 0
            voters = city.eleitores or 0
            ls_pct = round(ls_votes / max(voters, 1) * 100, 2)

            deps = allied_dep_votes.get(city.slug, [])
            deps.sort(key=lambda d: d['votes'], reverse=True)

            best_dep_name = deps[0]['name'] if deps else ''
            best_dep_pct = deps[0]['pct'] if deps else 0
            top3_deps = deps[:3]

            total_dep_votes = sum(d['votes'] for d in deps)
            has_strong_dep = any(d['pct'] >= 10 for d in deps)
            ls_strong = ls_pct >= 1.0

            if ls_strong and has_strong_dep and total_dep_votes > 0:
                if best_dep_pct >= 15:
                    classification = 'ponte_forte'
                else:
                    classification = 'base_conjunta'
            elif has_strong_dep and not ls_strong:
                classification = 'territorio_dep'
            elif ls_strong and not has_strong_dep:
                classification = 'territorio_ls'
            else:
                classification = 'sem_presenca'

            # Adversary competition
            advs = adversary_top.get(city.slug, [])
            advs.sort(key=lambda d: d['votes'], reverse=True)
            top_adversary = advs[0] if advs else None

            # Visits
            total_visits = visits_map.get(city.slug, 0)
            future_visits = upcoming_visits.get(city.slug, 0)

            # Alertas
            alertas = []
            if has_strong_dep and total_visits == 0:
                alertas.append('dep_forte_sem_visita')
            if classification == 'territorio_dep' and total_visits == 0:
                alertas.append('oportunidade_articulacao')
            if top_adversary and top_adversary['pct'] > best_dep_pct and has_strong_dep:
                alertas.append('adversario_mais_forte')

            entry = {
                'slug': city.slug,
                'name': city.nome,
                'region_name': city.regiao.sigla,
                'region_slug': city.regiao.slug,
                'ls_votes': ls_votes,
                'ls_pct': ls_pct,
                'best_dep_name': best_dep_name,
                'best_dep_pct': best_dep_pct,
                'top3_deps': top3_deps,
                'classification': classification,
                'total_visits': total_visits,
                'future_visits': future_visits,
                'alertas': alertas,
            }
            if top_adversary:
                entry['top_adversary'] = top_adversary

            cities_list.append(entry)

        # Summary
        summary = defaultdict(int)
        for c in cities_list:
            summary[c['classification']] += 1

        # Cities with strong dep but no visits
        sem_visita = sum(1 for c in cities_list if 'dep_forte_sem_visita' in c['alertas'])

        return Response({
            'summary': dict(summary),
            'sem_visita_com_dep': sem_visita,
            'cities': cities_list,
        })


class CompeticaoMapAPI(APIView):
    """Concorrência: candidatos 2022, comparação com LS, ranking de ameaça.

    Sem parâmetro -> lista de candidatos com overlap_score (ameaça ao LS).
    Com ?cand=<tipo>::<nome> -> votos por cidade + comparação com LS.
    """
    CARGO_LABELS = {
        'governador': 'Governador',
        'senador': 'Senador',
        'deputado_federal': 'Deputado Federal',
        'deputado_estadual': 'Deputado Estadual',
    }
    CARGO_ORDER = ['governador', 'senador', 'deputado_federal', 'deputado_estadual']

    @method_decorator(cache_page(60 * 60 * 24))  # 24h – dados de 2022 são estáticos
    def get(self, request):
        cand = request.GET.get('cand')
        if cand:
            return self._city_results(cand)
        return self._candidate_list()

    def _candidate_list(self):
        qs = (
            ResultadoCandidato.objects
            .filter(eleicao__ano=2022, eleicao__turno=1, eleicao__tipo__in=self.CARGO_ORDER)
            .values('eleicao__tipo', 'candidato_nome', 'partido')
            .annotate(total=Sum('votos'))
            .order_by('eleicao__tipo', '-total')
        )

        # Votos do candidato por cidade (cargo-base de referência) p/ cálculo de overlap
        ls_by_city = {}
        ls_total = 0
        ls_results = (
            ResultadoCandidato.objects
            .filter(eleicao__ano=2022, eleicao__turno=1,
                    eleicao__tipo=settings.CAMPANHA['TSE_CARGO_BASE'], is_candidato=True)
            .values('cidade__slug', 'votos')
        )
        for r in ls_results:
            ls_by_city[r['cidade__slug']] = r['votos'] or 0
            ls_total += r['votos'] or 0

        # Cargo em disputa em 2026 (config) e o "outro" cargo de deputado —
        # generaliza o caso cruzado: base histórica pode ser federal e a disputa
        # estadual (ou vice-versa) sem tocar em código (Fase 2 passo 3).
        cargo_2026 = settings.CAMPANHA['TSE_CARGO_2026']
        cargo_alt = ('deputado_estadual' if cargo_2026 == 'deputado_federal'
                     else 'deputado_federal')

        # Overlap simples para o cargo de deputado que NÃO está em disputa
        # (contexto de comparação, não ameaça direta)
        alt_overlap = {}
        alt_results = (
            ResultadoCandidato.objects
            .filter(eleicao__ano=2022, eleicao__turno=1, eleicao__tipo=cargo_alt)
            .exclude(is_candidato=True)
            .values('candidato_nome', 'cidade__slug', 'votos')
        )
        cand_cities = defaultdict(dict)
        for r in alt_results:
            cand_cities[r['candidato_nome']][r['cidade__slug']] = r['votos'] or 0

        for cand_name, cities_votes in cand_cities.items():
            # Overlap = sum of min(LS_votes, cand_votes) in cities where both have votes
            overlap = 0
            shared_cities = 0
            for slug, cand_v in cities_votes.items():
                ls_v = ls_by_city.get(slug, 0)
                if ls_v > 0 and cand_v > 0:
                    overlap += min(ls_v, cand_v)
                    shared_cities += 1
            alt_overlap[cand_name] = {
                'overlap_votes': overlap,
                'overlap_pct': round(overlap / max(ls_total, 1) * 100, 1),
                'shared_cities': shared_cities,
            }

        # Overlap dos candidatos ao CARGO EM DISPUTA (rivais reais de 2026) vs
        # base do candidato (TSE_CARGO_BASE), PONDERADO pelos redutos: cada
        # cidade pesa pelos votos do candidato ali — onde ele é forte conta mais.
        #   ameaca = Σ[ votos_LS · min(votos_LS, votos_rival) ] / Σ[ votos_LS² ]
        # Usa min() em votos absolutos → candidato pequeno não infla; normalizado
        # para LS-vs-LS = 100% e naturalmente limitado a 0–100%.
        est_overlap = {}
        if ls_total > 0:
            ls_sq = sum(v * v for v in ls_by_city.values()) or 1  # Σ votos_LS²
            est_results = (
                ResultadoCandidato.objects
                .filter(eleicao__ano=2022, eleicao__turno=1, eleicao__tipo=cargo_2026)
                .exclude(is_candidato=True)
                .values('candidato_nome', 'cidade__slug', 'votos')
            )
            est_cities = defaultdict(dict)
            for r in est_results:
                est_cities[r['candidato_nome']][r['cidade__slug']] = r['votos'] or 0
            for name, cv in est_cities.items():
                num = 0.0
                shared = 0
                for slug, rv in cv.items():
                    lv = ls_by_city.get(slug, 0)
                    if lv > 0 and rv > 0:
                        num += lv * min(lv, rv)
                        shared += 1
                est_overlap[name] = {
                    'overlap_pct': round(num / ls_sq * 100, 1),
                    'shared_cities': shared,
                }

        candidatos = []
        for r in qs:
            entry = {
                'key': f"{r['eleicao__tipo']}::{r['candidato_nome']}",
                'nome': r['candidato_nome'],
                'partido': r['partido'],
                'cargo': r['eleicao__tipo'],
                'cargo_label': self.CARGO_LABELS.get(r['eleicao__tipo'], r['eleicao__tipo']),
                'total_votos': r['total'] or 0,
                'is_candidato': settings.CAMPANHA['TSE_TERMO_BUSCA'] in (r['candidato_nome'] or '').upper(),
            }
            if r['eleicao__tipo'] == cargo_2026:
                ov = est_overlap.get(r['candidato_nome'])
                if ov:
                    entry['overlap_pct'] = ov['overlap_pct']
                    entry['shared_cities'] = ov['shared_cities']
            elif r['eleicao__tipo'] == cargo_alt:
                ov = alt_overlap.get(r['candidato_nome'])
                if ov:
                    entry['overlap_votes'] = ov['overlap_votes']
                    entry['overlap_pct'] = ov['overlap_pct']
                    entry['shared_cities'] = ov['shared_cities']
            candidatos.append(entry)

        # Ranking de ameaça por cargo (overlap_pct desc)
        for cargo in (cargo_alt, cargo_2026):
            ranked = [c for c in candidatos if c['cargo'] == cargo and 'overlap_pct' in c]
            ranked.sort(key=lambda c: c['overlap_pct'], reverse=True)
            for i, c in enumerate(ranked, 1):
                c['threat_rank'] = i

        return Response({'candidatos': candidatos})

    def _city_results(self, cand):
        try:
            tipo, nome = cand.split('::', 1)
        except ValueError:
            return Response({'error': 'parâmetro cand inválido'}, status=400)

        qs = (
            ResultadoCandidato.objects
            .filter(eleicao__ano=2022, eleicao__turno=1, eleicao__tipo=tipo, candidato_nome=nome)
            .values('cidade__slug', 'cidade__nome', 'votos', 'percentual')
        )

        # LS votes in same cargo for comparison
        ls_qs = (
            ResultadoCandidato.objects
            .filter(eleicao__ano=2022, eleicao__turno=1, eleicao__tipo=tipo, is_candidato=True)
            .values('cidade__slug', 'votos', 'percentual')
        )
        ls_by_city = {}
        for r in ls_qs:
            ls_by_city[r['cidade__slug']] = {
                'votos': r['votos'] or 0,
                'pct': round(float(r['percentual'] or 0), 2),
            }

        # Base geográfica do candidato (votos do cargo-base 2022) — usada para a
        # lente Defender×Atacar mesmo quando o rival é de outro cargo.
        ls_base = {}
        for r in (ResultadoCandidato.objects
                  .filter(eleicao__ano=2022, eleicao__turno=1,
                          eleicao__tipo=settings.CAMPANHA['TSE_CARGO_BASE'], is_candidato=True)
                  .values('cidade__slug', 'votos')):
            ls_base[r['cidade__slug']] = r['votos'] or 0

        cidades = {}
        max_votos = 0
        total = 0
        for r in qs:
            v = r['votos'] or 0
            slug = r['cidade__slug']
            ls = ls_by_city.get(slug, {})
            entry = {
                'nome': r['cidade__nome'],
                'votos': v,
                'pct': round(float(r['percentual'] or 0), 2),
                'ls_base_votos': ls_base.get(slug, 0),
            }
            # LS comparison (mesmo cargo)
            if ls:
                entry['ls_votos'] = ls['votos']
                entry['ls_pct'] = ls['pct']
                entry['diff_votos'] = v - ls['votos']
                entry['diff_pct'] = round(entry['pct'] - ls['pct'], 2)
            cidades[slug] = entry
            total += v
            max_votos = max(max_votos, v)

        # Cities where candidate beats LS
        cand_wins = sum(1 for c in cidades.values() if c.get('diff_votos', 0) > 0)
        ls_wins = sum(1 for c in cidades.values() if c.get('diff_votos', 0) < 0)

        return Response({
            'candidato': nome,
            'cargo': self.CARGO_LABELS.get(tipo, tipo),
            'cidades': cidades,
            'max_votos': max_votos,
            'total_votos': total,
            'cidades_com_voto': sum(1 for c in cidades.values() if c['votos'] > 0),
            'vs_ls': {
                'cand_wins': cand_wins,
                'ls_wins': ls_wins,
                'has_ls_data': bool(ls_by_city),
            },
        })



class PerfilIdeologicoAPI(APIView):
    """Perfil Ideológico: retorna componentes individuais normalizados por cidade.

    O frontend combina os componentes selecionados pelo usuário em tempo real.
    Componentes eleitorais: votos_gov (governador), votos_gov2t (2o turno), votos_sen (senador)
    Componentes socioeconômicos: pib, renda, bf (bolsa família invertido), meis
    Todos normalizados 0-1 dentro do range de SC.
    """

    DIREITA = {
        'PL', 'NOVO', 'PP', 'REPUBLICANOS', 'UNIÃO', 'UNIÃO BRASIL',
        'PSD', 'PATRIOTA', 'PTB', 'PSC', 'AVANTE', 'PROS',
    }
    ESQUERDA = {
        'PT', 'PSOL', 'PCdoB', 'REDE', 'PV', 'PDT', 'SOLIDARIEDADE',
        'PSB', 'PSTU', 'PCB', 'UP',
    }

    @method_decorator(cache_page(60 * 60 * 24))
    def get(self, request):
        ano = int(request.GET.get('ano', 2022))

        # ── Indicadores socioeconômicos ──
        indicadores = {
            ind.cidade_id: ind
            for ind in IndicadorMunicipal.objects.filter(ano_referencia=ano).select_related('cidade')
        }

        # ── Votos por tipo de eleição ──
        election_types = ['governador', 'senador']
        turnos = {
            'governador': [1, 2],
            'senador': [1],
        }
        # {tipo_turno: {cidade_id: {dir, esq, total}}}
        votes_by_type = {}
        for tipo in election_types:
            for turno in turnos[tipo]:
                key = f'{tipo}_{turno}t'
                qs = (
                    ResultadoCandidato.objects
                    .filter(eleicao__ano=2022, eleicao__turno=turno, eleicao__tipo=tipo)
                    .values('cidade_id', 'cidade__slug', 'cidade__nome', 'partido')
                    .annotate(total=Sum('votos'))
                )
                cv = defaultdict(lambda: {'dir': 0, 'esq': 0, 'total': 0, 'slug': '', 'nome': ''})
                for r in qs:
                    cid = r['cidade_id']
                    cv[cid]['slug'] = r['cidade__slug']
                    cv[cid]['nome'] = r['cidade__nome']
                    v = r['total'] or 0
                    cv[cid]['total'] += v
                    p = (r['partido'] or '').upper()
                    if p in self.DIREITA:
                        cv[cid]['dir'] += v
                    elif p in self.ESQUERDA:
                        cv[cid]['esq'] += v
                if cv:
                    votes_by_type[key] = dict(cv)

        # ── Coletar todas as cidades (union de todas as fontes) ──
        all_city_ids = set()
        city_info = {}  # cid -> {slug, nome}
        for vt in votes_by_type.values():
            for cid, data in vt.items():
                all_city_ids.add(cid)
                city_info[cid] = {'slug': data['slug'], 'nome': data['nome']}

        # ── Calcular componentes normalizados ──
        # Socioeconômicos
        if indicadores:
            vals = list(indicadores.values())
            max_renda = float(max((i.renda_per_capita for i in vals), default=1) or 1)
            max_pib_pop = max(
                (float(i.pib) / i.populacao if i.populacao else 0 for i in vals), default=1
            ) or 1
            max_bf_pct = max(
                (i.familias_bolsa_familia / i.populacao if i.populacao else 0 for i in vals),
                default=1,
            ) or 1
            max_mei_pct = max(
                (i.meis_ativos / i.populacao if i.populacao else 0 for i in vals),
                default=1,
            ) or 1
            # Demográficos
            max_urban_pct = max(
                (i.populacao_urbana / i.populacao if i.populacao else 0 for i in vals),
                default=1,
            ) or 1
            max_idosos_pct = max(
                (i.idosos_60_mais / i.populacao if i.populacao else 0 for i in vals),
                default=1,
            ) or 1
            max_jovens_pct = max(
                (i.jovens_18_29 / i.populacao if i.populacao else 0 for i in vals),
                default=1,
            ) or 1
            max_escolaridade = float(max(
                (i.taxa_alfabetizacao for i in vals), default=1
            ) or 1)

        cidades = {}
        for cid in all_city_ids:
            info = city_info[cid]
            slug = info['slug']
            c = {'nome': info['nome']}

            # Componentes eleitorais (proporção votos direita: 0=esq, 1=dir)
            for vt_key, vt_data in votes_by_type.items():
                cv = vt_data.get(cid)
                if cv and cv['total'] > 0:
                    c[vt_key] = round(cv['dir'] / cv['total'], 4)
                    c[f'{vt_key}_dir'] = cv['dir']
                    c[f'{vt_key}_esq'] = cv['esq']
                    c[f'{vt_key}_total'] = cv['total']

            # Componentes socioeconômicos (normalizados 0-1)
            ind = indicadores.get(cid)
            if ind and ind.populacao > 0:
                pop = ind.populacao
                c['pib'] = round(float(ind.pib) / pop / max_pib_pop, 4)
                c['renda'] = round(float(ind.renda_per_capita) / max_renda, 4)
                c['bf'] = round(1 - (ind.familias_bolsa_familia / pop / max_bf_pct), 4)
                c['meis'] = round(ind.meis_ativos / pop / max_mei_pct, 4)
                c['pib_raw'] = float(ind.pib)
                # PIB per capita real (R$/hab): fonte única em IndicadorMunicipal.
                c['pib_pc'] = round(ind.pib_per_capita)
                c['renda_raw'] = float(ind.renda_per_capita)
                c['bf_raw'] = ind.familias_bolsa_familia
                c['meis_raw'] = ind.meis_ativos
                c['pop'] = pop

                # Demográficos
                if ind.populacao_urbana > 0 or ind.populacao_rural > 0:
                    urban_pct = ind.populacao_urbana / pop
                    c['pop_urbana_pct'] = round(urban_pct / max_urban_pct, 4) if max_urban_pct else 0
                    c['pop_urbana_pct_raw'] = round(urban_pct * 100, 1)

                if ind.idosos_60_mais > 0:
                    idosos_pct = ind.idosos_60_mais / pop
                    c['idosos_pct'] = round(idosos_pct / max_idosos_pct, 4) if max_idosos_pct else 0
                    c['idosos_pct_raw'] = round(idosos_pct * 100, 1)

                if ind.jovens_18_29 > 0:
                    jovens_pct = ind.jovens_18_29 / pop
                    c['jovens_pct'] = round(jovens_pct / max_jovens_pct, 4) if max_jovens_pct else 0
                    c['jovens_pct_raw'] = round(jovens_pct * 100, 1)

                if float(ind.taxa_alfabetizacao) > 0:
                    c['escolaridade'] = round(float(ind.taxa_alfabetizacao) / max_escolaridade, 4) if max_escolaridade else 0
                    c['escolaridade_raw'] = float(ind.taxa_alfabetizacao)

            cidades[slug] = c

        # ── Dados CRM (apoiadores e demandas por cidade) ──
        apoiadores_qs = (
            Lideranca.objects.apoiadores_aprovados()
            .values('cidade__slug')
            .annotate(total=Count('id'))
        )
        apoiadores_map = {r['cidade__slug']: r['total'] for r in apoiadores_qs}

        demandas_qs = (
            Tarefa.objects.all()
            .values('cidade__slug')
            .annotate(total=Count('id'))
        )
        demandas_map = {r['cidade__slug']: r['total'] for r in demandas_qs}

        # ── Classificação estratégica e rede PL por cidade ──
        all_cities = Cidade.objects.select_related('regiao').annotate(
            # distinct: dois Count sobre relações to-many diferentes
            coord_count=Count('regiao__liderancas', filter=Q(regiao__liderancas__papel='coordenador'), distinct=True),
            cabo_count=Count('liderancas', filter=Q(liderancas__papel='cabo'), distinct=True),
        )
        # Médias de estado: Count e Sum em queries separadas (join inflaria os Sum).
        st_apoiadores = Lideranca.objects.apoiadores_aprovados().count()
        st_sums = Cidade.objects.aggregate(
            total_votes=Sum('votos_referencia_2022'), total_voters=Sum('eleitores'),
        )
        st_voters = st_sums['total_voters'] or 0
        avg_pen = ((st_sums['total_votes'] or 0) / st_voters * 100) if st_voters else 0
        st_density = (st_apoiadores / max(st_voters, 1) * 100)

        strategic_map = {}  # slug -> {classification, pl_network_level}
        for ct in all_cities:
            voters = ct.eleitores or 0
            votes = ct.votos_referencia_2022 or 0
            pen = (votes / voters * 100) if voters > 0 else 0
            mayor_p = (ct.prefeito_partido or '').upper().strip()
            if mayor_p in ALLIED_PARTIES:
                al = 'allied'
            elif mayor_p in ADVERSARY_PARTIES:
                al = 'adversary'
            else:
                al = 'neutral'
            good = pen >= avg_pen
            if al == 'allied' and good:
                cls = 'base_forte'
            elif al == 'adversary' and good:
                cls = 'potencial_oculto'
            elif al == 'allied' and not good:
                cls = 'aliado_fraco'
            elif al == 'adversary' and not good:
                cls = 'territorio_hostil'
            else:
                cls = 'potencial_oculto' if good else 'neutro'

            # PL network level
            vp = (ct.num_vereadores_partido / ct.num_vereadores * 100) if ct.num_vereadores else 0
            ap_count = apoiadores_map.get(ct.slug, 0)
            dens = (ap_count / max(voters, 1)) * 100
            pl_raw = round(
                (100 if (ct.coord_count or 0) > 0 else 0) * 0.25
                + min(vp * 2, 100) * 0.25
                + (100 if ct.presidente_diretorio else 0) * 0.20
                + min(dens / max(st_density * 2, 0.01) * 100, 100) * 0.15
                + min((ct.cabo_count or 0) * 25, 100) * 0.15
            )
            if pl_raw >= 60:
                pl_level = 'forte'
            elif pl_raw >= 30:
                pl_level = 'moderada'
            elif pl_raw > 0:
                pl_level = 'fraca'
            else:
                pl_level = 'ausente'

            strategic_map[ct.slug] = {
                'classification': cls,
                'alignment': al,
                'pl_network_level': pl_level,
                'pl_network_score': pl_raw,
                'penetration': round(pen, 2),
            }

        for slug, c in cidades.items():
            c['apoiadores'] = apoiadores_map.get(slug, 0)
            c['demandas'] = demandas_map.get(slug, 0)
            strat = strategic_map.get(slug)
            if strat:
                c['classification'] = strat['classification']
                c['alignment'] = strat['alignment']
                c['pl_network_level'] = strat['pl_network_level']
                c['pl_network_score'] = strat['pl_network_score']
                c['penetration'] = strat['penetration']

        return Response({
            'cidades': cidades,
            'total_cidades': len(cidades),
            'com_indicadores': sum(1 for c in cidades.values() if 'pib' in c),
            'avg_penetration': round(avg_pen, 2),
            'componentes': {
                'eleitorais': [
                    {'key': 'governador_1t', 'label': 'Governador 1º turno', 'disponivel': 'governador_1t' in votes_by_type},
                    {'key': 'governador_2t', 'label': 'Governador 2º turno', 'disponivel': 'governador_2t' in votes_by_type},
                    {'key': 'senador_1t', 'label': 'Senador', 'disponivel': 'senador_1t' in votes_by_type},
                ],
                'socioeconomicos': [
                    {'key': 'pib', 'label': 'PIB per capita', 'disponivel': bool(indicadores)},
                    {'key': 'renda', 'label': 'Renda per capita', 'disponivel': bool(indicadores)},
                    {'key': 'bf', 'label': 'Bolsa Família (menos = mais conservador)', 'disponivel': bool(indicadores)},
                    {'key': 'meis', 'label': 'MEIs ativos', 'disponivel': bool(indicadores)},
                    {'key': 'pop_urbana_pct', 'label': '% Pop. urbana', 'disponivel': bool(indicadores)},
                    {'key': 'idosos_pct', 'label': '% Idosos (60+)', 'disponivel': bool(indicadores)},
                    {'key': 'jovens_pct', 'label': '% Jovens (18-29)', 'disponivel': bool(indicadores)},
                    {'key': 'escolaridade', 'label': 'Escolaridade média', 'disponivel': bool(indicadores)},
                ],
            },
        })


# ─── API: ROTEIROS INTELIGENTES (urgência de visita + painel de ação) ──────

class VisitUrgencyAPI(APIView):
    """Urgência de visita por cidade: contatos com relacionamento vencido
    (Fila) + tempo desde o último compromisso realizado do candidato."""

    def get(self, request):
        from django.db.models import Max
        from liderancas.views import FREQ_PRAZOS
        agora = timezone.now()

        por_cidade = defaultdict(lambda: {'vencidos': 0, 'nunca': 0, 'alta': 0})

        def acumular(qs, campo_cidade):
            for c in qs.annotate(ultima=Max('interacoes__data')):
                prazo = FREQ_PRAZOS.get(c.frequencia_relacionamento, 30)
                dias = (agora - c.ultima).days if c.ultima else None
                if dias is not None and dias <= prazo:
                    continue
                d = por_cidade[getattr(c, campo_cidade)]
                d['vencidos'] += 1
                if dias is None:
                    d['nunca'] += 1
                if c.prioridade == 'alta':
                    d['alta'] += 1

        acumular(Lideranca.objects.filter(papel='cabo'), 'cidade_id')
        acumular(Lideranca.objects.aprovados().filter(papel='apoiador'), 'cidade_id')
        acumular(Lideranca.objects.filter(papel='coordenador'), 'cidade_id')

        realizados = dict(
            Compromisso.objects.filter(status='realizado')
            .values('cidade_id').annotate(m=Max('data_hora_inicio'))
            .values_list('cidade_id', 'm')
        )
        futuros = dict(
            Compromisso.objects.filter(data_hora_inicio__gte=agora)
            .exclude(status='cancelado')
            .values('cidade_id').annotate(n=Count('id'))
            .values_list('cidade_id', 'n')
        )

        cities, regions = {}, {}
        for cid in Cidade.objects.select_related('regiao'):
            d = por_cidade.get(cid.id, {'vencidos': 0, 'nunca': 0, 'alta': 0})
            ultima = realizados.get(cid.id)
            v = d['vencidos']
            if v == 0:
                nivel = 0
            elif v <= 3:
                nivel = 1
            elif v <= 10:
                nivel = 2
            elif v <= 25:
                nivel = 3
            else:
                nivel = 4
            if d['alta'] > 0 and nivel < 4:
                nivel += 1
            cities[cid.slug] = {
                'id': cid.id,
                'name': cid.nome,
                'region_slug': cid.regiao.slug,
                'vencidos': v,
                'nunca': d['nunca'],
                'alta': d['alta'],
                'dias_visita': (agora - ultima).days if ultima else None,
                'proximos': futuros.get(cid.id, 0),
                'nivel': nivel,
                'lat': cid.latitude,
                'lng': cid.longitude,
            }
            r = regions.setdefault(cid.regiao.slug, {'vencidos': 0, 'nivel': 0, 'pior': '', 'pior_v': -1})
            r['vencidos'] += v
            r['nivel'] = max(r['nivel'], nivel)
            if v > r['pior_v']:
                r['pior_v'] = v
                r['pior'] = cid.nome
        return Response({'cities': cities, 'regions': regions})


class CityActionAPI(APIView):
    """Painel de ação de uma cidade no modo Roteiros: vencidos, última visita,
    próximo compromisso e top contatos para visitar."""

    def get(self, request, slug):
        from django.db.models import Max
        from liderancas.views import FREQ_PRAZOS
        agora = timezone.now()
        cid = Cidade.objects.select_related('regiao').filter(slug=slug).first()
        if not cid:
            return Response({'error': 'Cidade não encontrada'}, status=404)

        contatos = []
        fontes = [
            ('coordenador', Lideranca.objects.filter(papel='coordenador', cidade=cid)),
            ('cabo', Lideranca.objects.filter(papel='cabo', cidade=cid)),
            ('apoiador', Lideranca.objects.aprovados().filter(papel='apoiador', cidade=cid)),
        ]
        for tipo, qs in fontes:
            for c in qs.annotate(ultima=Max('interacoes__data')):
                prazo = FREQ_PRAZOS.get(c.frequencia_relacionamento, 30)
                dias = (agora - c.ultima).days if c.ultima else None
                contatos.append({
                    'id': c.pk, 'tipo': tipo, 'nome': c.nome,
                    'telefone': c.telefone, 'prioridade': c.prioridade,
                    'dias': dias,
                    'vencido': dias is None or dias > prazo,
                })

        vencidos = [c for c in contatos if c['vencido']]
        ordem_pr = {'alta': 0, 'media': 1, 'baixa': 2}
        vencidos.sort(key=lambda x: (
            ordem_pr.get(x['prioridade'], 1),
            0 if x['dias'] is None else 1,
            -(x['dias'] or 0),
        ))

        ultima = Compromisso.objects.filter(cidade=cid, status='realizado') \
            .aggregate(m=Max('data_hora_inicio'))['m']
        proximo = Compromisso.objects.filter(cidade=cid, data_hora_inicio__gte=agora) \
            .exclude(status='cancelado').order_by('data_hora_inicio').first()

        return Response({
            'id': cid.id,
            'nome': cid.nome,
            'slug': cid.slug,
            'regiao': cid.regiao.sigla,
            'controle': cid.controle,
            'controle_manual': cid.controle_manual,
            'adversario_nome': cid.adversario_nome,
            'adversario_partido': cid.adversario_partido,
            'lat': cid.latitude,
            'lng': cid.longitude,
            'total_contatos': len(contatos),
            'vencidos': len(vencidos),
            'nunca': sum(1 for c in vencidos if c['dias'] is None),
            'alta': sum(1 for c in vencidos if c['prioridade'] == 'alta'),
            'ultima_visita_dias': (agora - ultima).days if ultima else None,
            'proximo': {
                'titulo': proximo.titulo,
                'data': timezone.localtime(proximo.data_hora_inicio).strftime('%d/%m %H:%M'),
            } if proximo else None,
            'top_vencidos': vencidos[:6],
        })


class CityControlAPI(APIView):
    """Marca o controle político de uma cidade (manual, do painel do mapa)."""
    def post(self, request, slug):
        cid = Cidade.objects.filter(slug=slug).first()
        if not cid:
            return Response({'ok': False, 'error': 'Cidade não encontrada'}, status=404)
        data = request.data  # DRF já parseia o body (acessar request.body quebra após o CSRF)
        controle = data.get('controle', '')
        if controle not in ('', 'aliado', 'neutro', 'disputado', 'adversario'):
            return Response({'ok': False, 'error': 'Controle inválido'}, status=400)
        cid.controle = controle
        cid.controle_manual = bool(controle)   # vazio = volta ao automático
        if controle in ('adversario', 'disputado'):
            cid.adversario_nome = data.get('adversario_nome', cid.adversario_nome)
            cid.adversario_partido = data.get('adversario_partido', cid.adversario_partido)
        else:
            cid.adversario_nome = ''
            cid.adversario_partido = ''
        cid.save(update_fields=['controle', 'controle_manual', 'adversario_nome', 'adversario_partido'])
        from django.core.cache import cache
        cache.clear()   # invalida o cache da análise estratégica
        return Response({'ok': True, 'controle': cid.controle})


class AliadoToggleAPI(APIView):
    """Liga/desliga um aliado de chapa no mapa de Transferência."""
    def post(self, request, pk):
        from mapa.models import AliadoChapa
        a = AliadoChapa.objects.filter(pk=pk).first()
        if not a:
            return Response({'ok': False}, status=404)
        a.ativo = not a.ativo
        a.save(update_fields=['ativo'])
        from django.core.cache import cache
        cache.clear()
        return Response({'ok': True, 'ativo': a.ativo})


def _aliado_dict(a):
    return {
        'id': a.id, 'nome': a.nome, 'termos_busca': a.termos_busca,
        'candidato_numero': a.candidato_numero, 'cargo_2022': a.cargo_2022,
        'partido': a.partido,
        'cargo_2026': a.cargo_2026, 'cor': a.cor, 'ativo': a.ativo, 'ordem': a.ordem,
    }


# Cor sugerida por partido (legenda partidária aproximada)
PARTIDO_COR = {
    'PL': '#1d4ed8', 'PT': '#dc2626', 'PP': '#0ea5e9', 'PSD': '#f59e0b',
    'MDB': '#16a34a', 'REPUBLICANOS': '#2563eb', 'PSDB': '#0284c7',
    'PDT': '#b91c1c', 'PODE': '#16a34a', 'UNIÃO': '#1e3a8a', 'PSB': '#ea580c',
    'NOVO': '#ea580c', 'PSOL': '#7c3aed', 'CIDADANIA': '#db2777',
}
CARGO_2026_SUGESTAO = {
    'governador': 'Governador', 'senador': 'Senador',
    'deputado_federal': 'Dep. Federal', 'deputado_estadual': 'Dep. Estadual',
}


class Candidatos2022API(APIView):
    """Lista candidatos de 2022 por cargo (agregado estadual) para o seletor de aliados.

    ?cargo=governador|senador|deputado_federal|deputado_estadual
    ?q=termo (filtro por nome, mínimo 2 letras para deputados)
    """
    def get(self, request):
        cargo = (request.query_params.get('cargo') or '').strip()
        q = (request.query_params.get('q') or '').strip().upper()
        if cargo not in CARGO_2026_SUGESTAO:
            return Response({'candidatos': []})
        qs = ResultadoCandidato.objects.filter(eleicao__ano=2022, eleicao__tipo=cargo)
        if q:
            qs = qs.filter(candidato_nome__icontains=q)
        agg = (qs.values('candidato_nome', 'candidato_numero', 'partido')
                 .annotate(votos_total=Sum('votos'), eleito=Count('id', filter=Q(eleito=True)))
                 .order_by('-votos_total'))
        limite = 200 if cargo in ('governador', 'senador') else 25
        out = [{
            'nome': r['candidato_nome'], 'numero': r['candidato_numero'] or '',
            'partido': r['partido'] or '', 'votos': r['votos_total'] or 0,
            'eleito': bool(r['eleito']),
            'cor': PARTIDO_COR.get((r['partido'] or '').upper(), '#2563eb'),
            'cargo_2026_sugestao': CARGO_2026_SUGESTAO[cargo],
        } for r in agg[:limite]]
        return Response({'candidatos': out})


class AliadoChapaListCreateAPI(APIView):
    """Lista todos os aliados de chapa (ativos e inativos) e cria novos."""
    def get(self, request):
        from mapa.models import AliadoChapa
        return Response({'aliados': [_aliado_dict(a) for a in AliadoChapa.objects.all()]})

    def post(self, request):
        from mapa.models import AliadoChapa
        d = request.data
        nome = (d.get('nome') or '').strip()
        termos = (d.get('termos_busca') or '').strip()
        if not nome or not termos:
            return Response({'ok': False, 'erro': 'Nome e termos de busca são obrigatórios.'}, status=400)
        a = AliadoChapa.objects.create(
            nome=nome, termos_busca=termos,
            candidato_numero=(d.get('candidato_numero') or '').strip(),
            cargo_2022=(d.get('cargo_2022') or '').strip(),
            partido=(d.get('partido') or '').strip(),
            cargo_2026=(d.get('cargo_2026') or '').strip(),
            cor=(d.get('cor') or '#2563eb').strip(),
            ativo=bool(d.get('ativo', True)),
            ordem=int(d.get('ordem') or 0),
        )
        from django.core.cache import cache
        cache.clear()
        return Response({'ok': True, 'aliado': _aliado_dict(a)}, status=201)


class AliadoChapaDetailAPI(APIView):
    """Edita ou exclui um aliado de chapa."""
    def patch(self, request, pk):
        from mapa.models import AliadoChapa
        a = AliadoChapa.objects.filter(pk=pk).first()
        if not a:
            return Response({'ok': False}, status=404)
        d = request.data
        if 'nome' in d:
            nome = (d.get('nome') or '').strip()
            if not nome:
                return Response({'ok': False, 'erro': 'Nome obrigatório.'}, status=400)
            a.nome = nome
        if 'termos_busca' in d:
            termos = (d.get('termos_busca') or '').strip()
            if not termos:
                return Response({'ok': False, 'erro': 'Termos de busca obrigatórios.'}, status=400)
            a.termos_busca = termos
        if 'candidato_numero' in d:
            a.candidato_numero = (d.get('candidato_numero') or '').strip()
        if 'cargo_2022' in d:
            a.cargo_2022 = (d.get('cargo_2022') or '').strip()
        if 'partido' in d:
            a.partido = (d.get('partido') or '').strip()
        if 'cargo_2026' in d:
            a.cargo_2026 = (d.get('cargo_2026') or '').strip()
        if 'cor' in d:
            a.cor = (d.get('cor') or '#2563eb').strip()
        if 'ativo' in d:
            a.ativo = bool(d.get('ativo'))
        if 'ordem' in d:
            a.ordem = int(d.get('ordem') or 0)
        a.save()
        from django.core.cache import cache
        cache.clear()
        return Response({'ok': True, 'aliado': _aliado_dict(a)})

    def delete(self, request, pk):
        from mapa.models import AliadoChapa
        a = AliadoChapa.objects.filter(pk=pk).first()
        if not a:
            return Response({'ok': False}, status=404)
        a.delete()
        from django.core.cache import cache
        cache.clear()
        return Response({'ok': True})


# ─── API: VITÓRIA 2026 (lacuna de votos + quadrantes + presença CRM) ──────

class VictoryMapAPI(APIView):
    """Tabuleiro de guerra 2026: por cidade, cruza votos 2022 → meta sugerida
    (lacuna), classificação estratégica (celeiro/mina de ouro/etc.) e a
    presença atual da campanha (estrutura CRM + relacionamento vencido).

    Meta sugerida = max(votos_2022 × 1.4, eleitores × 1.2%), arredondada;
    o campo Cidade.meta_votos sobrescreve quando preenchido.
    """

    TARGET_PEN = 0.012   # alvo aspiracional de penetração (1,2% do eleitorado)
    GROWTH = 1.4         # crescimento mínimo sobre a base de 2022
    PEN_FORTE = 1.0      # % penetração para considerar o candidato "forte" na cidade
    PORTE_GRANDE = 12000  # eleitores para considerar a cidade "grande"

    def get(self, request):
        from django.db.models import Max, Count
        from liderancas.views import FREQ_PRAZOS
        agora = timezone.now()

        # Premissas configuráveis (env via settings.CAMPANHA; fallback nas constantes).
        prem = settings.CAMPANHA
        GROWTH = float(prem.get('VITORIA_CRESCIMENTO', self.GROWTH))
        TARGET = float(prem.get('VITORIA_PENETRACAO', self.TARGET_PEN))
        FORTE = float(prem.get('VITORIA_FORTE_PCT', self.PEN_FORTE))
        PORTE = int(prem.get('VITORIA_PORTE_GRANDE', self.PORTE_GRANDE))

        coord_count = dict(
            Lideranca.objects.filter(papel='coordenador').values('cidade')
            .annotate(n=Count('id')).values_list('cidade', 'n')
        )
        cabo_count = dict(
            Lideranca.objects.filter(papel='cabo').values('cidade')
            .annotate(n=Count('id')).values_list('cidade', 'n')
        )
        apoi_count = dict(
            Lideranca.objects.aprovados().filter(papel='apoiador').values('cidade')
            .annotate(n=Count('id')).values_list('cidade', 'n')
        )

        vencidos = defaultdict(int)

        def acumular(qs, campo):
            for c in qs.annotate(ultima=Max('interacoes__data')):
                prazo = FREQ_PRAZOS.get(c.frequencia_relacionamento, 30)
                dias = (agora - c.ultima).days if c.ultima else None
                if dias is None or dias > prazo:
                    vencidos[getattr(c, campo)] += 1

        acumular(Lideranca.objects.filter(papel='cabo'), 'cidade_id')
        acumular(Lideranca.objects.aprovados().filter(papel='apoiador'), 'cidade_id')
        acumular(Lideranca.objects.filter(papel='coordenador'), 'cidade_id')

        cities, regions = {}, {}
        quad_labels = ['celeiro', 'fortaleza', 'mina_ouro', 'marginal']
        quad_count = {q: 0 for q in quad_labels}
        tot_v, tot_meta, tot_gap = 0, 0, 0
        # Totais SÓ das cidades onde o candidato fez votos em 2022 (base real).
        base_v = base_meta = base_gap = base_n = 0
        n_orfa = n_esfriando = 0

        def nivel_gap(g):
            if g <= 20:
                return 0
            if g <= 60:
                return 1
            if g <= 150:
                return 2
            if g <= 400:
                return 3
            return 4

        for cid in Cidade.objects.select_related('regiao'):
            v = cid.votos_referencia_2022 or 0
            elei = cid.eleitores or 0
            meta = cid.meta_votos or int(round(max(v * GROWTH, elei * TARGET) / 10) * 10)
            gap = max(0, meta - v)
            pen = (v / elei * 100) if elei else 0
            forte = pen >= FORTE
            grande = elei >= PORTE
            if forte and grande:
                quad = 'celeiro'
            elif forte:
                quad = 'fortaleza'
            elif grande:
                quad = 'mina_ouro'
            else:
                quad = 'marginal'

            coord = coord_count.get(cid.id, 0)
            cabo = cabo_count.get(cid.id, 0)
            apoi = apoi_count.get(cid.id, 0)
            estrutura = coord + cabo + apoi
            venc = vencidos.get(cid.id, 0)

            alerta = None
            if quad == 'mina_ouro' and estrutura == 0:
                alerta = 'orfa'
                n_orfa += 1
            elif quad in ('celeiro', 'fortaleza') and estrutura > 0 and venc >= estrutura * 0.6:
                alerta = 'esfriando'
                n_esfriando += 1

            cities[cid.slug] = {
                'id': cid.id, 'name': cid.nome, 'region': cid.regiao.sigla,
                'region_slug': cid.regiao.slug, 'eleitores': elei,
                'votos_2022': v, 'meta': meta, 'gap': gap,
                'penetracao': round(pen, 2), 'quadrante': quad,
                'coord': coord, 'cabo': cabo, 'apoi': apoi,
                'estrutura': estrutura, 'vencidos': venc,
                'alerta': alerta, 'nivel': nivel_gap(gap),
                'lat': cid.latitude, 'lng': cid.longitude,
            }
            tot_v += v
            tot_meta += meta
            tot_gap += gap
            if v > 0:                       # base = cidades onde ela fez votos
                base_v += v; base_meta += meta; base_gap += gap; base_n += 1
            quad_count[quad] += 1

            r = regions.setdefault(cid.regiao.slug, {
                'gap': 0, 'meta': 0, 'votos_2022': 0, 'orfas': 0, 'pior': '', 'pior_gap': -1,
            })
            r['gap'] += gap
            r['meta'] += meta
            r['votos_2022'] += v
            if alerta == 'orfa':
                r['orfas'] += 1
            if gap > r['pior_gap']:
                r['pior_gap'] = gap
                r['pior'] = cid.nome

        # nível de cor por região conforme o gap total
        gaps_reg = sorted((r['gap'] for r in regions.values()), reverse=True) or [0]
        max_gap_reg = gaps_reg[0] or 1
        for r in regions.values():
            frac = r['gap'] / max_gap_reg
            r['nivel'] = 4 if frac > 0.66 else 3 if frac > 0.4 else 2 if frac > 0.2 else 1 if frac > 0.05 else 0

        from core.models import Configuracao
        meta_campanha = Configuracao.get().meta_votos or 0

        return Response({
            'summary': {
                'votos_2022': tot_v, 'potencial': tot_meta, 'gap': tot_gap,
                'meta_campanha': meta_campanha,
                'falta_meta': max(0, meta_campanha - tot_v),
                'cidades': len(cities),
            },
            # Total da base real: só cidades onde o candidato fez votos em 2022.
            'totais': {
                'cidades': base_n, 'votos_2022': base_v,
                'potencial': base_meta, 'disponiveis': base_gap,
            },
            'premissas': {
                'crescimento_pct': round((GROWTH - 1) * 100),   # 1,4 → 40
                'penetracao_pct': round(TARGET * 100, 1),        # 0,012 → 1,2
                'porte_grande': PORTE,                            # 12000
                'forte_pct': FORTE,                               # 1,0
            },
            'quadrantes': quad_count,
            'alertas': {'orfas': n_orfa, 'esfriando': n_esfriando},
            'cities': cities,
            'regions': regions,
        })


# ─── API: CAMADAS DO MAPA DE CALOR (multi-métrica + fronteira + divergência) ──

class HeatLayersAPI(APIView):
    """Alimenta o mapa de calor multi-camada: por cidade calcula penetração,
    densidade de apoiadores, lacuna de votos, votos absolutos, esforço de campo,
    doações, a fronteira de expansão (proximidade geográfica à base forte) e a
    divergência entre força de 2022 e estrutura atual."""

    def get(self, request):
        from math import radians, sin, cos, asin, sqrt
        from liderancas.views import FREQ_PRAZOS  # noqa (mantém consistência de prazos)

        # contagens de estrutura/esforço por cidade
        apoi = dict(
            Lideranca.objects.apoiadores_aprovados().values('cidade')
            .annotate(n=Count('id')).values_list('cidade', 'n')
        )
        visitas = dict(
            Compromisso.objects.filter(status='realizado').values('cidade')
            .annotate(n=Count('id')).values_list('cidade', 'n')
        )
        politicos = _politicos_por_cidade()

        TARGET_PEN, GROWTH = 0.012, 1.4
        raw = []
        for cid in Cidade.objects.select_related('regiao'):
            v = cid.votos_referencia_2022 or 0
            elei = cid.eleitores or 0
            pen = (v / elei * 100) if elei else 0
            ap = apoi.get(cid.id, 0)
            dens = (ap / elei * 1000) if elei else 0   # apoiadores por mil eleitores
            meta = cid.meta_votos or int(round(max(v * GROWTH, elei * TARGET_PEN) / 10) * 10)
            gap = max(0, meta - v)
            pol = politicos.get(cid.id, {'prefeito': 0, 'vice': 0, 'vereador': 0,
                                         'presidente': 0, 'votos_maquina': 0, 'meta_transferir': 0})
            raw.append({
                'cid': cid, 'slug': cid.slug, 'name': cid.nome,
                'region_slug': cid.regiao.slug, 'region': cid.regiao.sigla,
                'lat': cid.latitude, 'lng': cid.longitude,
                'eleitores': elei, 'votos_2022': v, 'penetracao': round(pen, 2),
                'apoiadores': ap, 'densidade': round(dens, 2), 'lacuna': gap,
                'absoluto': v, 'esforco': visitas.get(cid.id, 0),
                'forca_politica': _forca_politica(pol),
                'pol_prefeito': pol['prefeito'], 'pol_vice': pol['vice'],
                'pol_vereador': pol['vereador'], 'pol_presidente': pol['presidente'],
                'votos_maquina': pol['votos_maquina'],
                '_pen': pen, '_dens': dens,
            })

        # ── Fronteira de expansão: proximidade a uma cidade-base (pen>=2%) ──
        bases = [r for r in raw if r['_pen'] >= 2.0 and r['lat'] and r['lng']]

        def hav(a, b):
            lat1, lon1, lat2, lon2 = map(radians, [a['lat'], a['lng'], b['lat'], b['lng']])
            d = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
            return 2 * 6371 * asin(sqrt(d))

        for r in raw:
            if r['_pen'] >= 2.0 or not r['lat'] or not r['lng'] or not bases:
                r['fronteira'] = 0
                continue
            dist = min(hav(r, b) for b in bases)
            prox = max(0.0, 1 - dist / 70.0)            # raio de 70 km
            traction = min(r['_pen'] / 1.0, 1.0)        # tração já existente
            size = min(1.0, 0.5 + r['eleitores'] / 30000)
            r['fronteira'] = round(prox * (0.4 + 0.6 * traction) * size * 100)

        # ── Divergência: percentil de estrutura − percentil de penetração ──
        def percentis(chave):
            ordenados = sorted(range(len(raw)), key=lambda i: raw[i][chave])
            pct = [0.0] * len(raw)
            for rank, i in enumerate(ordenados):
                pct[i] = rank / (len(raw) - 1) if len(raw) > 1 else 0
            return pct

        p_pen = percentis('_pen')
        p_dens = percentis('_dens')
        for i, r in enumerate(raw):
            r['divergencia'] = round((p_dens[i] - p_pen[i]) * 100)

        # ── Monta resposta (cidades) e agrega regiões ──
        keep = ['slug', 'name', 'region_slug', 'region', 'lat', 'lng', 'eleitores',
                'votos_2022', 'penetracao', 'apoiadores', 'densidade', 'lacuna',
                'absoluto', 'esforco', 'fronteira', 'divergencia',
                'forca_politica', 'pol_prefeito', 'pol_vice', 'pol_vereador',
                'pol_presidente', 'votos_maquina']
        cities = {r['slug']: {k: r[k] for k in keep} for r in raw}

        regions = {}
        for r in raw:
            rs = r['region_slug']
            g = regions.setdefault(rs, {
                'sigla': r['region'], 'nome': r['cid'].regiao.nome,
                'votos': 0, 'eleitores': 0, 'apoiadores': 0, 'lacuna': 0,
                'esforco': 0, 'fronteira': 0, 'div_sum': 0,
                'forca_politica': 0, 'pol_prefeito': 0, 'pol_vereador': 0,
                'pol_presidente': 0, 'votos_maquina': 0, 'populacao': 0, 'n': 0,
            })
            g['populacao'] += (r['cid'].populacao or 0)
            g['votos'] += r['votos_2022']
            g['eleitores'] += r['eleitores']
            g['apoiadores'] += r['apoiadores']
            g['lacuna'] += r['lacuna']
            g['esforco'] += r['esforco']
            g['fronteira'] = max(g['fronteira'], r['fronteira'])
            g['div_sum'] += r['divergencia']
            g['forca_politica'] += r['forca_politica']
            g['pol_prefeito'] += r['pol_prefeito']
            g['pol_vereador'] += r['pol_vereador']
            g['pol_presidente'] += r['pol_presidente']
            g['votos_maquina'] += r['votos_maquina']
            g['n'] += 1
        for g in regions.values():
            n = g['n'] or 1
            g['penetracao'] = round(g['votos'] / g['eleitores'] * 100, 2) if g['eleitores'] else 0
            g['densidade'] = round(g['apoiadores'] / g['eleitores'] * 1000, 2) if g['eleitores'] else 0
            g['absoluto'] = g['votos']
            g['divergencia'] = round(g['div_sum'] / n)

        return Response({'cities': cities, 'regions': regions})
