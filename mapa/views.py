import math
from collections import defaultdict

from django.db.models import Count, Sum, Q, F, Avg
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.views import APIView
from rest_framework.response import Response

from liderancas.models import (
    Regiao, Cidade, Apoiador, CoordenadorRegional, CaboEleitoral, Bairro,
)
from doacoes.models import Doacao
from tarefas.models import Tarefa
from agenda.models import Compromisso, Roteiro, RoteiroPonto
from usuarios.models import Usuario
from usuarios.views import secao_required
from mapa.models import Eleicao, ResultadoCandidato, ResultadoZona, IndicadorMunicipal

ALLIED_PARTIES = {'PL', 'PP', 'REPUBLICANOS', 'UNIÃO', 'UNIÃO BRASIL'}
ADVERSARY_PARTIES = {'PT', 'PSOL', 'PCdoB', 'REDE', 'PV', 'SOLIDARIEDADE'}


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

class StateMapAPI(APIView):
    """GeoJSON do estado com todas as regiões."""
    def get(self, request):
        regions = Regiao.objects.annotate(
            total_apoiadores=Count(
                'cidades__apoiadores',
                filter=Q(cidades__apoiadores__status='ativo'),
            ),
            total_votos_2022=Sum('cidades__votos_sorgatto_2022'),
            total_eleitores=Sum('cidades__eleitores'),
        )
        features = []
        for r in regions:
            if r.geojson:
                features.append({
                    'type': 'Feature',
                    'properties': {
                        'name': r.sigla,
                        'full_name': r.nome_completo or r.nome,
                        'slug': r.slug,
                        'population': r.populacao,
                        'color': r.cor,
                        'meta_votes': r.meta_votos,
                        'total_apoiadores': r.total_apoiadores,
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
        cities = region.cidades.annotate(
            total_apoiadores=Count(
                'apoiadores', filter=Q(apoiadores__status='ativo'),
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
                        'votes_2022': city.votos_sorgatto_2022,
                        'registered_voters': city.eleitores,
                        'meta_votes': city.meta_votos,
                        'total_apoiadores': city.total_apoiadores,
                        'mayor': city.prefeito_nome,
                    },
                    'geometry': city.geojson,
                })
        return Response({
            'type': 'FeatureCollection',
            'features': features,
            'region': {
                'name': region.sigla,
                'full_name': region.nome_completo or region.nome,
                'population': region.populacao,
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
                    'apoiadores', filter=Q(apoiadores__status='ativo'),
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
                    'votes_2022': city.votos_sorgatto_2022,
                    'registered_voters': city.eleitores,
                    'meta_votes': city.meta_votos,
                    'total_apoiadores': city.total_apoiadores,
                },
                'geometry': city.geojson,
            })
        return Response({'type': 'FeatureCollection', 'features': features})


class HeatmapAPI(APIView):
    """Dados para choropleth baseado em métrica."""
    def get(self, request, metric):
        regions = Regiao.objects.annotate(
            total_apoiadores=Count(
                'cidades__apoiadores',
                filter=Q(cidades__apoiadores__status='ativo'),
            ),
            total_votos_2022=Sum('cidades__votos_sorgatto_2022'),
        )
        data = []
        for r in regions:
            value = 0
            if metric == 'apoiadores':
                value = r.total_apoiadores
            elif metric == 'votes_2022':
                value = r.total_votos_2022 or 0
            elif metric == 'meta_progress':
                if r.meta_votos > 0:
                    value = round((r.total_apoiadores / r.meta_votos) * 100, 2)
            elif metric == 'saturation':
                if r.populacao > 0:
                    value = round((r.total_apoiadores / r.populacao) * 100, 4)
            data.append({
                'slug': r.slug,
                'name': r.sigla,
                'value': value,
            })
        return Response(data)


# ─── API: DASHBOARD ───────────────────────────────────────────────

class DashboardOverviewAPI(APIView):
    def get(self, request):
        ativos = Apoiador.objects.filter(status='ativo')
        total_apoiadores = ativos.count()
        total_coordenadores = CoordenadorRegional.objects.count()
        total_cabos = CaboEleitoral.objects.count()
        total_parceiros = ativos.filter(tipo='empresarial').count()
        total_liderancas = ativos.filter(tipo='politico').count()
        total_empresas = ativos.filter(tipo='empresarial').count()
        total_contatos = total_apoiadores + total_coordenadores + total_cabos

        # Separate queries to avoid JOIN multiplication
        votos_by_region = dict(
            Cidade.objects.values('regiao_id')
            .annotate(total=Sum('votos_sorgatto_2022'))
            .values_list('regiao_id', 'total')
        )
        apoiadores_by_region = dict(
            Apoiador.objects.filter(status='ativo')
            .values('cidade__regiao_id')
            .annotate(total=Count('id'))
            .values_list('cidade__regiao_id', 'total')
        )

        regions = []
        for r in Regiao.objects.select_related('macro_regiao').order_by('nome'):
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
        total_apoiadores = Apoiador.objects.filter(
            cidade__regiao=region, status='ativo',
        ).count()
        total_coordenadores = CoordenadorRegional.objects.filter(regiao=region).count()
        total_cabos = CaboEleitoral.objects.filter(cidade__regiao=region).count()

        cities = region.cidades.annotate(
            total_apoiadores=Count(
                'apoiadores', filter=Q(apoiadores__status='ativo'),
            ),
        )

        return Response({
            'region': {
                'name': region.sigla,
                'full_name': region.nome_completo or region.nome,
                'population': region.populacao,
                'meta_votes': region.meta_votos,
            },
            'total_apoiadores': total_apoiadores,
            'total_coordenadores': total_coordenadores,
            'total_cabos': total_cabos,
            'cities': list(cities.values(
                'nome', 'slug', 'populacao', 'votos_sorgatto_2022',
                'meta_votos', 'total_apoiadores',
            )),
        })


class CityDashboardAPI(APIView):
    def get(self, request, slug):
        city = Cidade.objects.select_related('regiao').get(slug=slug)
        today = timezone.now().date()

        apoiadores_ativos = Apoiador.objects.filter(cidade=city, status='ativo').count()

        # Doações
        doacoes_city = Doacao.objects.filter(cidade=city, status='confirmada')
        total_doacoes = doacoes_city.aggregate(t=Sum('valor'))['t'] or 0

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
                'num_vereadores_pl': city.num_vereadores_pl,
                'pl_executive_president': city.presidente_pl,
                'votes_sorgatto_2022': city.votos_sorgatto_2022,
                'meta_votes': city.meta_votos,
            },
            'total_apoiadores': apoiadores_ativos,
            'total_coordenadores': CoordenadorRegional.objects.filter(regiao=city.regiao).count(),
            'total_cabos': CaboEleitoral.objects.filter(cidade=city).count(),
            'total_doacoes': float(total_doacoes),
            'tarefas_total': tarefas_total,
            'tarefas_concluidas': tarefas_concluidas,
            'tarefas_vencidas': tarefas_vencidas,
            'compromissos': compromissos,
            'strategic': strategic,
        })

    def _build_strategic(self, city, apoiadores_count, today):
        votes_2022 = city.votos_sorgatto_2022 or 0
        meta = city.meta_votos or 0
        voters = city.eleitores or 0
        penetration = round((votes_2022 / voters * 100), 2) if voters > 0 else 0

        state = Cidade.objects.aggregate(
            total_votes=Sum('votos_sorgatto_2022'),
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
        ver_pct = (city.num_vereadores_pl / city.num_vereadores * 100) if city.num_vereadores else 0
        pen_normalized = min(penetration / max(avg_penetration * 2, 0.01) * 100, 100)
        has_structure = 100 if city.presidente_pl else 0
        total_score = round(
            align_score * 0.30 + ver_pct * 0.20 + pen_normalized * 0.35 + has_structure * 0.15
        )

        has_coordinator = CoordenadorRegional.objects.filter(regiao=city.regiao).exists()
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
                'num_vereadores_pl': city.num_vereadores_pl,
                'pl_executive_president': city.presidente_pl or '',
                'has_coordinator': has_coordinator,
            },
        }


class StrategicAnalysisAPI(APIView):
    """Análise estratégica: classificação de cidades."""
    def get(self, request):
        cities = (
            Cidade.objects
            .select_related('regiao')
            .annotate(
                total_apoiadores=Count(
                    'apoiadores', filter=Q(apoiadores__status='ativo'),
                ),
            )
            .order_by('regiao__nome', 'nome')
        )

        totals = Cidade.objects.aggregate(
            total_votes=Sum('votos_sorgatto_2022'),
            total_voters=Sum('eleitores'),
        )
        avg_penetration = 0
        if totals['total_voters']:
            avg_penetration = (totals['total_votes'] or 0) / totals['total_voters'] * 100

        result = []
        summary = {
            'base_forte': 0, 'potencial_oculto': 0,
            'aliado_fraco': 0, 'territorio_hostil': 0, 'neutro': 0,
        }

        for city in cities:
            voters = city.eleitores or 0
            votes = city.votos_sorgatto_2022 or 0
            penetration = (votes / voters * 100) if voters > 0 else 0
            mayor_party = (city.prefeito_partido or '').upper().strip()

            if mayor_party in ALLIED_PARTIES:
                alignment = 'allied'
            elif mayor_party in ADVERSARY_PARTIES:
                alignment = 'adversary'
            else:
                alignment = 'neutral'

            good = penetration >= avg_penetration
            if alignment == 'allied' and good:
                cls = 'base_forte'
            elif alignment == 'adversary' and good:
                cls = 'potencial_oculto'
            elif alignment == 'allied' and not good:
                cls = 'aliado_fraco'
            elif alignment == 'adversary' and not good:
                cls = 'territorio_hostil'
            else:
                cls = 'potencial_oculto' if good else 'neutro'

            align_score = {'allied': 100, 'neutral': 50, 'adversary': 0}[alignment]
            ver_pct = (city.num_vereadores_pl / city.num_vereadores * 100) if city.num_vereadores else 0
            pen_norm = min(penetration / max(avg_penetration * 2, 0.01) * 100, 100)
            has_struct = 100 if city.presidente_pl else 0
            score = round(align_score * 0.30 + ver_pct * 0.20 + pen_norm * 0.35 + has_struct * 0.15)

            summary[cls] += 1

            result.append({
                'slug': city.slug,
                'name': city.nome,
                'region_name': city.regiao.sigla,
                'region_slug': city.regiao.slug,
                'population': city.populacao,
                'registered_voters': voters,
                'mayor_name': city.prefeito_nome or '',
                'mayor_party': city.prefeito_partido or '',
                'num_vereadores': city.num_vereadores or 0,
                'num_vereadores_pl': city.num_vereadores_pl or 0,
                'votes_2022': votes,
                'penetration': round(penetration, 2),
                'classification': cls,
                'alignment': alignment,
                'score': score,
                'apoiadores': city.total_apoiadores,
            })

        return Response({
            'avg_penetration': round(avg_penetration, 2),
            'summary': summary,
            'cities': result,
        })


class PLNetworkAPI(APIView):
    """Força da rede PL por cidade."""
    def get(self, request):
        cities = (
            Cidade.objects
            .select_related('regiao')
            .annotate(
                total_apoiadores=Count(
                    'apoiadores', filter=Q(apoiadores__status='ativo'),
                ),
                coord_count=Count('regiao__coordenadores'),
                cabo_count=Count('cabos_eleitorais'),
            )
            .order_by('regiao__nome', 'nome')
        )

        totals = Cidade.objects.aggregate(
            total_apoiadores=Count('apoiadores', filter=Q(apoiadores__status='ativo')),
            total_voters=Sum('eleitores'),
        )
        state_density = 0
        if totals['total_voters']:
            state_density = (totals['total_apoiadores'] or 0) / totals['total_voters'] * 100

        raw_results = []

        for city in cities:
            voters = city.eleitores or 0

            coord_score = 100 if (city.coord_count or 0) > 0 else 0
            ver_pct = (city.num_vereadores_pl / city.num_vereadores * 100) if city.num_vereadores else 0
            ver_score = min(ver_pct * 2, 100)
            dir_score = 100 if city.presidente_pl else 0
            density = ((city.total_apoiadores or 0) / max(voters, 1)) * 100
            contact_score = min(density / max(state_density * 2, 0.01) * 100, 100)
            cabo_score = min((city.cabo_count or 0) * 25, 100)

            total_score = round(
                coord_score * 0.25
                + ver_score * 0.25
                + dir_score * 0.20
                + contact_score * 0.15
                + cabo_score * 0.15
            )

            raw_results.append({
                'slug': city.slug,
                'name': city.nome,
                'region_name': city.regiao.sigla,
                'region_slug': city.regiao.slug,
                'population': city.populacao,
                'registered_voters': voters,
                'mayor_party': city.prefeito_partido or '',
                'num_vereadores': city.num_vereadores or 0,
                'num_vereadores_pl': city.num_vereadores_pl or 0,
                'has_coordinator': (city.coord_count or 0) > 0,
                'pl_executive_president': city.presidente_pl or '',
                'apoiadores': city.total_apoiadores or 0,
                'cabos': city.cabo_count or 0,
                'raw_score': total_score,
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
            r['score'] = min(score, 100)
            r['level'] = level
            del r['raw_score']
            result.append(r)

        return Response({
            'state_density': round(state_density, 2),
            'summary': levels,
            'cities': result,
        })


class DoacoesMapAPI(APIView):
    """Doações agrupadas por região e cidade para choropleth."""
    def get(self, request):
        # Doações por região
        regions_data = {}
        for r in Regiao.objects.all():
            doacoes = Doacao.objects.filter(
                cidade__regiao=r, status='confirmada',
            )
            agg = doacoes.aggregate(
                total=Sum('valor'),
                count=Count('id'),
            )
            total = float(agg['total'] or 0)

            # Doadores distintos
            doadores = doacoes.values('doador_nome').distinct().count() if total > 0 else 0

            regions_data[r.slug] = {
                'slug': r.slug,
                'name': r.sigla,
                'total': total,
                'count': agg['count'],
                'doadores': doadores,
                'captadores': 0,
                'top_captadores': [],
            }

        # Doações por cidade
        cities_data = {}
        for city in Cidade.objects.all():
            doacoes_city = Doacao.objects.filter(
                cidade=city, status='confirmada',
            )
            agg = doacoes_city.aggregate(total=Sum('valor'), count=Count('id'))
            total = float(agg['total'] or 0)
            if total > 0:
                cities_data[city.slug] = {
                    'total': total,
                    'count': agg['count'],
                    'doadores': doacoes_city.values('doador_nome').distinct().count(),
                }

        # Retornar como array (para compatibilidade com setDoacoes que converte para map)
        result = list(regions_data.values())
        return Response(result)


class DemandasMapAPI(APIView):
    """Demandas/tarefas por região para choropleth."""
    def get(self, request):
        today = timezone.now().date()
        regions = Regiao.objects.annotate(
            total_tarefas=Count(
                'cidades__tarefas',
                filter=Q(cidades__tarefas__excluida_em__isnull=True),
            ),
            tarefas_vencidas=Count(
                'cidades__tarefas',
                filter=Q(
                    cidades__tarefas__excluida_em__isnull=True,
                    cidades__tarefas__prazo__lt=today,
                ) & ~Q(cidades__tarefas__fase='concluida'),
            ),
            tarefas_concluidas=Count(
                'cidades__tarefas',
                filter=Q(
                    cidades__tarefas__excluida_em__isnull=True,
                    cidades__tarefas__fase='concluida',
                ),
            ),
        )
        data = []
        for r in regions:
            total = r.total_tarefas
            vencidas = r.tarefas_vencidas
            concluidas = r.tarefas_concluidas
            abertas = total - concluidas

            if vencidas > 0:
                status = 'overdue'
            elif abertas > 0:
                status = 'ok'
            else:
                status = 'empty'

            data.append({
                'slug': r.slug,
                'name': r.sigla,
                'total': total,
                'active': abertas,
                'overdue': vencidas,
                'completed': concluidas,
                'open': abertas,
                'status': status,
            })
        return Response(data)


class RoteirosMapAPI(APIView):
    """Roteiros/itinerários com lat/lng para cada parada."""
    def get(self, request):
        show_completed = request.GET.get('completed', 'false') == 'true'
        qs = Roteiro.objects.select_related('regiao').prefetch_related(
            'pontos__compromisso__cidade',
        )
        if not show_completed:
            qs = qs.exclude(status='realizado')

        roteiros = []
        for roteiro in qs:
            stops = []
            for ponto in roteiro.pontos.select_related('compromisso__cidade').order_by('ordem'):
                comp = ponto.compromisso
                if not comp or not comp.cidade:
                    continue
                city = comp.cidade

                # Usar lat/lng da cidade se disponível, senão calcular centróide
                lat = city.latitude
                lng = city.longitude
                if not lat or not lng:
                    if city.geojson:
                        geo = city.geojson
                        coords = geo.get('coordinates', [])
                        ring = coords[0] if geo['type'] == 'Polygon' else (coords[0][0] if coords else [])
                        if ring:
                            lng = sum(p[0] for p in ring) / len(ring)
                            lat = sum(p[1] for p in ring) / len(ring)

                if lat and lng:
                    stops.append({
                        'city_name': city.nome,
                        'city_slug': city.slug,
                        'lat': lat,
                        'lng': lng,
                        'date': comp.data_hora_inicio.date().isoformat() if comp.data_hora_inicio else '',
                        'time': comp.data_hora_inicio.strftime('%H:%M:%S') if comp.data_hora_inicio else '',
                        'task_title': comp.titulo or '',
                        'is_overnight': ponto.pernoite if hasattr(ponto, 'pernoite') else False,
                        'is_origin': ponto.ordem == 0,
                        'order': ponto.ordem,
                    })

            if stops:
                # Mapear status do CRM para o que sc-map.js espera
                status_map = {
                    'planejado': 'planned',
                    'confirmado': 'confirmed',
                    'em_andamento': 'in_progress',
                    'realizado': 'completed',
                }
                roteiros.append({
                    'name': roteiro.titulo,
                    'status': status_map.get(roteiro.status, roteiro.status),
                    'stops': stops,
                })

        return Response(roteiros)


class ZoneRankingAPI(APIView):
    """Ranking por zonas eleitorais com dados de ResultadoZona."""
    def get(self, request):
        eleicao_dep = Eleicao.objects.filter(
            ano=2022, tipo='deputado_federal',
        ).first()

        cities = Cidade.objects.select_related('regiao').exclude(zona_eleitoral='')

        # Agrupar cidades por zona
        zone_cities = defaultdict(list)
        for city in cities:
            zone_cities[city.zona_eleitoral].append(city)

        # Se temos resultados por zona, usar para ranking preciso
        zone_ls_positions = {}
        if eleicao_dep:
            for zone_number in zone_cities.keys():
                # Somar votos por candidato nesta zona
                cand_votes = (
                    ResultadoZona.objects
                    .filter(eleicao=eleicao_dep, zona=zone_number)
                    .values('candidato_nome', 'is_sorgatto')
                    .annotate(total_votos=Sum('votos'))
                    .order_by('-total_votos')
                )
                for i, cv in enumerate(cand_votes, 1):
                    if cv['is_sorgatto']:
                        zone_ls_positions[zone_number] = i
                        break
                if zone_number not in zone_ls_positions:
                    # Fallback: usar ResultadoCandidato
                    zone_city_ids = [c.id for c in zone_cities[zone_number]]
                    cand_votes2 = (
                        ResultadoCandidato.objects
                        .filter(eleicao=eleicao_dep, cidade_id__in=zone_city_ids)
                        .values('candidato_nome', 'is_sorgatto')
                        .annotate(total_votos=Sum('votos'))
                        .order_by('-total_votos')
                    )
                    for i, cv in enumerate(cand_votes2, 1):
                        if cv['is_sorgatto']:
                            zone_ls_positions[zone_number] = i
                            break

        zones = []
        city_zone_map = {}

        for zone_number, zone_cities_list in sorted(zone_cities.items()):
            city_infos = []
            zone_ls_votes = 0
            zone_total_voters = 0

            for city in zone_cities_list:
                voters = city.eleitores or 0
                ls_votes = city.votos_sorgatto_2022 or 0
                zone_total_voters += voters
                zone_ls_votes += ls_votes
                city_infos.append({
                    'slug': city.slug,
                    'name': city.nome,
                    'region': city.regiao.sigla,
                    'region_slug': city.regiao.slug,
                    'ls_votes': ls_votes,
                    'voters': voters,
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

        return Response({
            'total_zones': len(zones),
            'zones': zones,
            'city_zone_map': city_zone_map,
        })


class VoteTransferAPI(APIView):
    """Transferência de votos — 6 classes de oportunidade."""
    def get(self, request):
        cities = (
            Cidade.objects
            .select_related('regiao')
            .exclude(geojson__isnull=True)
            .order_by('nome')
        )

        # Buscar votos de Jorginho Melo (governador 2022) e Carol De Toni (dep. federal 2022)
        jorginho_votes = {}
        carol_votes = {}

        gov_election = Eleicao.objects.filter(ano=2022, tipo='governador', turno=1).first()
        if gov_election:
            for r in ResultadoCandidato.objects.filter(eleicao=gov_election).select_related('cidade'):
                name_upper = r.candidato_nome.upper()
                if 'JORGINHO' in name_upper:
                    jorginho_votes[r.cidade.slug] = {
                        'votes': r.votos, 'pct': float(r.percentual),
                    }

        dep_fed_election = Eleicao.objects.filter(ano=2022, tipo='deputado_federal', turno=1).first()
        if dep_fed_election:
            for r in ResultadoCandidato.objects.filter(eleicao=dep_fed_election).select_related('cidade'):
                name_upper = r.candidato_nome.upper()
                if 'CAROL' in name_upper and 'TONI' in name_upper:
                    carol_votes[r.cidade.slug] = {
                        'votes': r.votos, 'pct': float(r.percentual),
                    }

        city_data = {}
        for city in cities:
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
            votes = city.votos_sorgatto_2022 or 0
            penetration = (votes / voters * 100) if voters > 0 else 0

            jv = jorginho_votes.get(city.slug, {})
            cv = carol_votes.get(city.slug, {})

            city_data[city.slug] = {
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
                'jorginho_votes': jv.get('votes'),
                'jorginho_pct': jv.get('pct'),
                'carol_votes': cv.get('votes'),
                'carol_pct': cv.get('pct'),
            }

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
        # Calcular médias de Jorginho e Carol para thresholds relativos
        all_j = [c.get('jorginho_pct') or 0 for c in city_data.values() if c.get('jorginho_pct')]
        all_c = [c.get('carol_pct') or 0 for c in city_data.values() if c.get('carol_pct')]
        avg_j = sum(all_j) / len(all_j) if all_j else 0
        avg_c = sum(all_c) / len(all_c) if all_c else 0

        cities_list = []
        for c in city_data.values():
            ls_pen = c['penetration']
            j_pct = c.get('jorginho_pct') or 0
            c_pct = c.get('carol_pct') or 0

            ls_forte = ls_pen >= avg_pen
            j_forte = j_pct >= avg_j
            c_forte = c_pct >= avg_c

            if ls_forte and j_forte and c_forte:
                opp_class = 'zona_ouro'
            elif ls_forte:
                opp_class = 'polo_ls'
            elif not ls_forte and not j_forte and not c_forte:
                opp_class = 'buscar_ambos'
            elif not ls_forte and j_forte:
                opp_class = 'buscar_jorginho'
            elif not ls_forte and c_forte:
                opp_class = 'buscar_carol'
            else:
                opp_class = 'baixa_prioridade'

            # Level
            if ls_pen >= avg_pen * 1.5:
                level = 'polo'
            elif ls_forte:
                level = 'acima'
            elif ls_pen > 0:
                level = 'abaixo'
            else:
                level = 'zero'

            cities_list.append({**c, 'level': level, 'opp_class': opp_class})

        return Response({
            'avg_penetration': round(avg_pen, 2),
            'avg_jorginho': round(avg_j, 2),
            'avg_carol': round(avg_c, 2),
            'total_opportunities': len(opportunities),
            'total_potential_votes': sum(o['potential_votes'] for o in opportunities),
            'opportunities': opportunities,
            'cities': cities_list,
        })


class Elections2022API(APIView):
    """Dados eleitorais 2022 por cidade com posição de LS (dep. federal)."""
    def get(self, request):
        eleicao = Eleicao.objects.filter(
            ano=2022, tipo='deputado_federal',
        ).first()

        if not eleicao:
            return Response({'summary': {}, 'perf_summary': {}, 'cities': [], 'zones': []})

        # Agrupar todos os resultados por cidade, ordenados por votos
        all_results = (
            ResultadoCandidato.objects
            .filter(eleicao=eleicao)
            .select_related('cidade__regiao')
            .values(
                'cidade__slug', 'cidade__nome', 'cidade__regiao__sigla',
                'cidade__regiao__slug', 'cidade__eleitores',
                'candidato_nome', 'votos', 'percentual', 'is_sorgatto',
            )
            .order_by('cidade__slug', '-votos')
        )

        city_candidates = defaultdict(list)
        for r in all_results:
            city_candidates[r['cidade__slug']].append(r)

        cities = []
        total_ls_votes = 0
        positions = []

        for slug, candidates in city_candidates.items():
            ls_pos = None
            ls_votes = 0
            ls_pct = 0
            first_name = candidates[0]['candidato_nome'] if candidates else ''
            first_votes = candidates[0]['votos'] if candidates else 0

            for i, c in enumerate(candidates, 1):
                if c['is_sorgatto']:
                    ls_pos = i
                    ls_votes = c['votos']
                    ls_pct = float(c['percentual'])
                    break

            if ls_pos is None:
                continue

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

            info = candidates[0]
            cities.append({
                'slug': slug,
                'name': info['cidade__nome'],
                'region': info['cidade__regiao__sigla'],
                'region_slug': info['cidade__regiao__slug'],
                'voters': info['cidade__eleitores'] or 0,
                'ls_votes': ls_votes,
                'ls_position': ls_pos,
                'ls_pct': ls_pct,
                'total_candidates': len(candidates),
                'first_name': first_name,
                'first_votes': first_votes,
                'performance': perf,
            })

        cities.sort(key=lambda c: c['ls_position'])

        # Zonas — resumo
        zone_agg = (
            ResultadoZona.objects
            .filter(
                eleicao=eleicao,
                is_sorgatto=True,
            )
            .values('zona')
            .annotate(total_votes=Sum('votos'))
            .order_by('-total_votes')
        )
        zones = [
            {'zone_number': z['zona'], 'votes': z['total_votes']}
            for z in zone_agg
        ]

        avg_pos = round(sum(positions) / len(positions), 1) if positions else 0

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
                'total_zones': len(zones),
            },
            'perf_summary': perf_summary,
            'cities': cities,
            'zones': zones,
        })


class NeighborDeputiesAPI(APIView):
    """Deputados aliados — classificação baseada em dados reais."""
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

        cities = Cidade.objects.select_related('regiao').order_by('nome')
        cities_list = []

        for city in cities:
            ls_votes = city.votos_sorgatto_2022 or 0
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

            cities_list.append({
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
            })

        # Summary
        summary = defaultdict(int)
        for c in cities_list:
            summary[c['classification']] += 1

        return Response({
            'summary': dict(summary),
            'cities': cities_list,
        })


class CompeticaoMapAPI(APIView):
    """MVP Concorrência: lista candidatos de 2022 e votos por cidade de um candidato.

    Sem parâmetro -> lista de candidatos (governador/senador/dep. federal/estadual).
    Com ?cand=<tipo>::<nome> -> votos por cidade daquele candidato (área de atuação).
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
        candidatos = [
            {
                'key': f"{r['eleicao__tipo']}::{r['candidato_nome']}",
                'nome': r['candidato_nome'],
                'partido': r['partido'],
                'cargo': r['eleicao__tipo'],
                'cargo_label': self.CARGO_LABELS.get(r['eleicao__tipo'], r['eleicao__tipo']),
                'total_votos': r['total'] or 0,
            }
            for r in qs
        ]
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
        cidades = {}
        max_votos = 0
        total = 0
        for r in qs:
            v = r['votos'] or 0
            cidades[r['cidade__slug']] = {
                'nome': r['cidade__nome'],
                'votos': v,
                'pct': round(float(r['percentual'] or 0), 2),
            }
            total += v
            max_votos = max(max_votos, v)

        return Response({
            'candidato': nome,
            'cargo': self.CARGO_LABELS.get(tipo, tipo),
            'cidades': cidades,
            'max_votos': max_votos,
            'total_votos': total,
            'cidades_com_voto': sum(1 for c in cidades.values() if c['votos'] > 0),
        })


class PerfilIdeologicoAPI(APIView):
    """Perfil Ideológico: cruza indicadores socioeconômicos com resultados eleitorais 2022.

    Retorna um índice de alinhamento ideológico por cidade (0=esquerda .. 1=direita).
    score = score_socio * 0.40 + score_eleitoral * 0.60
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

        indicadores = {
            ind.cidade_id: ind
            for ind in IndicadorMunicipal.objects.filter(ano_referencia=ano).select_related('cidade')
        }

        # Votos por partido por cidade (governador 2022 1T como proxy principal)
        votos_qs = (
            ResultadoCandidato.objects
            .filter(eleicao__ano=2022, eleicao__turno=1, eleicao__tipo='governador')
            .values('cidade_id', 'cidade__slug', 'cidade__nome', 'partido')
            .annotate(total=Sum('votos'))
        )

        # Agrupar votos por cidade
        city_votes = defaultdict(lambda: {'dir': 0, 'esq': 0, 'total': 0, 'slug': '', 'nome': ''})
        for r in votos_qs:
            cid = r['cidade_id']
            city_votes[cid]['slug'] = r['cidade__slug']
            city_votes[cid]['nome'] = r['cidade__nome']
            v = r['total'] or 0
            city_votes[cid]['total'] += v
            partido_upper = (r['partido'] or '').upper()
            if partido_upper in self.DIREITA:
                city_votes[cid]['dir'] += v
            elif partido_upper in self.ESQUERDA:
                city_votes[cid]['esq'] += v

        # Calcular scores socioeconômicos normalizados
        if indicadores:
            vals = list(indicadores.values())
            max_renda = max((i.renda_per_capita for i in vals), default=1) or 1
            max_pib_pop = max(
                (i.pib / i.populacao if i.populacao else 0 for i in vals), default=1
            ) or 1
            max_bf_pct = max(
                (i.familias_bolsa_familia / i.populacao if i.populacao else 0 for i in vals),
                default=1,
            ) or 1
            max_mei_pct = max(
                (i.meis_ativos / i.populacao if i.populacao else 0 for i in vals),
                default=1,
            ) or 1

        cidades = {}
        for cid, cv in city_votes.items():
            # Score eleitoral: proporção de votos à direita
            if cv['total'] > 0:
                score_eleitoral = cv['dir'] / cv['total']
            else:
                score_eleitoral = 0.5

            # Score socioeconômico
            ind = indicadores.get(cid)
            if ind and ind.populacao > 0:
                renda_n = float(ind.renda_per_capita) / float(max_renda)
                pib_n = float(ind.pib) / float(ind.populacao) / float(max_pib_pop)
                bf_n = ind.familias_bolsa_familia / ind.populacao / float(max_bf_pct)
                mei_n = ind.meis_ativos / ind.populacao / float(max_mei_pct)
                # Maior renda/PIB/MEI = mais direita, mais BF = mais esquerda
                score_socio = (renda_n * 0.30 + pib_n * 0.25 + mei_n * 0.25 + (1 - bf_n) * 0.20)
            else:
                score_socio = 0.5

            score = score_socio * 0.40 + score_eleitoral * 0.60
            score = round(min(max(score, 0), 1), 4)

            cidades[cv['slug']] = {
                'nome': cv['nome'],
                'score': score,
                'score_socio': round(score_socio, 4),
                'score_eleitoral': round(score_eleitoral, 4),
                'votos_dir': cv['dir'],
                'votos_esq': cv['esq'],
                'votos_total': cv['total'],
                'tem_indicadores': ind is not None,
            }

        return Response({
            'cidades': cidades,
            'total_cidades': len(cidades),
            'com_indicadores': sum(1 for c in cidades.values() if c['tem_indicadores']),
            'legenda': {
                'min_label': 'Esquerda',
                'max_label': 'Direita',
                'cores': ['#E53935', '#FF7043', '#FFD54F', '#66BB6A', '#1565C0'],
            },
        })
