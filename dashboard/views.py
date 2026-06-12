from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth, TruncDate
from django.utils import timezone
from datetime import timedelta
import json

from core.models import Configuracao
from core.services import calcular_scores_rede, score_usuario
from usuarios.models import Usuario
from usuarios.views import secao_required
from liderancas.models import Apoiador, CoordenadorRegional, CaboEleitoral, Regiao, InteracaoLog
from doacoes.models import Doacao
from agenda.models import Compromisso, Evento
from tarefas.models import Tarefa

def home_view(request):
    config = Configuracao.get()
    total_votos = Apoiador.objects.count()
    percentual = round((total_votos / config.meta_votos) * 100, 1) if config.meta_votos > 0 else 0
    faltam = max(0, config.meta_votos - total_votos)

    now = timezone.now()
    hoje = now.date()
    fim_semana = hoje + timedelta(days=7)

    # --- Resumo Financeiro ---
    doacoes_confirmadas = Doacao.objects.filter(status='confirmada')
    total_arrecadado = doacoes_confirmadas.aggregate(t=Sum('valor'))['t'] or 0
    total_liquido = doacoes_confirmadas.aggregate(t=Sum('valor_liquido'))['t'] or 0
    doacoes_pendentes = Doacao.objects.filter(status='pendente')
    pendentes_qtd = doacoes_pendentes.count()
    pendentes_valor = doacoes_pendentes.aggregate(t=Sum('valor'))['t'] or 0

    # --- Agenda da Semana ---
    compromissos_semana = Compromisso.objects.filter(
        data_hora_inicio__date__gte=hoje,
        data_hora_inicio__date__lte=fim_semana,
    ).exclude(status='cancelado').select_related('cidade').order_by('data_hora_inicio')[:8]

    eventos_semana = Evento.objects.filter(
        data__gte=hoje, data__lte=fim_semana,
        status='confirmado',
    ).select_related('cidade').order_by('data')[:5]

    # --- Tarefas ---
    tarefas_abertas = Tarefa.objects.exclude(fase='concluida')
    tarefas_vencidas = tarefas_abertas.filter(prazo__lt=hoje).count()
    tarefas_hoje = tarefas_abertas.filter(prazo=hoje).count()
    tarefas_semana_qs = tarefas_abertas.filter(
        prazo__gte=hoje, prazo__lte=fim_semana,
    ).select_related('responsavel', 'cidade').order_by('prazo', 'prioridade')[:8]

    # --- Atividade Recente ---
    ultimos_apoiadores = Apoiador.objects.select_related(
        'cadastrado_por', 'cidade',
    ).order_by('-created_at')[:5]

    ultimas_doacoes = Doacao.objects.select_related(
        'cidade',
    ).order_by('-criado_em')[:5]

    # --- Placar da Semana (ciclo de relacionamento) ---
    from django.db.models import Max
    from datetime import date
    from liderancas.views import FREQ_PRAZOS
    last_7 = now - timedelta(days=7)
    interacoes_7d = InteracaoLog.objects.filter(data__gte=last_7).count()
    contatos_alcancados_7d = (
        InteracaoLog.objects.filter(data__gte=last_7, coordenador__isnull=False).values('coordenador').distinct().count()
        + InteracaoLog.objects.filter(data__gte=last_7, cabo__isnull=False).values('cabo').distinct().count()
        + InteracaoLog.objects.filter(data__gte=last_7, apoiador__isnull=False).values('apoiador').distinct().count()
    )
    fila_total = 0
    for qs in (CoordenadorRegional.objects.all(), CaboEleitoral.objects.all(), Apoiador.objects.all()):
        for c in qs.annotate(ultima=Max('interacoes__data')):
            prazo = FREQ_PRAZOS.get(c.frequencia_relacionamento, 30)
            dias = (now - c.ultima).days if c.ultima else None
            if dias is None or dias > prazo:
                fila_total += 1
    dias_eleicao = (date(2026, 10, 4) - hoje).days

    # --- Rede ---
    coordenadores_ativos = CoordenadorRegional.objects.count()
    cabos_ativos = CaboEleitoral.objects.count()
    top_regioes = (
        Apoiador.objects.filter(cidade__regiao__isnull=False)
        .values('cidade__regiao__sigla')
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )

    # --- Gráficos ---
    # Captação últimos 7 dias (uma única query agregada por dia)
    inicio_captacao = hoje - timedelta(days=6)
    captacao_por_dia = dict(
        Apoiador.objects.filter(created_at__date__gte=inicio_captacao)
        .annotate(dia=TruncDate('created_at'))
        .values('dia')
        .annotate(total=Count('id'))
        .values_list('dia', 'total')
    )
    dias_captacao = [
        {
            'label': dia.strftime('%d/%m'),
            'count': captacao_por_dia.get(dia, 0),
        }
        for dia in (inicio_captacao + timedelta(days=i) for i in range(7))
    ]
    chart_captacao_labels = json.dumps([d['label'] for d in dias_captacao])
    chart_captacao_data = json.dumps([d['count'] for d in dias_captacao])

    # Arrecadação por mês
    arrec_mes = list(
        doacoes_confirmadas.annotate(mes=TruncMonth('data'))
        .values('mes')
        .annotate(total=Sum('valor'))
        .order_by('mes')
    )
    chart_arrec_labels = json.dumps([m['mes'].strftime('%b/%Y') for m in arrec_mes])
    chart_arrec_data = json.dumps([float(m['total']) for m in arrec_mes])

    return render(request, 'home.html', {
        'interacoes_7d': interacoes_7d,
        'contatos_alcancados_7d': contatos_alcancados_7d,
        'fila_total': fila_total,
        'dias_eleicao': dias_eleicao,
        'meta_votos': config.meta_votos,
        'total_votos': total_votos,
        'percentual': percentual,
        'faltam': faltam,
        # Financeiro
        'meta_doacoes_fmt': f'{config.meta_doacoes:,.0f}'.replace(',', '.'),
        'percentual_meta': round(float(total_arrecadado) / config.meta_doacoes * 100, 1) if config.meta_doacoes > 0 else 0,
        'total_arrecadado': total_arrecadado,
        'total_liquido': total_liquido,
        'pendentes_qtd': pendentes_qtd,
        'pendentes_valor': pendentes_valor,
        # Agenda
        'compromissos_semana': compromissos_semana,
        'eventos_semana': eventos_semana,
        # Tarefas
        'tarefas_vencidas': tarefas_vencidas,
        'tarefas_hoje': tarefas_hoje,
        'tarefas_semana': tarefas_semana_qs,
        # Atividade
        'ultimos_apoiadores': ultimos_apoiadores,
        'ultimas_doacoes': ultimas_doacoes,
        # Rede
        'coordenadores_ativos': coordenadores_ativos,
        'cabos_ativos': cabos_ativos,
        'top_regioes': top_regioes,
        # Gráficos
        'chart_captacao_labels': chart_captacao_labels,
        'chart_captacao_data': chart_captacao_data,
        'chart_arrec_labels': chart_arrec_labels,
        'chart_arrec_data': chart_arrec_data,
    })






@secao_required('dashboard:meta_votos')
def meta_votos(request):
    vinculo_map = dict(Usuario.VINCULO_CHOICES)

    config = Configuracao.get()
    total_votos = Apoiador.objects.count()
    percentual = round((total_votos / config.meta_votos) * 100, 1) if config.meta_votos > 0 else 0

    pwa_users = Usuario.objects.filter(
        vinculo__in=['coordenador', 'cabo', 'replicador']
    ).select_related('regiao', 'cidade')

    ranking_geral = []
    totais_vinculo = {'coordenador': 0, 'cabo': 0, 'replicador': 0}
    totais_regiao = {}

    diretos_map, convidados_map = calcular_scores_rede()

    for u in pwa_users:
        diretos, rede, total, convidados = score_usuario(u.id, diretos_map, convidados_map)
        if u.vinculo in totais_vinculo:
            totais_vinculo[u.vinculo] += total

        regiao_sigla = u.regiao.sigla if u.regiao else 'Sem região'
        if regiao_sigla not in totais_regiao:
            totais_regiao[regiao_sigla] = {'total': 0, 'coordenador': 0, 'cabo': 0, 'replicador': 0}
        totais_regiao[regiao_sigla]['total'] += total
        if u.vinculo in totais_regiao[regiao_sigla]:
            totais_regiao[regiao_sigla][u.vinculo] += total

        ranking_geral.append({
            'id': u.id,
            'nome': u.get_full_name() or u.username,
            'vinculo': vinculo_map.get(u.vinculo, u.vinculo),
            'vinculo_raw': u.vinculo,
            'regiao': regiao_sigla,
            'cidade': str(u.cidade) if u.cidade else '-',
            'diretos': diretos,
            'rede': rede,
            'total': total,
            'replicadores': len(convidados),
        })

    ranking_geral.sort(key=lambda x: x['total'], reverse=True)

    regioes_ranking = sorted(totais_regiao.items(), key=lambda x: x[1]['total'], reverse=True)

    vinculo_filtro = request.GET.get('vinculo', '')
    regiao_filtro = request.GET.get('regiao', '')
    busca = request.GET.get('busca', '')

    ranking_filtrado = ranking_geral
    if vinculo_filtro:
        ranking_filtrado = [r for r in ranking_filtrado if r['vinculo_raw'] == vinculo_filtro]
    if regiao_filtro:
        ranking_filtrado = [r for r in ranking_filtrado if r['regiao'] == regiao_filtro]
    if busca:
        busca_lower = busca.lower()
        ranking_filtrado = [r for r in ranking_filtrado if busca_lower in r['nome'].lower()]

    regioes_list = Regiao.objects.all().order_by('sigla')

    faltam = max(0, config.meta_votos - total_votos)

    paginator = Paginator(ranking_filtrado, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'dashboard/meta_votos.html', {
        'meta_votos': config.meta_votos,
        'total_votos': total_votos,
        'percentual': percentual,
        'faltam': faltam,
        'totais_vinculo': totais_vinculo,
        'regioes_ranking': regioes_ranking,
        'page_obj': page_obj,
        'vinculo_choices': Usuario.VINCULO_CHOICES,
        'regioes_list': regioes_list,
        'vinculo_filtro': vinculo_filtro,
        'regiao_filtro': regiao_filtro,
        'busca': busca,
    })
