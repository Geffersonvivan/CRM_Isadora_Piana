from django.shortcuts import render, redirect
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
import json

from core.models import Configuracao
from core.services import calcular_scores_rede, score_usuario
from usuarios.models import Usuario
from usuarios.views import secao_required
from liderancas.models import Lideranca, Regiao, InteracaoLog
from agenda.models import Compromisso, Evento
from tarefas.models import Tarefa

def home_view(request):
    config = Configuracao.get()
    total_votos = Lideranca.objects.aprovados().filter(papel='apoiador').count()
    percentual = round((total_votos / config.meta_votos) * 100, 1) if config.meta_votos > 0 else 0
    faltam = max(0, config.meta_votos - total_votos)

    now = timezone.now()
    hoje = now.date()
    fim_semana = hoje + timedelta(days=7)

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
    ultimos_apoiadores = Lideranca.objects.aprovados().filter(papel='apoiador').select_related(
        'cadastrado_por', 'cidade',
    ).order_by('-created_at')[:5]

    # --- Placar da Semana (ciclo de relacionamento) ---
    from datetime import date
    last_7 = now - timedelta(days=7)
    interacoes_7d = InteracaoLog.objects.filter(data__gte=last_7).count()
    contatos_alcancados_7d = (
        InteracaoLog.objects.filter(data__gte=last_7, lideranca__isnull=False)
        .values('lideranca').distinct().count()
    )
    dias_eleicao = (date(2026, 10, 4) - hoje).days

    # --- Rede ---
    coordenadores_ativos = Lideranca.objects.filter(papel='coordenador').count()
    cabos_ativos = Lideranca.objects.filter(papel='cabo').count()
    top_regioes = (
        Lideranca.objects.aprovados().filter(papel='apoiador', cidade__regiao__isnull=False)
        .values('cidade__regiao__sigla')
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )

    # --- Gráficos ---
    # Captação últimos 7 dias (uma única query agregada por dia)
    inicio_captacao = hoje - timedelta(days=6)
    captacao_por_dia = dict(
        Lideranca.objects.aprovados().filter(papel='apoiador', created_at__date__gte=inicio_captacao)
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

    return render(request, 'home.html', {
        'interacoes_7d': interacoes_7d,
        'contatos_alcancados_7d': contatos_alcancados_7d,
        'dias_eleicao': dias_eleicao,
        'meta_votos': config.meta_votos,
        'total_votos': total_votos,
        'percentual': percentual,
        'faltam': faltam,
        # Agenda
        'compromissos_semana': compromissos_semana,
        'eventos_semana': eventos_semana,
        # Tarefas
        'tarefas_vencidas': tarefas_vencidas,
        'tarefas_hoje': tarefas_hoje,
        'tarefas_semana': tarefas_semana_qs,
        # Atividade
        'ultimos_apoiadores': ultimos_apoiadores,
        # Rede
        'coordenadores_ativos': coordenadores_ativos,
        'cabos_ativos': cabos_ativos,
        'top_regioes': top_regioes,
        # Gráficos
        'chart_captacao_labels': chart_captacao_labels,
        'chart_captacao_data': chart_captacao_data,
    })






def capa_view(request):
    """Capa de campanha — a tela inicial ao acessar (o '22' do LS).
    Um momento de orientação (identidade + relógio + meta + entradas),
    não uma ferramenta. O painel operacional vive atrás do menu Dashboard.
    Os contadores de pendentes vêm do context processor (leads_pendentes)."""
    # Marca sem capa (Isadora) entra direto no destino pós-login (a Dashboard).
    if not settings.CAMPANHA.get('CAPA_ATIVA', True):
        return redirect(settings.LOGIN_REDIRECT_URL)
    from datetime import date
    config = Configuracao.get()
    total_votos = Lideranca.objects.aprovados().filter(papel='apoiador').count()
    meta = config.meta_votos or 0
    faltam = max(0, meta - total_votos)
    percentual = round((total_votos / meta) * 100, 1) if meta > 0 else 0
    hoje = timezone.now().date()
    dias_eleicao = max(0, (date(2026, 10, 4) - hoje).days)
    tarefas_vencidas = Tarefa.objects.exclude(fase='concluida').filter(prazo__lt=hoje).count()
    compromissos_hoje = (
        Compromisso.objects.filter(data_hora_inicio__date=hoje)
        .exclude(status='cancelado').count()
    )
    return render(request, 'capa.html', {
        'meta_votos': meta,
        'total_votos': total_votos,
        'faltam': faltam,
        'percentual': percentual,
        'percentual_barra': min(percentual, 100),
        'dias_eleicao': dias_eleicao,
        'tarefas_vencidas': tarefas_vencidas,
        'compromissos_hoje': compromissos_hoje,
    })


def _meta_votos_planilha(request):
    """Dashboard de votos no modelo da planilha central (Isadora): intenção de
    voto, funil vaquinha→doação e ranking por atendente. Só considera aprovados
    (base oficial, §3.1). Toda contagem agregada no banco (§12.2)."""
    config = Configuracao.get()
    meta = config.meta_votos or 0
    base = Lideranca.objects.aprovados().filter(papel='apoiador')

    ag = base.aggregate(
        total=Count('id'),
        sim=Count('id', filter=Q(intencao_voto='sim')),
        talvez=Count('id', filter=Q(intencao_voto='talvez')),
        nao=Count('id', filter=Q(intencao_voto='nao')),
        nao_contactado=Count('id', filter=Q(intencao_voto='nao_contactado')),
        contato=Count('id', filter=Q(contato_feito=True)),
        vaquinha=Count('id', filter=Q(vaquinha_enviada=True)),
        doou=Count('id', filter=Q(doou=True)),
        material=Count('id', filter=Q(material_entregue=True)),
    )
    total = ag['total']
    classificados = ag['sim'] + ag['talvez'] + ag['nao'] + ag['nao_contactado']
    confirmados = ag['sim']
    potencial = ag['sim'] + ag['talvez']

    percentual = round(confirmados / meta * 100, 1) if meta else 0
    faltam = max(0, meta - confirmados)
    cobertura_pct = round(classificados / total * 100, 1) if total else 0

    # Donut sobre os CLASSIFICADOS (decisão do responsável). Stops exatos por
    # contagem para o conic-gradient fechar 100% sem erro de arredondamento.
    voto_defs = [
        ('sim', 'Sim', ag['sim'], '#0d9488'),
        ('talvez', 'Talvez', ag['talvez'], '#f59e0b'),
        ('nao', 'Não', ag['nao'], '#dc2626'),
        ('nao_contactado', 'Não contactado', ag['nao_contactado'], '#94a3b8'),
    ]
    voto_legenda, stops, acc = [], [], 0.0
    for key, label, n, cor in voto_defs:
        frac = (n / classificados * 100) if classificados else 0
        stops.append(f'{cor} {acc:.3f}% {acc + frac:.3f}%')
        acc += frac
        voto_legenda.append({
            'key': key, 'label': label, 'n': n,
            'pct': round((n / classificados * 100), 1) if classificados else 0,
            'cor': cor,
        })
    donut_gradient = 'conic-gradient(' + ', '.join(stops) + ')' if classificados else ''

    # Funil de engajamento. Doação é conversão da VAQUINHA (não da base).
    def _pct(n, base_n):
        return round(n / base_n * 100, 1) if base_n else 0
    funil = [
        {'label': 'Base cadastrada', 'n': total, 'pct': 100, 'cor': '#FF6B00',
         'sub': 'aprovados na base oficial'},
        {'label': 'Contato feito', 'n': ag['contato'], 'pct': _pct(ag['contato'], total),
         'cor': '#2563eb', 'sub': f"{_pct(ag['contato'], total)}% da base"},
        {'label': 'Vaquinha enviada', 'n': ag['vaquinha'], 'pct': _pct(ag['vaquinha'], total),
         'cor': '#7c3aed', 'sub': f"link enviado a {ag['vaquinha']}"},
        {'label': 'Doou', 'n': ag['doou'], 'pct': _pct(ag['doou'], ag['vaquinha']),
         'cor': '#0d9488',
         'sub': (f"{ag['doou']} de {ag['vaquinha']} que receberam · "
                 f"{_pct(ag['doou'], ag['vaquinha'])}% de conversão"
                 if ag['vaquinha'] else 'sem vaquinha enviada ainda')},
    ]

    # Intenção por região de SC (só quem tem cidade/região e intenção definida).
    regioes = list(
        base.filter(cidade__regiao__isnull=False)
        .values('cidade__regiao__sigla')
        .annotate(
            sim=Count('id', filter=Q(intencao_voto='sim')),
            talvez=Count('id', filter=Q(intencao_voto='talvez')),
            nao=Count('id', filter=Q(intencao_voto='nao')),
            classificados=Count('id', filter=Q(
                intencao_voto__in=['sim', 'talvez', 'nao', 'nao_contactado'])),
        )
        .filter(classificados__gt=0)
        .order_by('-sim', '-talvez')[:12]
    )

    # Ranking por atendente — produtividade real da equipe.
    atendentes = list(
        base.filter(atendente_user__isnull=False)
        .values('atendente_user__id', 'atendente_user__first_name',
                'atendente_user__last_name', 'atendente_user__username')
        .annotate(
            sim=Count('id', filter=Q(intencao_voto='sim')),
            talvez=Count('id', filter=Q(intencao_voto='talvez')),
            contato=Count('id', filter=Q(contato_feito=True)),
            vaquinha=Count('id', filter=Q(vaquinha_enviada=True)),
            atendidos=Count('id'),
        )
        .order_by('-sim', '-atendidos')
    )
    for a in atendentes:
        nome = f"{a['atendente_user__first_name']} {a['atendente_user__last_name']}".strip()
        a['nome'] = nome or a['atendente_user__username']

    return render(request, 'dashboard/meta_votos_planilha.html', {
        'meta_votos': meta,
        'confirmados': confirmados,
        'potencial': potencial,
        'percentual': percentual,
        'faltam': faltam,
        'base_total': total,
        'classificados': classificados,
        'nao_classificados': total - classificados,
        'cobertura_pct': cobertura_pct,
        'donut_gradient': donut_gradient,
        'voto_legenda': voto_legenda,
        'funil': funil,
        'regioes': regioes,
        'atendentes': atendentes,
    })


@secao_required('dashboard:meta_votos')
def meta_votos(request):
    if settings.CAMPANHA.get('DASHBOARD_VOTOS_PLANILHA'):
        return _meta_votos_planilha(request)

    vinculo_map = dict(Usuario.VINCULO_CHOICES)

    config = Configuracao.get()
    total_votos = Lideranca.objects.aprovados().filter(papel='apoiador').count()
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
