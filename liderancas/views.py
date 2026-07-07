import csv
import io
from datetime import timedelta
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Max, Count
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from core.views import api_cidades as core_api_cidades
from core.views import api_regioes_cidades as core_api_regioes_cidades
from usuarios.views import admin_required, secao_required
from .models import Lideranca, Voluntario, Regiao, Cidade, InteracaoLog
from .forms import CoordenadorRegionalForm, CaboEleitoralForm, ApoiadorForm, VoluntarioForm, InteracaoLogForm


def login_required_view(view_func):
    """Decorator que exige autenticação."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


PER_PAGE_OPTIONS = [25, 50, 100, 200]

# Prazo (em dias) para cada frequência de relacionamento configurada.
# Usado por mapa (cálculo estratégico) e agenda; a página "Fila" foi removida.
FREQ_PRAZOS = {'semanal': 7, 'quinzenal': 15, 'mensal': 30, 'eventual': 90}


def _paginate(request, queryset, default=50):
    """Pagina respeitando o parâmetro ?per_page= (25/50/100/200)."""
    try:
        per_page = int(request.GET.get('per_page', default))
    except (TypeError, ValueError):
        per_page = default
    if per_page not in PER_PAGE_OPTIONS:
        per_page = default
    # annotate(Max(...)) descarta o Meta.ordering — sem isso a paginação embaralha
    # (listas já ordenadas em Python não têm o atributo 'ordered')
    if hasattr(queryset, 'ordered') and not queryset.ordered:
        queryset = queryset.order_by('nome')
    paginator = Paginator(queryset, per_page)
    return paginator, paginator.get_page(request.GET.get('page'))


def _ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _apply_sorting(request, queryset, allowed_fields):
    """Aplica ordenação ao queryset baseado nos parâmetros sort/dir."""
    sort = request.GET.get('sort', '')
    direction = request.GET.get('dir', 'asc')
    if sort in allowed_fields:
        order_field = f'-{sort}' if direction == 'desc' else sort
        queryset = queryset.order_by(order_field)
    current_sort = sort
    current_dir = direction
    return queryset, current_sort, current_dir


# ==================== LISTA UNIFICADA ====================

PAPEL_LABEL = {'coordenador': 'Coordenador', 'cabo': 'Cabo Eleitoral', 'apoiador': 'Apoiador'}
PAPEL_EDIT_URL = {
    'coordenador': 'liderancas:coordenador_edit',
    'cabo': 'liderancas:cabo_edit',
    'apoiador': 'liderancas:apoiador_edit',
}


SITUACAO_CHOICES = [
    ('em_dia', 'Em dia'),
    ('atrasado', 'Atrasado'),
    ('nunca', 'Nunca contatado'),
]

LIDERANCA_CSV_HEADER = ['Nome', 'Papel', 'Telefone', 'Email', 'Cidade', 'Região',
                        'Coordenador Responsável', 'Categoria', 'Cargo', 'Prioridade',
                        'Frequência', 'Status', 'Instagram', 'Observações']


def _busca_q(busca):
    """Q de busca em nome/email/cidade/observações (sem acento no Postgres) + telefone."""
    from django.db import connection
    ic = 'unaccent__icontains' if connection.vendor == 'postgresql' else 'icontains'
    return (
        Q(**{f'nome__{ic}': busca}) | Q(telefone__icontains=busca) |
        Q(**{f'email__{ic}': busca}) | Q(**{f'cidade__nome__{ic}': busca}) |
        Q(**{f'observacoes__{ic}': busca})
    )


def _liderancas_csv(qs, filename):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.charset = 'utf-8-sig'
    writer = csv.writer(response)
    writer.writerow(LIDERANCA_CSV_HEADER)
    for o in qs:
        writer.writerow([
            o.nome, o.get_papel_display(), o.telefone, o.email,
            o.cidade.nome if o.cidade_id else '', o.cidade.regiao.sigla if o.cidade_id else '',
            o.coordenador_responsavel.nome if o.coordenador_responsavel_id else '',
            o.get_tipos_display() if o.tipo else '', o.get_cargo_display() if o.cargo else '',
            o.get_prioridade_display(), o.get_frequencia_relacionamento_display(),
            o.get_status_display() if o.status else '', o.instagram, o.observacoes,
        ])
    return response


@secao_required('liderancas:lista')
def lideranca_list(request):
    """Lista única de Lideranças (coordenadores + cabos + apoiadores) com filtros avançados."""
    papeis = [p for p in request.GET.getlist('papel') if p in ('coordenador', 'cabo', 'apoiador')]
    regioes_sel = [r for r in request.GET.getlist('regiao') if r]
    tipos_sel = [t for t in request.GET.getlist('tipo') if t]
    busca = request.GET.get('busca', '')
    cidade_id = request.GET.get('cidade', '')
    coordenador_id = request.GET.get('coordenador', '')
    prioridade = request.GET.get('prioridade', '')
    status = request.GET.get('status', '')
    situacao = request.GET.get('situacao', '')
    aprovacao = request.GET.get('aprovacao', '')

    qs = Lideranca.objects.select_related(
        'cidade', 'cidade__regiao', 'regiao', 'coordenador_responsavel', 'cadastrado_por'
    ).annotate(ultima_interacao=Max('interacoes__data'))

    # Aprovação: por padrão esconde rejeitados; filtro explícito mostra o estado pedido
    if aprovacao in ('pendente', 'aprovado', 'rejeitado'):
        qs = qs.filter(aprovacao=aprovacao)
    else:
        qs = qs.exclude(aprovacao='rejeitado')

    # --- filtros (exceto papel; papel é aplicado depois p/ contar as abas) ---
    if busca:
        qs = qs.filter(_busca_q(busca))
    if regioes_sel:
        qs = qs.filter(regiao_id__in=regioes_sel)
    if cidade_id:
        qs = qs.filter(cidade_id=cidade_id)
    if coordenador_id:
        qs = qs.filter(coordenador_responsavel_id=coordenador_id)
    if prioridade:
        qs = qs.filter(prioridade=prioridade)
    if tipos_sel:
        qs = qs.filter(tipo__in=tipos_sel)
    if status:
        qs = qs.filter(status=status)
    if situacao == 'nunca':
        qs = qs.filter(ultima_interacao__isnull=True)
    elif situacao in ('em_dia', 'atrasado'):
        agora = timezone.now()
        atraso_q = Q()
        for freq, dias in FREQ_PRAZOS.items():
            atraso_q |= Q(frequencia_relacionamento=freq, ultima_interacao__lt=agora - timedelta(days=dias))
        qs = qs.filter(ultima_interacao__isnull=False)
        qs = qs.filter(atraso_q) if situacao == 'atrasado' else qs.exclude(atraso_q)

    # Contagem por papel (respeita os demais filtros) → abas
    contagem = {
        'todos': qs.count(),
        'coordenador': qs.filter(papel='coordenador').count(),
        'cabo': qs.filter(papel='cabo').count(),
        'apoiador': qs.filter(papel='apoiador').count(),
    }
    if papeis:
        qs = qs.filter(papel__in=papeis)

    qs, current_sort, current_dir = _apply_sorting(
        request, qs,
        ['nome', 'papel', 'cidade__nome', 'regiao__sigla', 'prioridade',
         'ultima_interacao', 'votos_referencia', 'created_at'],
    )

    if request.GET.get('export') == 'csv':
        return _liderancas_csv(qs, 'liderancas.csv')

    paginator, page_obj = _paginate(request, qs)

    cidades_filtro = Cidade.objects.filter(regiao_id__in=regioes_sel).order_by('nome') if regioes_sel else []
    coordenadores = Lideranca.objects.filter(papel='coordenador').order_by('nome')
    regioes = Regiao.objects.all().order_by('sigla')

    # --- Abas-contador por papel (toggle multi) ---
    papeis_set = set(papeis)

    def _toggle_qs(papel_key):
        params = request.GET.copy()
        params.pop('page', None)
        params.pop('export', None)
        if papel_key == '':
            params.setlist('papel', [])
        else:
            s = set(papeis_set)
            s.discard(papel_key) if papel_key in s else s.add(papel_key)
            params.setlist('papel', sorted(s))
        return params.urlencode()

    abas = [{'key': '', 'label': 'Todos', 'count': contagem['todos'], 'qs': _toggle_qs(''), 'active': not papeis}]
    for val, label in Lideranca.PAPEL_CHOICES:
        abas.append({'key': val, 'label': label, 'count': contagem[val],
                     'qs': _toggle_qs(val), 'active': val in papeis_set})

    # --- Chips de filtros ativos (remove um valor por vez) ---
    base_params = request.GET.copy()
    base_params.pop('page', None)
    base_params.pop('export', None)
    filtros_ativos = []

    def _chip(param, label, value, display):
        sem = base_params.copy()
        sem.setlist(param, [v for v in sem.getlist(param) if v != value])
        filtros_ativos.append({'label': label, 'display': display or value, 'remove_qs': sem.urlencode()})

    for p in papeis:
        _chip('papel', 'Papel', p, dict(Lideranca.PAPEL_CHOICES).get(p, p))
    for r in regioes_sel:
        _chip('regiao', 'Região', r, Regiao.objects.filter(id=r).values_list('sigla', flat=True).first() or r)
    for t in tipos_sel:
        _chip('tipo', 'Categoria', t, dict(Lideranca.TIPO_CHOICES).get(t, t))
    if busca:
        _chip('busca', 'Busca', busca, busca)
    if cidade_id:
        _chip('cidade', 'Cidade', cidade_id, Cidade.objects.filter(id=cidade_id).values_list('nome', flat=True).first() or cidade_id)
    if coordenador_id:
        _chip('coordenador', 'Coordenador', coordenador_id, coordenadores.filter(id=coordenador_id).values_list('nome', flat=True).first() or coordenador_id)
    if prioridade:
        _chip('prioridade', 'Prioridade', prioridade, prioridade.title())
    if status:
        _chip('status', 'Status', status, dict(Lideranca.STATUS_CHOICES).get(status, status))
    if situacao:
        _chip('situacao', 'Situação', situacao, dict(SITUACAO_CHOICES).get(situacao, situacao))
    if aprovacao:
        _chip('aprovacao', 'Aprovação', aprovacao, dict(Lideranca.APROVACAO_CHOICES).get(aprovacao, aprovacao))

    try:
        per_page = int(request.GET.get('per_page', 50))
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 50

    qs_params = request.GET.copy()
    qs_params.pop('page', None)

    sort_base = request.GET.copy()
    sort_base.pop('page', None)
    sort_base.pop('sort', None)
    sort_base.pop('dir', None)

    return render(request, 'liderancas/lideranca_list.html', {
        'page_obj': page_obj,
        # Colunas exibidas vêm da config de marca (Fase 2): mesma tabela,
        # cada marca com seu conjunto/ordem de colunas.
        'colunas': settings.CAMPANHA['COLUNAS_LIDERANCA'],
        'total': paginator.count,
        'total_geral': Lideranca.objects.count(),
        'qs_sort_base': sort_base.urlencode(),
        'abas': abas,
        'papeis_sel': papeis,
        'tipo_choices': Lideranca.TIPO_CHOICES,
        'status_choices': Lideranca.STATUS_CHOICES,
        'situacao_choices': SITUACAO_CHOICES,
        'aprovacao_choices': Lideranca.APROVACAO_CHOICES,
        'aprovacao_filtro': aprovacao,
        'prioridade_choices': Lideranca.PRIORIDADE_CHOICES,
        'pode_aprovar': request.user.pode_acessar('liderancas:aprovar'),
        'pendentes_total': Lideranca.objects.filter(aprovacao='pendente').count(),
        'rejeitados_total': Lideranca.objects.filter(aprovacao='rejeitado').count(),
        'regioes': regioes,
        'regioes_sel': regioes_sel,
        'tipos_sel': tipos_sel,
        'cidades_filtro': cidades_filtro,
        'coordenadores': coordenadores,
        'busca': busca,
        'cidade_filtro': cidade_id,
        'coordenador_filtro': coordenador_id,
        'prioridade_filtro': prioridade,
        'status_filtro': status,
        'situacao_filtro': situacao,
        'filtros_ativos': filtros_ativos,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTIONS,
        'query_string': qs_params.urlencode(),
        'current_sort': current_sort,
        'current_dir': current_dir,
        'papel_edit_url': PAPEL_EDIT_URL,
    })


@secao_required('liderancas:lista')
def lideranca_bulk_action(request):
    """Ações em massa sobre a tabela unificada de Lideranças."""
    nxt = request.POST.get('next', '')
    back = redirect(nxt if nxt.startswith('/') else 'liderancas:lideranca_list')
    if request.method != 'POST':
        return back

    ids = request.POST.getlist('selected_ids')
    action = request.POST.get('bulk_action', '')
    if not ids:
        messages.warning(request, 'Nenhum registro selecionado.')
        return back

    qs = Lideranca.objects.filter(pk__in=ids)

    if action == 'export_csv':
        return _liderancas_csv(qs.select_related('cidade', 'cidade__regiao', 'coordenador_responsavel'),
                               'liderancas_selecionados.csv')
    elif action == 'delete':
        n = 0
        for o in qs:
            o.soft_delete(user=request.user)
            n += 1
        messages.success(request, f'{n} registro(s) removido(s).')
    elif action.startswith('prioridade_'):
        val = action.split('_', 1)[1]
        if val in dict(Lideranca.PRIORIDADE_CHOICES):
            n = qs.update(prioridade=val, atualizado_por=request.user)
            messages.success(request, f'{n} registro(s) com prioridade alterada para {val}.')
    elif action.startswith('status_'):
        val = action.split('_', 1)[1]
        if val in dict(Lideranca.STATUS_CHOICES):
            n = qs.filter(papel='apoiador').update(status=val, atualizado_por=request.user)
            messages.success(request, f'{n} apoiador(es) com status alterado para {val}.')
    elif action.startswith('coordenador_'):
        coord_id = action.split('_', 1)[1]
        if Lideranca.objects.filter(pk=coord_id, papel='coordenador').exists():
            n = qs.exclude(papel='coordenador').update(coordenador_responsavel_id=coord_id, atualizado_por=request.user)
            messages.success(request, f'{n} liderança(s) vinculada(s) ao coordenador.')
    elif action == 'registrar_interacao':
        tipo = request.POST.get('int_tipo', '')
        descricao = request.POST.get('int_descricao', '')
        data_raw = request.POST.get('int_data', '')
        if tipo and descricao:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(data_raw) if data_raw else None
            if dt and timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            dt = dt or timezone.now()
            n = 0
            for o in qs:
                InteracaoLog.objects.create(lideranca=o, tipo=tipo, descricao=descricao,
                                            data=dt, registrado_por=request.user)
                n += 1
            messages.success(request, f'{n} interação(ões) registrada(s).')
        else:
            messages.warning(request, 'Informe tipo e descrição da interação.')
    elif action in ('aprovar', 'rejeitar'):
        if not request.user.pode_acessar('liderancas:aprovar'):
            messages.error(request, 'Você não tem permissão para aprovar/rejeitar leads.')
            return back
        if action == 'aprovar':
            # aprova pendentes E rejeitados (aceitar/restaurar)
            n = qs.exclude(aprovacao='aprovado').update(
                aprovacao='aprovado', aprovado_por=request.user,
                aprovado_em=timezone.now(), motivo_rejeicao='',
            )
            messages.success(request, f'{n} lead(s) aprovado(s) — agora contam na base.')
        else:
            motivo = request.POST.get('motivo_rejeicao', '').strip()
            n = qs.exclude(aprovacao='rejeitado').update(
                aprovacao='rejeitado', aprovado_por=request.user,
                aprovado_em=timezone.now(), motivo_rejeicao=motivo,
            )
            messages.success(request, f'{n} lead(s) rejeitado(s).')
    else:
        messages.error(request, 'Ação inválida.')

    return back


# ==================== COORDENADORES ====================

@secao_required('liderancas:lista')
def coordenador_list(request):
    coordenadores = Lideranca.objects.filter(papel='coordenador').select_related('regiao', 'cidade').annotate(
        ultima_interacao=Max('interacoes__data')
    )

    busca = request.GET.get('busca', '')
    regiao_id = request.GET.get('regiao', '')
    prioridade = request.GET.get('prioridade', '')

    if busca:
        coordenadores = coordenadores.filter(
            Q(nome__icontains=busca) | Q(telefone__icontains=busca) | Q(email__icontains=busca)
        )
    if regiao_id:
        coordenadores = coordenadores.filter(regiao_id=regiao_id)
    if prioridade:
        coordenadores = coordenadores.filter(prioridade=prioridade)

    coordenadores, current_sort, current_dir = _apply_sorting(
        request, coordenadores, ['nome', 'regiao__sigla', 'cidade__nome', 'prioridade', 'created_at']
    )

    # CSV Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="coordenadores.csv"'
        response.charset = 'utf-8-sig'
        writer = csv.writer(response)
        writer.writerow(['Nome', 'Telefone', 'Email', 'Região', 'Cidade Base', 'Instagram', 'Prioridade', 'Frequência', 'Observações'])
        for c in coordenadores:
            writer.writerow([c.nome, c.telefone, c.email, c.regiao.sigla if c.regiao else '', c.cidade.nome, c.instagram, c.get_prioridade_display(), c.get_frequencia_relacionamento_display(), c.observacoes])
        return response

    paginator, page_obj = _paginate(request, coordenadores)

    qs_params = request.GET.copy()
    qs_params.pop('page', None)

    return render(request, 'liderancas/coordenador_list.html', {
        'page_obj': page_obj,
        'regioes': Regiao.objects.all().order_by('sigla'),
        'busca': busca,
        'regiao_filtro': regiao_id,
        'prioridade_filtro': prioridade,
        'total': paginator.count,
        'query_string': qs_params.urlencode(),
        'current_sort': current_sort,
        'current_dir': current_dir,
    })


@secao_required('liderancas:lista')
def coordenador_create(request):
    if request.method == 'POST':
        form = CoordenadorRegionalForm(request.POST)
        if form.is_valid():
            coord = form.save(commit=False)
            coord.cadastrado_por = request.user
            coord.save()
            messages.success(request, 'Coordenador Regional cadastrado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:coordenador_list')
    else:
        form = CoordenadorRegionalForm()
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/coordenador_form.html', {
        'form': form,
        'titulo': 'Novo Coordenador Regional',
    })


@secao_required('liderancas:lista')
def coordenador_edit(request, pk):
    coord = get_object_or_404(Lideranca, pk=pk, papel='coordenador')
    if request.method == 'POST':
        form = CoordenadorRegionalForm(request.POST, instance=coord)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.atualizado_por = request.user
            obj.save()
            messages.success(request, 'Coordenador Regional atualizado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:coordenador_list')
    else:
        form = CoordenadorRegionalForm(instance=coord)
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/coordenador_form.html', {
        'form': form,
        'titulo': f'Editar: {coord}',
    })


@secao_required('liderancas:lista')
def coordenador_delete(request, pk):
    coord = get_object_or_404(Lideranca, pk=pk, papel='coordenador')
    if request.method == 'POST':
        coord.soft_delete(user=request.user)
        messages.success(request, 'Coordenador Regional removido com sucesso.')
    return redirect('liderancas:coordenador_list')


# ==================== CABOS ELEITORAIS ====================

@secao_required('liderancas:lista')
def cabo_list(request):
    cabos = Lideranca.objects.filter(papel='cabo').select_related('cidade', 'cidade__regiao', 'coordenador_responsavel').annotate(
        ultima_interacao=Max('interacoes__data')
    )

    busca = request.GET.get('busca', '')
    regiao_id = request.GET.get('regiao', '')
    cidade_id = request.GET.get('cidade', '')
    prioridade = request.GET.get('prioridade', '')

    if busca:
        cabos = cabos.filter(
            Q(nome__icontains=busca) | Q(telefone__icontains=busca) | Q(email__icontains=busca)
        )
    if regiao_id:
        cabos = cabos.filter(cidade__regiao_id=regiao_id)
    if cidade_id:
        cabos = cabos.filter(cidade_id=cidade_id)
    if prioridade:
        cabos = cabos.filter(prioridade=prioridade)

    cabos, current_sort, current_dir = _apply_sorting(
        request, cabos, ['nome', 'cidade__nome', 'cidade__regiao__sigla', 'coordenador_responsavel__nome', 'prioridade', 'created_at']
    )

    # CSV Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="cabos_eleitorais.csv"'
        response.charset = 'utf-8-sig'
        writer = csv.writer(response)
        writer.writerow(['Nome', 'Telefone', 'Email', 'Cidade', 'Região', 'Coordenador', 'Instagram', 'Prioridade', 'Frequência', 'Observações'])
        for c in cabos:
            writer.writerow([c.nome, c.telefone, c.email, c.cidade.nome, c.cidade.regiao.sigla, c.coordenador_responsavel.nome if c.coordenador_responsavel_id else '', c.instagram, c.get_prioridade_display(), c.get_frequencia_relacionamento_display(), c.observacoes])
        return response

    paginator, page_obj = _paginate(request, cabos)

    cidades_filtro = []
    if regiao_id:
        cidades_filtro = Cidade.objects.filter(regiao_id=regiao_id).order_by('nome')

    qs_params = request.GET.copy()
    qs_params.pop('page', None)

    return render(request, 'liderancas/cabo_list.html', {
        'page_obj': page_obj,
        'regioes': Regiao.objects.all().order_by('sigla'),
        'cidades_filtro': cidades_filtro,
        'busca': busca,
        'regiao_filtro': regiao_id,
        'cidade_filtro': cidade_id,
        'prioridade_filtro': prioridade,
        'total': paginator.count,
        'query_string': qs_params.urlencode(),
        'current_sort': current_sort,
        'current_dir': current_dir,
    })


@secao_required('liderancas:lista')
def cabo_create(request):
    if request.method == 'POST':
        form = CaboEleitoralForm(request.POST)
        if form.is_valid():
            cabo = form.save(commit=False)
            cabo.cadastrado_por = request.user
            cabo.save()
            messages.success(request, 'Cabo Eleitoral cadastrado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:cabo_list')
    else:
        form = CaboEleitoralForm()
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/cabo_form.html', {
        'form': form,
        'titulo': 'Novo Cabo Eleitoral',
    })


@secao_required('liderancas:lista')
def cabo_edit(request, pk):
    cabo = get_object_or_404(Lideranca, pk=pk, papel='cabo')
    if request.method == 'POST':
        form = CaboEleitoralForm(request.POST, instance=cabo)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.atualizado_por = request.user
            obj.save()
            messages.success(request, 'Cabo Eleitoral atualizado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:cabo_list')
    else:
        form = CaboEleitoralForm(instance=cabo)
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/cabo_form.html', {
        'form': form,
        'titulo': f'Editar: {cabo}',
    })


@secao_required('liderancas:lista')
def cabo_delete(request, pk):
    cabo = get_object_or_404(Lideranca, pk=pk, papel='cabo')
    if request.method == 'POST':
        cabo.soft_delete(user=request.user)
        messages.success(request, 'Cabo Eleitoral removido com sucesso.')
    return redirect('liderancas:cabo_list')


# ==================== APOIADORES ====================

@secao_required('liderancas:lista')
def apoiador_list(request):
    apoiadores = Lideranca.objects.filter(papel='apoiador').select_related('cidade', 'cidade__regiao', 'cadastrado_por').annotate(
        ultima_interacao=Max('interacoes__data')
    )

    # Filtrar por perfil do usuário
    user = request.user
    if user.perfil == 'admin' or user.is_superuser or user.pode_acessar('liderancas:apoiadores'):
        pass  # Vê todos
    elif hasattr(user, 'coordenacao'):
        apoiadores = apoiadores.filter(cidade__regiao=user.coordenacao.regiao)
    elif hasattr(user, 'cabo_eleitoral'):
        apoiadores = apoiadores.filter(cidade=user.cabo_eleitoral.cidade)
    else:
        apoiadores = apoiadores.filter(cadastrado_por=user)

    # Filtros da query string
    busca = request.GET.get('busca', '')
    tipo = request.GET.get('tipo', '')
    regiao_id = request.GET.get('regiao', '')
    cidade_id = request.GET.get('cidade', '')
    prioridade = request.GET.get('prioridade', '')
    status = request.GET.get('status', '')
    grau = request.GET.get('grau', '')
    cargo = request.GET.get('cargo', '')

    if busca:
        apoiadores = apoiadores.filter(
            Q(nome__icontains=busca) |
            Q(telefone__icontains=busca) |
            Q(email__icontains=busca)
        )
    if tipo:
        apoiadores = apoiadores.filter(tipo=tipo)
    if cargo:
        apoiadores = apoiadores.filter(cargo=cargo)
    if regiao_id:
        apoiadores = apoiadores.filter(cidade__regiao_id=regiao_id)
    if cidade_id:
        apoiadores = apoiadores.filter(cidade_id=cidade_id)
    if prioridade:
        apoiadores = apoiadores.filter(prioridade=prioridade)
    if status:
        apoiadores = apoiadores.filter(status=status)
    if grau:
        apoiadores = apoiadores.filter(grau_influencia=grau)

    apoiadores, current_sort, current_dir = _apply_sorting(
        request, apoiadores, ['nome', 'cidade__nome', 'cidade__regiao__sigla', 'tipo', 'cargo', 'prioridade', 'grau_influencia', 'status', 'created_at']
    )

    # CSV Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="apoiadores.csv"'
        response.charset = 'utf-8-sig'
        writer = csv.writer(response)
        writer.writerow(['Nome', 'Telefone', 'Email', 'Cidade', 'Região', 'Tipo', 'Cargo', 'Origem', 'Instagram', 'Prioridade', 'Influência', 'Frequência', 'Status', 'Observações'])
        for a in apoiadores:
            writer.writerow([a.nome, a.telefone, a.email, a.cidade.nome, a.cidade.regiao.sigla, a.get_tipos_display(), a.get_cargo_display(), a.origem_contato, a.instagram, a.get_prioridade_display(), a.get_grau_influencia_display(), a.get_frequencia_relacionamento_display(), a.get_status_display(), a.observacoes])
        return response

    paginator, page_obj = _paginate(request, apoiadores)

    # Cidades filtradas por região (para o select de cidade)
    cidades_filtro = []
    if regiao_id:
        cidades_filtro = Cidade.objects.filter(regiao_id=regiao_id).order_by('nome')

    # Query string sem 'page' para paginação
    qs_params = request.GET.copy()
    qs_params.pop('page', None)
    query_string = qs_params.urlencode()

    return render(request, 'liderancas/apoiador_list.html', {
        'page_obj': page_obj,
        'tipo_choices': Lideranca.TIPO_CHOICES,
        'cargo_choices': Lideranca.CARGO_CHOICES,
        'prioridade_choices': Lideranca.PRIORIDADE_CHOICES,
        'regioes': Regiao.objects.all().order_by('sigla'),
        'cidades_filtro': cidades_filtro,
        'busca': busca,
        'tipo_filtro': tipo,
        'cargo_filtro': cargo,
        'regiao_filtro': regiao_id,
        'cidade_filtro': cidade_id,
        'prioridade_filtro': prioridade,
        'status_filtro': status,
        'grau_filtro': grau,
        'total': paginator.count,
        'query_string': query_string,
        'current_sort': current_sort,
        'current_dir': current_dir,
    })


@secao_required('liderancas:lista')
def apoiador_create(request):
    if request.method == 'POST':
        form = ApoiadorForm(request.POST, user=request.user)
        if form.is_valid():
            apoiador = form.save(commit=False)
            apoiador.cadastrado_por = request.user
            apoiador.save()
            messages.success(request, 'Apoiador cadastrado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:apoiador_list')
    else:
        form = ApoiadorForm(user=request.user)
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/apoiador_form.html', {
        'form': form,
        'titulo': 'Novo Apoiador',
    })


@secao_required('liderancas:lista')
def apoiador_edit(request, pk):
    apoiador = get_object_or_404(Lideranca, pk=pk, papel='apoiador')
    user = request.user
    if not user.is_superuser and getattr(user, 'perfil', None) != 'admin':
        if apoiador.cadastrado_por != user:
            messages.error(request, 'Você não tem permissão para editar este apoiador.')
            return redirect('liderancas:apoiador_list')
    if request.method == 'POST':
        form = ApoiadorForm(request.POST, instance=apoiador, user=request.user)
        if form.is_valid():
            apoiador = form.save(commit=False)
            apoiador.atualizado_por = request.user
            apoiador.save()
            messages.success(request, 'Apoiador atualizado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:apoiador_list')
    else:
        form = ApoiadorForm(instance=apoiador, user=request.user)
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/apoiador_form.html', {
        'form': form,
        'titulo': f'Editar: {apoiador}',
    })


@secao_required('liderancas:lista')
def apoiador_delete(request, pk):
    apoiador = get_object_or_404(Lideranca, pk=pk, papel='apoiador')
    user = request.user
    if not user.is_superuser and getattr(user, 'perfil', None) != 'admin':
        if apoiador.cadastrado_por != user:
            messages.error(request, 'Você não tem permissão para excluir este apoiador.')
            return redirect('liderancas:apoiador_list')
    if request.method == 'POST':
        apoiador.soft_delete(user=request.user)
        messages.success(request, 'Apoiador removido com sucesso.')
    return redirect('liderancas:apoiador_list')



@secao_required('liderancas:lista')
def bulk_action(request):
    """Ações em massa para liderancas."""
    if request.method != 'POST':
        return redirect('liderancas:apoiador_list')

    action = request.POST.get('bulk_action', '')
    ids = request.POST.getlist('selected_ids')
    entity_type = request.POST.get('entity_type', '')

    if not ids:
        messages.warning(request, 'Nenhum registro selecionado.')
        redirect_map = {
            'coordenador': 'liderancas:coordenador_list',
            'cabo': 'liderancas:cabo_list',
            'apoiador': 'liderancas:apoiador_list',
        }
        return redirect(redirect_map.get(entity_type, 'liderancas:apoiador_list'))

    if entity_type in ('coordenador', 'cabo', 'apoiador'):
        qs = Lideranca.objects.filter(pk__in=ids, papel=entity_type)
    else:
        messages.error(request, 'Tipo inválido.')
        return redirect('liderancas:apoiador_list')

    if action == 'delete':
        count = 0
        for obj in qs:
            obj.soft_delete(user=request.user)
            count += 1
        messages.success(request, f'{count} registro(s) removido(s).')

    elif action.startswith('status_') and entity_type == 'apoiador':
        new_status = action.replace('status_', '')
        count = qs.update(status=new_status)
        messages.success(request, f'{count} registro(s) atualizado(s) para {new_status}.')

    elif action == 'export_csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{entity_type}_selecionados.csv"'
        response.charset = 'utf-8-sig'
        writer = csv.writer(response)

        if entity_type == 'apoiador':
            writer.writerow(['Nome', 'Telefone', 'Email', 'Cidade', 'Região', 'Tipo', 'Status', 'Prioridade'])
            for a in qs.select_related('cidade', 'cidade__regiao'):
                writer.writerow([a.nome, a.telefone, a.email, a.cidade.nome, a.cidade.regiao.sigla, a.get_tipos_display(), a.get_status_display(), a.get_prioridade_display()])
        elif entity_type == 'cabo':
            writer.writerow(['Nome', 'Telefone', 'Email', 'Cidade', 'Região', 'Coordenador', 'Prioridade'])
            for c in qs.select_related('cidade', 'cidade__regiao', 'coordenador_responsavel'):
                writer.writerow([c.nome, c.telefone, c.email, c.cidade.nome, c.cidade.regiao.sigla, c.coordenador_responsavel.nome if c.coordenador_responsavel_id else '', c.get_prioridade_display()])
        elif entity_type == 'coordenador':
            writer.writerow(['Nome', 'Telefone', 'Email', 'Região', 'Cidade Base', 'Prioridade'])
            for c in qs.select_related('regiao', 'cidade'):
                writer.writerow([c.nome, c.telefone, c.email, c.regiao.sigla if c.regiao else '', c.cidade.nome, c.get_prioridade_display()])
        return response

    redirect_map = {
        'coordenador': 'liderancas:coordenador_list',
        'cabo': 'liderancas:cabo_list',
        'apoiador': 'liderancas:apoiador_list',
    }
    return redirect(redirect_map.get(entity_type, 'liderancas:apoiador_list'))


# ==================== INTERAÇÕES ====================

def _resolve_entidade(entidade_tipo, pk):
    """Resolve a entidade e o nome do FK no InteracaoLog.
    Coordenador/cabo/apoiador → modelo unificado Lideranca (FK 'lideranca')."""
    if entidade_tipo in ('coordenador', 'cabo', 'apoiador'):
        return get_object_or_404(Lideranca, pk=pk, papel=entidade_tipo), 'lideranca'
    return None, None


@secao_required('liderancas:lista')
def interacao_add(request, entidade_tipo, pk):
    redirect_map = {
        'coordenador': 'liderancas:coordenador_list',
        'cabo': 'liderancas:cabo_list',
        'apoiador': 'liderancas:apoiador_list',
    }
    entidade, fk_field = _resolve_entidade(entidade_tipo, pk)
    if entidade is None:
        messages.error(request, 'Tipo de entidade inválido.')
        return redirect('liderancas:apoiador_list')

    if request.method == 'POST':
        form = InteracaoLogForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            setattr(log, fk_field, entidade)
            log.registrado_por = request.user
            log.save()
            messages.success(request, 'Interação registrada com sucesso.')
            return redirect(redirect_map[entidade_tipo])
    else:
        form = InteracaoLogForm()

    return render(request, 'liderancas/interacao_form.html', {
        'form': form,
        'entidade': entidade,
        'entidade_tipo': entidade_tipo,
        'titulo': f'Nova Interação — {entidade.nome}',
    })


@login_required_view
def interacao_add_ajax(request, entidade_tipo, pk):
    """Registra interação via AJAX (modal)."""
    entidade, fk_field = _resolve_entidade(entidade_tipo, pk)
    if entidade is None:
        return JsonResponse({'ok': False, 'error': 'Tipo inválido.'}, status=400)

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método não permitido.'}, status=405)

    form = InteracaoLogForm(request.POST)
    if form.is_valid():
        log = form.save(commit=False)
        setattr(log, fk_field, entidade)
        log.registrado_por = request.user
        log.save()
        return JsonResponse({'ok': True})
    else:
        errors = {field: errs[0] for field, errs in form.errors.items()}
        return JsonResponse({'ok': False, 'errors': errors}, status=400)


@secao_required('liderancas:lista')
def interacao_list(request, entidade_tipo, pk):
    entidade, fk_field = _resolve_entidade(entidade_tipo, pk)
    if entidade is None:
        return JsonResponse({'error': 'Tipo inválido'}, status=400)

    interacoes = InteracaoLog.objects.filter(**{fk_field: entidade}).select_related('registrado_por')

    data = [{
        'id': i.id,
        'tipo': i.get_tipo_display(),
        'descricao': i.descricao,
        'data': i.data.strftime('%d/%m/%Y %H:%M'),
        'registrado_por': i.registrado_por.get_full_name() if i.registrado_por else '',
    } for i in interacoes[:50]]

    return JsonResponse({'interacoes': data, 'nome': entidade.nome})


# ==================== CSV IMPORT ====================

@admin_required
def csv_import(request, entidade_tipo):
    model_config = {
        'coordenador': {
            'fields': ['nome', 'telefone', 'email', 'regiao_sigla', 'cidade_nome', 'instagram', 'prioridade', 'frequencia_relacionamento', 'observacoes'],
            'redirect': 'liderancas:coordenador_list',
            'label': 'Coordenadores',
        },
        'cabo': {
            'fields': ['nome', 'telefone', 'email', 'regiao_sigla', 'cidade_nome', 'instagram', 'prioridade', 'frequencia_relacionamento', 'observacoes'],
            'redirect': 'liderancas:cabo_list',
            'label': 'Cabos Eleitorais',
        },
        'apoiador': {
            'fields': ['nome', 'telefone', 'email', 'regiao_sigla', 'cidade_nome', 'tipo', 'origem_contato', 'instagram', 'prioridade', 'grau_influencia', 'frequencia_relacionamento', 'status', 'observacoes'],
            'redirect': 'liderancas:apoiador_list',
            'label': 'Apoiadores',
        },
    }

    config = model_config.get(entidade_tipo)
    if not config:
        messages.error(request, 'Tipo de importação inválido.')
        return redirect('liderancas:apoiador_list')

    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        decoded = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))

        created = 0
        errors = []
        for i, row in enumerate(reader, start=2):
            try:
                nome = row.get('Nome', '').strip()
                if not nome:
                    continue

                # Resolver região e cidade
                regiao_sigla = row.get('Região', row.get('regiao_sigla', '')).strip()
                cidade_nome = row.get('Cidade', row.get('Cidade Base', row.get('cidade_nome', ''))).strip()

                regiao = Regiao.objects.filter(sigla__iexact=regiao_sigla).first()
                if not regiao:
                    errors.append(f'Linha {i}: Região "{regiao_sigla}" não encontrada')
                    continue

                cidade = Cidade.objects.filter(nome__iexact=cidade_nome, regiao=regiao).first()
                if not cidade:
                    errors.append(f'Linha {i}: Cidade "{cidade_nome}" não encontrada na região {regiao_sigla}')
                    continue

                obj_data = {
                    'nome': nome,
                    'telefone': row.get('Telefone', '').strip(),
                    'email': row.get('Email', '').strip(),
                    'instagram': row.get('Instagram', '').strip(),
                    'observacoes': row.get('Observações', row.get('Observacoes', '')).strip(),
                    'cadastrado_por': request.user,
                }

                # Resolve prioridade
                prio_map = {'Alta': 'alta', 'Média': 'media', 'Baixa': 'baixa'}
                prio_raw = row.get('Prioridade', 'media').strip()
                obj_data['prioridade'] = prio_map.get(prio_raw, prio_raw.lower())

                # Resolve frequência
                freq_map = {'Semanal': 'semanal', 'Quinzenal': 'quinzenal', 'Mensal': 'mensal', 'Eventual': 'eventual'}
                freq_raw = row.get('Frequência', row.get('Frequencia', 'mensal')).strip()
                obj_data['frequencia_relacionamento'] = freq_map.get(freq_raw, freq_raw.lower())

                if entidade_tipo == 'coordenador':
                    obj_data['cidade'] = cidade
                    obj_data['regiao'] = regiao
                    Lideranca.objects.create(papel='coordenador', **obj_data)
                elif entidade_tipo == 'cabo':
                    obj_data['cidade'] = cidade
                    obj_data['regiao'] = regiao
                    coord = Lideranca.objects.filter(papel='coordenador', regiao=regiao).first()
                    if coord:
                        obj_data['coordenador_responsavel'] = coord
                    Lideranca.objects.create(papel='cabo', **obj_data)
                elif entidade_tipo == 'apoiador':
                    obj_data['cidade'] = cidade
                    obj_data['regiao'] = regiao
                    tipo_map = dict((v, k) for k, v in Lideranca.TIPO_CHOICES)
                    tipo_raw = row.get('Tipo', '').strip()
                    obj_data['tipo'] = tipo_map.get(tipo_raw, tipo_raw.lower() if tipo_raw else 'comunitario')
                    obj_data['origem_contato'] = row.get('Origem', '').strip()
                    infl_map = {'Alto': 'alto', 'Médio': 'medio', 'Baixo': 'baixo'}
                    infl_raw = row.get('Influência', row.get('Influencia', 'medio')).strip()
                    obj_data['grau_influencia'] = infl_map.get(infl_raw, infl_raw.lower())
                    status_map = {'Ativo': 'ativo', 'Inativo': 'inativo', 'Pendente': 'pendente'}
                    status_raw = row.get('Status', 'ativo').strip()
                    obj_data['status'] = status_map.get(status_raw, status_raw.lower())
                    Lideranca.objects.create(papel='apoiador', **obj_data)

                created += 1
            except Exception as e:
                errors.append(f'Linha {i}: {str(e)}')

        if created:
            messages.success(request, f'{created} registro(s) importado(s) com sucesso.')
        if errors:
            messages.warning(request, f'{len(errors)} erro(s) na importação: ' + '; '.join(errors[:5]))
        return redirect(config['redirect'])

    return render(request, 'liderancas/csv_import.html', {
        'entidade_tipo': entidade_tipo,
        'label': config['label'],
        'fields': config['fields'],
    })


# ==================== DASHBOARD ====================

@secao_required('liderancas:lista')
def dashboard(request):
    now = timezone.now()
    last_7 = now - timedelta(days=7)
    last_30 = now - timedelta(days=30)

    # Totais
    total_coord = Lideranca.objects.filter(papel='coordenador').count()
    total_cabos = Lideranca.objects.filter(papel='cabo').count()
    total_apoiadores = Lideranca.objects.aprovados().filter(papel='apoiador').count()

    # Apoiadores por tipo
    apoiadores_por_tipo = list(
        Lideranca.objects.aprovados().filter(papel='apoiador').values('tipo').annotate(total=Count('id')).order_by('-total')
    )
    tipo_map = dict(Lideranca.TIPO_CHOICES)
    for item in apoiadores_por_tipo:
        item['label'] = tipo_map.get(item['tipo'], item['tipo'])

    # Apoiadores por status
    apoiadores_por_status = list(
        Lideranca.objects.aprovados().filter(papel='apoiador').values('status').annotate(total=Count('id')).order_by('-total')
    )
    status_map = dict(Lideranca.STATUS_CHOICES)
    for item in apoiadores_por_status:
        item['label'] = status_map.get(item['status'], item['status'])

    # Por região (top 10)
    apoiadores_por_regiao = list(
        Lideranca.objects.aprovados().filter(papel='apoiador').values('cidade__regiao__sigla').annotate(total=Count('id')).order_by('-total')[:10]
    )

    # Interações recentes
    interacoes_7d = InteracaoLog.objects.filter(data__gte=last_7).count()
    interacoes_30d = InteracaoLog.objects.filter(data__gte=last_30).count()

    # Últimas interações
    ultimas_interacoes = InteracaoLog.objects.select_related(
        'registrado_por', 'lideranca'
    )[:10]

    # Sem contato há mais de 30 dias
    sem_contato_apoiadores = Lideranca.objects.aprovados().filter(papel='apoiador').annotate(
        ultima=Max('interacoes__data')
    ).filter(
        Q(ultima__lt=last_30) | Q(ultima__isnull=True)
    ).count()

    # Resumo da Semana (o placar do ciclo de relacionamento)
    contatos_alcancados_7d = (
        InteracaoLog.objects.filter(data__gte=last_7, lideranca__isnull=False).values('lideranca').distinct().count()
    )
    from datetime import date
    dias_eleicao = (date(2026, 10, 4) - now.date()).days

    return render(request, 'liderancas/dashboard.html', {
        'contatos_alcancados_7d': contatos_alcancados_7d,
        'dias_eleicao': dias_eleicao,
        'total_coord': total_coord,
        'total_cabos': total_cabos,
        'total_apoiadores': total_apoiadores,
        'apoiadores_por_tipo': apoiadores_por_tipo,
        'apoiadores_por_status': apoiadores_por_status,
        'apoiadores_por_regiao': apoiadores_por_regiao,
        'interacoes_7d': interacoes_7d,
        'interacoes_30d': interacoes_30d,
        'ultimas_interacoes': ultimas_interacoes,
        'sem_contato_apoiadores': sem_contato_apoiadores,
    })


# ==================== API ====================

api_cidades = core_api_cidades
api_regioes_cidades = core_api_regioes_cidades

# Cada tipo de registro de rede está sob a sua seção de permissão (CLAUDE.md §3.7).
# A limpeza com IA que GRAVA no registro precisa respeitar essa fronteira — senão
# vira escrita IDOR (qualquer autenticado sobrescreve observações por pk).
IA_LIMPAR_MODELOS = {
    'lideranca': (Lideranca, 'liderancas:lista'),
    'voluntario': (Voluntario, 'equipes:mobilizacao'),
}


@login_required_view
def api_limpar_texto(request):
    """Revisa o campo Observações com IA (Claude) e devolve a versão limpa.
    Back-office: usado pelos formulários de Leads e Mobilização. Requer
    ANTHROPIC_API_KEY no servidor; online apenas."""
    import json as _json
    from .ia import limpar_texto, IANaoConfigurada, IAError
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido.'}, status=405)
    # Operação que gasta tokens: só para quem tem alguma seção que usa a limpeza.
    if not any(request.user.pode_acessar(secao)
               for _m, secao in IA_LIMPAR_MODELOS.values()):
        return JsonResponse({'error': 'Acesso restrito'}, status=403)
    try:
        payload = _json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    texto = (payload.get('text') or '').strip()
    if not texto:
        return JsonResponse({'error': 'Nada para limpar.'}, status=400)
    try:
        return JsonResponse({'text': limpar_texto(texto)})
    except IANaoConfigurada:
        return JsonResponse({'error': 'Limpeza com IA não configurada no servidor.'}, status=503)
    except IAError:
        return JsonResponse({'error': 'Não foi possível limpar agora. Tente novamente.'}, status=502)


@login_required_view
def api_limpar_salvar(request):
    """Revisa o campo Observações de UM registro com IA e GRAVA na hora.
    Usado pelos pop-ups de Observações nas listas de Leads e Mobilização."""
    import json as _json
    from .ia import limpar_texto, IANaoConfigurada, IAError
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido.'}, status=405)
    try:
        payload = _json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    entrada = IA_LIMPAR_MODELOS.get((payload.get('tipo') or '').strip())
    pk = payload.get('pk')
    if not entrada or not pk:
        return JsonResponse({'error': 'Registro inválido.'}, status=400)
    Model, secao = entrada
    if not request.user.pode_acessar(secao):
        return JsonResponse({'error': 'Acesso restrito'}, status=403)
    obj = Model.objects.filter(pk=pk).first()
    if not obj:
        return JsonResponse({'error': 'Registro não encontrado.'}, status=404)
    original = (obj.observacoes or '').strip()
    if not original:
        return JsonResponse({'error': 'Sem observações para limpar.'}, status=400)
    try:
        novo = limpar_texto(original)
    except IANaoConfigurada:
        return JsonResponse({'error': 'Limpeza com IA não configurada no servidor.'}, status=503)
    except IAError:
        return JsonResponse({'error': 'Não foi possível limpar agora. Tente novamente.'}, status=502)
    if novo and novo != original:
        obj.observacoes = novo
        obj.save(update_fields=['observacoes'])
    return JsonResponse({'text': obj.observacoes})


# ==================== MOBILIZAÇÃO ====================

VOLUNTARIO_CSV_HEADER = ['Nome', 'Telefone', 'Região', 'Cidade', 'Endereço',
                         'Disponibilidades', 'Observações', 'Cadastrado por', 'Data']


def _busca_vol_q(busca):
    from django.db import connection
    ic = 'unaccent__icontains' if connection.vendor == 'postgresql' else 'icontains'
    return (
        Q(**{f'nome__{ic}': busca}) | Q(telefone__icontains=busca) |
        Q(**{f'cidade__nome__{ic}': busca}) | Q(**{f'observacoes__{ic}': busca})
    )


def _voluntarios_csv(qs, filename):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.charset = 'utf-8-sig'
    writer = csv.writer(response)
    writer.writerow(VOLUNTARIO_CSV_HEADER)
    disp_map = dict(Voluntario.DISPONIBILIDADE_CHOICES)
    for v in qs:
        disps = ', '.join(disp_map.get(d, d) for d in (v.disponibilidades or []))
        writer.writerow([
            v.nome, v.telefone,
            v.regiao.sigla if v.regiao_id else '', v.cidade.nome if v.cidade_id else '',
            v.endereco, disps, v.observacoes,
            v.cadastrado_por.get_full_name() if v.cadastrado_por else '',
            v.created_at.strftime('%d/%m/%Y %H:%M'),
        ])
    return response


@secao_required('equipes:mobilizacao')
def mobilizacao_list(request):
    """Lista de voluntários (Mobilização) — espelha a lista de Lideranças,
    com filtros, ordenação, ações em massa e moderação."""
    qs = Voluntario.objects.select_related('regiao', 'cidade', 'cadastrado_por')

    busca = request.GET.get('busca', '')
    regioes_sel = [r for r in request.GET.getlist('regiao') if r]
    disps_sel = [d for d in request.GET.getlist('disponibilidade') if d]
    cidade_id = request.GET.get('cidade', '')
    aprovacao = request.GET.get('aprovacao', '')

    if aprovacao in ('pendente', 'aprovado', 'rejeitado'):
        qs = qs.filter(aprovacao=aprovacao)
    else:
        qs = qs.exclude(aprovacao='rejeitado')

    if busca:
        qs = qs.filter(_busca_vol_q(busca))
    if regioes_sel:
        qs = qs.filter(regiao_id__in=regioes_sel)
    if cidade_id:
        qs = qs.filter(cidade_id=cidade_id)
    if disps_sel:
        from django.db.models.functions import Cast
        from django.db.models import TextField
        qs = qs.annotate(_disp_txt=Cast('disponibilidades', TextField()))
        dq = Q()
        for d in disps_sel:
            dq |= Q(_disp_txt__icontains='"%s"' % d)  # match exato pelo valor entre aspas
        qs = qs.filter(dq)

    qs, current_sort, current_dir = _apply_sorting(
        request, qs, ['nome', 'cidade__nome', 'regiao__sigla', 'created_at'],
    )

    if request.GET.get('export') == 'csv':
        return _voluntarios_csv(qs, 'mobilizacao.csv')

    paginator, page_obj = _paginate(request, qs)

    cidades_filtro = Cidade.objects.filter(regiao_id__in=regioes_sel).order_by('nome') if regioes_sel else []

    # Chips de filtros ativos
    base_params = request.GET.copy()
    base_params.pop('page', None)
    base_params.pop('export', None)
    filtros_ativos = []

    def _chip(param, label, value, display):
        sem = base_params.copy()
        sem.setlist(param, [v for v in sem.getlist(param) if v != value])
        filtros_ativos.append({'label': label, 'display': display or value, 'remove_qs': sem.urlencode()})

    for r in regioes_sel:
        _chip('regiao', 'Região', r, Regiao.objects.filter(id=r).values_list('sigla', flat=True).first() or r)
    for d in disps_sel:
        _chip('disponibilidade', 'Disponib.', d, dict(Voluntario.DISPONIBILIDADE_CHOICES).get(d, d))
    if busca:
        _chip('busca', 'Busca', busca, busca)
    if cidade_id:
        _chip('cidade', 'Cidade', cidade_id, Cidade.objects.filter(id=cidade_id).values_list('nome', flat=True).first() or cidade_id)
    if aprovacao:
        _chip('aprovacao', 'Aprovação', aprovacao, dict(Voluntario._meta.get_field('aprovacao').choices).get(aprovacao, aprovacao))

    try:
        per_page = int(request.GET.get('per_page', 50))
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 50

    qs_params = request.GET.copy()
    qs_params.pop('page', None)
    sort_base = request.GET.copy()
    sort_base.pop('page', None)
    sort_base.pop('sort', None)
    sort_base.pop('dir', None)

    return render(request, 'liderancas/mobilizacao_list.html', {
        'page_obj': page_obj,
        'total': paginator.count,
        'total_geral': Voluntario.objects.count(),
        'regioes': Regiao.objects.all().order_by('sigla'),
        'regioes_sel': regioes_sel,
        'cidades_filtro': cidades_filtro,
        'cidade_filtro': cidade_id,
        'disponibilidade_choices': Voluntario.DISPONIBILIDADE_CHOICES,
        'disps_sel': disps_sel,
        'busca': busca,
        'aprovacao_filtro': aprovacao,
        'filtros_ativos': filtros_ativos,
        'pode_aprovar': request.user.pode_acessar('equipes:aprovar'),
        'pendentes_total': Voluntario.objects.filter(aprovacao='pendente').count(),
        'rejeitados_total': Voluntario.objects.filter(aprovacao='rejeitado').count(),
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTIONS,
        'query_string': qs_params.urlencode(),
        'qs_sort_base': sort_base.urlencode(),
        'current_sort': current_sort,
        'current_dir': current_dir,
    })


@secao_required('equipes:mobilizacao')
def mobilizacao_bulk(request):
    """Ações em massa sobre voluntários (exportar/excluir + aprovar/rejeitar)."""
    nxt = request.POST.get('next', '')
    back = redirect(nxt if nxt.startswith('/') else 'liderancas:mobilizacao_list')
    if request.method != 'POST':
        return back
    ids = request.POST.getlist('selected_ids')
    action = request.POST.get('bulk_action', '')
    if not ids:
        messages.warning(request, 'Nenhum voluntário selecionado.')
        return back
    qs = Voluntario.objects.filter(pk__in=ids)

    if action == 'export_csv':
        return _voluntarios_csv(qs.select_related('regiao', 'cidade', 'cadastrado_por'),
                                'mobilizacao_selecionados.csv')
    elif action == 'delete':
        n = 0
        for o in qs:
            o.soft_delete(user=request.user)
            n += 1
        messages.success(request, f'{n} voluntário(s) removido(s).')
    elif action in ('aprovar', 'rejeitar'):
        if not request.user.pode_acessar('equipes:aprovar'):
            messages.error(request, 'Você não tem permissão para aprovar/rejeitar voluntários.')
            return back
        if action == 'aprovar':
            n = qs.exclude(aprovacao='aprovado').update(
                aprovacao='aprovado', aprovado_por=request.user,
                aprovado_em=timezone.now(), motivo_rejeicao='',
            )
            messages.success(request, f'{n} voluntário(s) aprovado(s).')
        else:
            motivo = request.POST.get('motivo_rejeicao', '').strip()
            n = qs.exclude(aprovacao='rejeitado').update(
                aprovacao='rejeitado', aprovado_por=request.user,
                aprovado_em=timezone.now(), motivo_rejeicao=motivo,
            )
            messages.success(request, f'{n} voluntário(s) rejeitado(s).')
    else:
        messages.error(request, 'Ação inválida.')
    return back


@secao_required('equipes:mobilizacao')
def mobilizacao_create(request):
    if request.method == 'POST':
        form = VoluntarioForm(request.POST)
        if form.is_valid():
            vol = form.save(commit=False)
            vol.cadastrado_por = request.user
            vol.save()
            messages.success(request, 'Voluntário cadastrado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:mobilizacao_list')
    else:
        form = VoluntarioForm()
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/mobilizacao_form.html', {
        'form': form,
        'titulo': 'Novo Voluntário',
    })


@secao_required('equipes:mobilizacao')
def mobilizacao_edit(request, pk):
    vol = get_object_or_404(Voluntario, pk=pk)
    if request.method == 'POST':
        form = VoluntarioForm(request.POST, instance=vol)
        if form.is_valid():
            form.save()
            messages.success(request, 'Voluntário atualizado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:mobilizacao_list')
    else:
        form = VoluntarioForm(instance=vol)
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/mobilizacao_form.html', {
        'form': form,
        'titulo': f'Editar: {vol.nome}',
    })


@secao_required('equipes:mobilizacao')
def mobilizacao_delete(request, pk):
    vol = get_object_or_404(Voluntario, pk=pk)
    if request.method == 'POST':
        vol.soft_delete(user=request.user)
        messages.success(request, 'Voluntário removido com sucesso.')
    return redirect('liderancas:mobilizacao_list')
