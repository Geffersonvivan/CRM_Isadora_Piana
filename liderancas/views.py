import csv
import io
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Max, Count
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from core.views import api_cidades as core_api_cidades
from usuarios.views import admin_required, secao_required
from .models import CoordenadorRegional, CaboEleitoral, Apoiador, Voluntario, Regiao, Cidade, InteracaoLog, Egresso, Lassberg
from .forms import CoordenadorRegionalForm, CaboEleitoralForm, ApoiadorForm, VoluntarioForm, InteracaoLogForm, EgressoForm, LassbergForm


def login_required_view(view_func):
    """Decorator que exige autenticação."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


PER_PAGE_OPTIONS = [25, 50, 100, 200]


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


# ==================== COORDENADORES ====================

@secao_required('liderancas:coordenador_regional')
def coordenador_list(request):
    coordenadores = CoordenadorRegional.objects.select_related('regiao', 'cidade_base').annotate(
        ultima_interacao=Max('interacoes__data')
    ).all()

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
        request, coordenadores, ['nome', 'regiao__sigla', 'cidade_base__nome', 'prioridade', 'created_at']
    )

    # CSV Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="coordenadores.csv"'
        response.charset = 'utf-8-sig'
        writer = csv.writer(response)
        writer.writerow(['Nome', 'Telefone', 'Email', 'Região', 'Cidade Base', 'Instagram', 'Prioridade', 'Frequência', 'Observações'])
        for c in coordenadores:
            writer.writerow([c.nome, c.telefone, c.email, c.regiao.sigla, c.cidade_base.nome, c.instagram, c.get_prioridade_display(), c.get_frequencia_relacionamento_display(), c.observacoes])
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


@secao_required('liderancas:coordenador_regional')
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


@secao_required('liderancas:coordenador_regional')
def coordenador_edit(request, pk):
    coord = get_object_or_404(CoordenadorRegional, pk=pk)
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


@secao_required('liderancas:coordenador_regional')
def coordenador_delete(request, pk):
    coord = get_object_or_404(CoordenadorRegional, pk=pk)
    if request.method == 'POST':
        coord.soft_delete(user=request.user)
        messages.success(request, 'Coordenador Regional removido com sucesso.')
    return redirect('liderancas:coordenador_list')


# ==================== CABOS ELEITORAIS ====================

@secao_required('liderancas:cabos_eleitorais')
def cabo_list(request):
    cabos = CaboEleitoral.objects.select_related('cidade', 'cidade__regiao', 'coordenador').annotate(
        ultima_interacao=Max('interacoes__data')
    ).all()

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
        request, cabos, ['nome', 'cidade__nome', 'cidade__regiao__sigla', 'coordenador__nome', 'prioridade', 'created_at']
    )

    # CSV Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="cabos_eleitorais.csv"'
        response.charset = 'utf-8-sig'
        writer = csv.writer(response)
        writer.writerow(['Nome', 'Telefone', 'Email', 'Cidade', 'Região', 'Coordenador', 'Instagram', 'Prioridade', 'Frequência', 'Observações'])
        for c in cabos:
            writer.writerow([c.nome, c.telefone, c.email, c.cidade.nome, c.cidade.regiao.sigla, c.coordenador.nome if c.coordenador else '', c.instagram, c.get_prioridade_display(), c.get_frequencia_relacionamento_display(), c.observacoes])
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


@secao_required('liderancas:cabos_eleitorais')
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


@secao_required('liderancas:cabos_eleitorais')
def cabo_edit(request, pk):
    cabo = get_object_or_404(CaboEleitoral, pk=pk)
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


@secao_required('liderancas:cabos_eleitorais')
def cabo_delete(request, pk):
    cabo = get_object_or_404(CaboEleitoral, pk=pk)
    if request.method == 'POST':
        cabo.soft_delete(user=request.user)
        messages.success(request, 'Cabo Eleitoral removido com sucesso.')
    return redirect('liderancas:cabo_list')


# ==================== APOIADORES ====================

@secao_required('liderancas:apoiadores')
def apoiador_list(request):
    apoiadores = Apoiador.objects.select_related('cidade', 'cidade__regiao', 'cadastrado_por').annotate(
        ultima_interacao=Max('interacoes__data')
    ).all()

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
            writer.writerow([a.nome, a.telefone, a.email, a.cidade.nome, a.cidade.regiao.sigla, a.get_tipo_display(), a.get_cargo_display(), a.origem_contato, a.instagram, a.get_prioridade_display(), a.get_grau_influencia_display(), a.get_frequencia_relacionamento_display(), a.get_status_display(), a.observacoes])
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
        'tipo_choices': Apoiador.TIPO_CHOICES,
        'cargo_choices': Apoiador.CARGO_CHOICES,
        'prioridade_choices': Apoiador.PRIORIDADE_CHOICES,
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


@secao_required('liderancas:apoiadores')
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


@secao_required('liderancas:apoiadores')
def apoiador_edit(request, pk):
    apoiador = get_object_or_404(Apoiador, pk=pk)
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


@secao_required('liderancas:apoiadores')
def apoiador_delete(request, pk):
    apoiador = get_object_or_404(Apoiador, pk=pk)
    user = request.user
    if not user.is_superuser and getattr(user, 'perfil', None) != 'admin':
        if apoiador.cadastrado_por != user:
            messages.error(request, 'Você não tem permissão para excluir este apoiador.')
            return redirect('liderancas:apoiador_list')
    if request.method == 'POST':
        apoiador.soft_delete(user=request.user)
        messages.success(request, 'Apoiador removido com sucesso.')
    return redirect('liderancas:apoiador_list')


# ==================== FILA DE RELACIONAMENTO ====================

# Prazo (em dias) para cada frequência de relacionamento configurada
FREQ_PRAZOS = {'semanal': 7, 'quinzenal': 15, 'mensal': 30, 'eventual': 90}


@secao_required('liderancas:fila')
def fila_relacionamento(request):
    """Contatos cujo último contato estourou a frequência configurada,
    ordenados por prioridade e tamanho do atraso."""
    agora = timezone.now()
    regiao_id = request.GET.get('regiao', '')
    tipo_filtro = request.GET.get('tipo', '')
    prioridade = request.GET.get('prioridade', '')
    busca = request.GET.get('busca', '')

    fontes = [
        ('coordenador', CoordenadorRegional.objects.select_related('regiao', 'cidade_base')),
        ('cabo', CaboEleitoral.objects.select_related('cidade', 'cidade__regiao')),
        ('apoiador', Apoiador.objects.select_related('cidade', 'cidade__regiao')),
    ]
    fila = []
    total_monitorado = 0
    for tipo, qs in fontes:
        if tipo_filtro and tipo != tipo_filtro:
            continue
        if regiao_id:
            qs = qs.filter(regiao_id=regiao_id) if tipo == 'coordenador' else qs.filter(cidade__regiao_id=regiao_id)
        if prioridade:
            qs = qs.filter(prioridade=prioridade)
        if busca:
            qs = qs.filter(Q(nome__icontains=busca) | Q(telefone__icontains=busca))
        for c in qs.annotate(ultima=Max('interacoes__data')):
            total_monitorado += 1
            prazo = FREQ_PRAZOS.get(c.frequencia_relacionamento, 30)
            dias = (agora - c.ultima).days if c.ultima else None
            if dias is not None and dias <= prazo:
                continue  # relacionamento em dia
            fila.append({
                'tipo': tipo,
                'obj': c,
                'cidade': c.cidade_base if tipo == 'coordenador' else c.cidade,
                'dias': dias,
                'prazo': prazo,
                'atraso': (dias - prazo) if dias is not None else None,
                'ultima': c.ultima,
            })

    ordem_pr = {'alta': 0, 'media': 1, 'baixa': 2}
    fila.sort(key=lambda x: (
        ordem_pr.get(x['obj'].prioridade, 1),
        0 if x['atraso'] is None else 1,
        -(x['atraso'] or 0),
    ))

    nunca = sum(1 for f in fila if f['dias'] is None)
    paginator, page_obj = _paginate(request, fila)

    qs_params = request.GET.copy()
    qs_params.pop('page', None)

    return render(request, 'liderancas/fila_relacionamento.html', {
        'page_obj': page_obj,
        'total': paginator.count,
        'total_monitorado': total_monitorado,
        'nunca': nunca,
        'regioes': Regiao.objects.all().order_by('sigla'),
        'busca': busca,
        'regiao_filtro': regiao_id,
        'tipo_filtro': tipo_filtro,
        'prioridade_filtro': prioridade,
        'query_string': qs_params.urlencode(),
    })


# ==================== EGRESSOS ====================

@secao_required('liderancas:egressos')
def egresso_list(request):
    egressos = Egresso.objects.select_related('cidade', 'cidade__regiao').annotate(
        ultima_interacao=Max('interacoes__data')
    ).all()

    busca = request.GET.get('busca', '')
    estado = request.GET.get('estado', '')
    regiao_id = request.GET.get('regiao', '')
    cidade_id = request.GET.get('cidade', '')
    curso = request.GET.get('curso', '')
    instituicao = request.GET.get('instituicao', '')

    if busca:
        egressos = egressos.filter(
            Q(nome__icontains=busca) |
            Q(telefone__icontains=busca) |
            Q(email__icontains=busca) |
            Q(cidade_nome__icontains=busca)
        )
    if estado:
        egressos = egressos.filter(estado=estado)
    if regiao_id:
        egressos = egressos.filter(cidade__regiao_id=regiao_id)
    if cidade_id:
        egressos = egressos.filter(cidade_id=cidade_id)
    if curso:
        egressos = egressos.filter(curso=curso)
    if instituicao:
        egressos = egressos.filter(instituicao=instituicao)

    egressos, current_sort, current_dir = _apply_sorting(
        request, egressos, ['nome', 'cidade_nome', 'estado', 'curso', 'instituicao', 'created_at']
    )

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="egressos.csv"'
        response.charset = 'utf-8-sig'
        writer = csv.writer(response)
        writer.writerow(['Nome', 'Telefone', 'Email', 'Redes Sociais', 'Cidade', 'UF', 'Curso', 'Instituição', 'Situação', 'Observações'])
        for e in egressos:
            writer.writerow([e.nome, e.telefone, e.email, e.instagram, e.cidade_nome, e.estado, e.curso, e.instituicao, e.situacao_curso, e.observacoes])
        return response

    paginator, page_obj = _paginate(request, egressos)

    cidades_filtro = []
    if regiao_id:
        cidades_filtro = Cidade.objects.filter(regiao_id=regiao_id).order_by('nome')

    qs_params = request.GET.copy()
    qs_params.pop('page', None)
    query_string = qs_params.urlencode()

    base_qs = Egresso.objects.all()
    return render(request, 'liderancas/egresso_list.html', {
        'page_obj': page_obj,
        'regioes': Regiao.objects.all().order_by('sigla'),
        'cidades_filtro': cidades_filtro,
        'estados': base_qs.exclude(estado='').values_list('estado', flat=True).distinct().order_by('estado'),
        'cursos': base_qs.exclude(curso='').values_list('curso', flat=True).distinct().order_by('curso'),
        'instituicoes': base_qs.exclude(instituicao='').values_list('instituicao', flat=True).distinct().order_by('instituicao'),
        'busca': busca,
        'estado_filtro': estado,
        'regiao_filtro': regiao_id,
        'cidade_filtro': cidade_id,
        'curso_filtro': curso,
        'instituicao_filtro': instituicao,
        'total': paginator.count,
        'query_string': query_string,
        'current_sort': current_sort,
        'current_dir': current_dir,
    })


@secao_required('liderancas:egressos')
def egresso_create(request):
    if request.method == 'POST':
        form = EgressoForm(request.POST)
        if form.is_valid():
            egresso = form.save(commit=False)
            egresso.cadastrado_por = request.user
            egresso.save()
            messages.success(request, 'Egresso cadastrado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:egresso_list')
    else:
        form = EgressoForm()
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/egresso_form.html', {
        'form': form,
        'titulo': 'Novo Egresso',
    })


@secao_required('liderancas:egressos')
def egresso_edit(request, pk):
    egresso = get_object_or_404(Egresso, pk=pk)
    if request.method == 'POST':
        form = EgressoForm(request.POST, instance=egresso)
        if form.is_valid():
            egresso = form.save(commit=False)
            egresso.atualizado_por = request.user
            egresso.save()
            messages.success(request, 'Egresso atualizado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:egresso_list')
    else:
        form = EgressoForm(instance=egresso)
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/egresso_form.html', {
        'form': form,
        'titulo': f'Editar: {egresso}',
    })


@secao_required('liderancas:egressos')
def egresso_delete(request, pk):
    egresso = get_object_or_404(Egresso, pk=pk)
    if request.method == 'POST':
        egresso.soft_delete(user=request.user)
        messages.success(request, 'Egresso removido com sucesso.')
    return redirect('liderancas:egresso_list')


# ==================== LASSBERG ====================

@secao_required('liderancas:lassberg')
def lassberg_list(request):
    contatos = Lassberg.objects.select_related('cidade', 'cidade__regiao').annotate(
        ultima_interacao=Max('interacoes__data')
    ).all()

    busca = request.GET.get('busca', '')
    estado = request.GET.get('estado', '')
    regiao_id = request.GET.get('regiao', '')
    cidade_id = request.GET.get('cidade', '')

    if busca:
        contatos = contatos.filter(
            Q(nome__icontains=busca) |
            Q(telefone__icontains=busca) |
            Q(email__icontains=busca) |
            Q(cidade_nome__icontains=busca)
        )
    if estado:
        contatos = contatos.filter(estado=estado)
    if regiao_id:
        contatos = contatos.filter(cidade__regiao_id=regiao_id)
    if cidade_id:
        contatos = contatos.filter(cidade_id=cidade_id)

    contatos, current_sort, current_dir = _apply_sorting(
        request, contatos, ['nome', 'cidade_nome', 'estado', 'created_at']
    )

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="lassberg.csv"'
        response.charset = 'utf-8-sig'
        writer = csv.writer(response)
        writer.writerow(['Nome', 'Telefone', 'Email', 'Cidade', 'Estado', 'Observações'])
        for c in contatos:
            writer.writerow([c.nome, c.telefone, c.email, c.cidade_nome, c.estado, c.observacoes])
        return response

    paginator, page_obj = _paginate(request, contatos)

    cidades_filtro = []
    if regiao_id:
        cidades_filtro = Cidade.objects.filter(regiao_id=regiao_id).order_by('nome')

    qs_params = request.GET.copy()
    qs_params.pop('page', None)
    query_string = qs_params.urlencode()

    return render(request, 'liderancas/lassberg_list.html', {
        'page_obj': page_obj,
        'regioes': Regiao.objects.all().order_by('sigla'),
        'cidades_filtro': cidades_filtro,
        'estados': Lassberg.objects.exclude(estado='').values_list('estado', flat=True).distinct().order_by('estado'),
        'busca': busca,
        'estado_filtro': estado,
        'regiao_filtro': regiao_id,
        'cidade_filtro': cidade_id,
        'total': paginator.count,
        'query_string': query_string,
        'current_sort': current_sort,
        'current_dir': current_dir,
    })


@secao_required('liderancas:lassberg')
def lassberg_create(request):
    if request.method == 'POST':
        form = LassbergForm(request.POST)
        if form.is_valid():
            contato = form.save(commit=False)
            contato.cadastrado_por = request.user
            contato.save()
            messages.success(request, 'Contato cadastrado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:lassberg_list')
    else:
        form = LassbergForm()
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/lassberg_form.html', {
        'form': form,
        'titulo': 'Novo Contato Lassberg',
    })


@secao_required('liderancas:lassberg')
def lassberg_edit(request, pk):
    contato = get_object_or_404(Lassberg, pk=pk)
    if request.method == 'POST':
        form = LassbergForm(request.POST, instance=contato)
        if form.is_valid():
            contato = form.save(commit=False)
            contato.atualizado_por = request.user
            contato.save()
            messages.success(request, 'Contato atualizado com sucesso.')
            if _ajax(request):
                return JsonResponse({'ok': True})
            return redirect('liderancas:lassberg_list')
    else:
        form = LassbergForm(instance=contato)
    if _ajax(request):
        return render(request, 'liderancas/_form_fields.html', {'form': form})
    return render(request, 'liderancas/lassberg_form.html', {
        'form': form,
        'titulo': f'Editar: {contato}',
    })


@secao_required('liderancas:lassberg')
def lassberg_delete(request, pk):
    contato = get_object_or_404(Lassberg, pk=pk)
    if request.method == 'POST':
        contato.soft_delete(user=request.user)
        messages.success(request, 'Contato removido com sucesso.')
    return redirect('liderancas:lassberg_list')


@secao_required('liderancas')
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

    model_map = {
        'coordenador': CoordenadorRegional,
        'cabo': CaboEleitoral,
        'apoiador': Apoiador,
        'egresso': Egresso,
        'lassberg': Lassberg,
    }
    model = model_map.get(entity_type)
    if not model:
        messages.error(request, 'Tipo inválido.')
        return redirect('liderancas:apoiador_list')

    qs = model.objects.filter(pk__in=ids)

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
                writer.writerow([a.nome, a.telefone, a.email, a.cidade.nome, a.cidade.regiao.sigla, a.get_tipo_display(), a.get_status_display(), a.get_prioridade_display()])
        elif entity_type == 'cabo':
            writer.writerow(['Nome', 'Telefone', 'Email', 'Cidade', 'Região', 'Coordenador', 'Prioridade'])
            for c in qs.select_related('cidade', 'cidade__regiao', 'coordenador'):
                writer.writerow([c.nome, c.telefone, c.email, c.cidade.nome, c.cidade.regiao.sigla, c.coordenador.nome if c.coordenador else '', c.get_prioridade_display()])
        elif entity_type == 'coordenador':
            writer.writerow(['Nome', 'Telefone', 'Email', 'Região', 'Cidade Base', 'Prioridade'])
            for c in qs.select_related('regiao', 'cidade_base'):
                writer.writerow([c.nome, c.telefone, c.email, c.regiao.sigla, c.cidade_base.nome, c.get_prioridade_display()])
        return response

    redirect_map = {
        'coordenador': 'liderancas:coordenador_list',
        'cabo': 'liderancas:cabo_list',
        'apoiador': 'liderancas:apoiador_list',
        'egresso': 'liderancas:egresso_list',
        'lassberg': 'liderancas:lassberg_list',
    }
    return redirect(redirect_map.get(entity_type, 'liderancas:apoiador_list'))


# ==================== INTERAÇÕES ====================

@secao_required('liderancas')
def interacao_add(request, entidade_tipo, pk):
    model_map = {
        'coordenador': CoordenadorRegional,
        'cabo': CaboEleitoral,
        'apoiador': Apoiador,
        'egresso': Egresso,
        'lassberg': Lassberg,
    }
    redirect_map = {
        'coordenador': 'liderancas:coordenador_list',
        'cabo': 'liderancas:cabo_list',
        'apoiador': 'liderancas:apoiador_list',
        'egresso': 'liderancas:egresso_list',
        'lassberg': 'liderancas:lassberg_list',
    }
    model = model_map.get(entidade_tipo)
    if not model:
        messages.error(request, 'Tipo de entidade inválido.')
        return redirect('liderancas:apoiador_list')

    entidade = get_object_or_404(model, pk=pk)

    if request.method == 'POST':
        form = InteracaoLogForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            setattr(log, entidade_tipo, entidade)
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
    model_map = {
        'coordenador': CoordenadorRegional,
        'cabo': CaboEleitoral,
        'apoiador': Apoiador,
        'egresso': Egresso,
        'lassberg': Lassberg,
    }
    model = model_map.get(entidade_tipo)
    if not model:
        return JsonResponse({'ok': False, 'error': 'Tipo inválido.'}, status=400)

    entidade = get_object_or_404(model, pk=pk)

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método não permitido.'}, status=405)

    form = InteracaoLogForm(request.POST)
    if form.is_valid():
        log = form.save(commit=False)
        setattr(log, entidade_tipo, entidade)
        log.registrado_por = request.user
        log.save()
        return JsonResponse({'ok': True})
    else:
        errors = {field: errs[0] for field, errs in form.errors.items()}
        return JsonResponse({'ok': False, 'errors': errors}, status=400)


@secao_required('liderancas')
def interacao_list(request, entidade_tipo, pk):
    model_map = {
        'coordenador': CoordenadorRegional,
        'cabo': CaboEleitoral,
        'apoiador': Apoiador,
        'egresso': Egresso,
        'lassberg': Lassberg,
    }
    model = model_map.get(entidade_tipo)
    if not model:
        return JsonResponse({'error': 'Tipo inválido'}, status=400)

    entidade = get_object_or_404(model, pk=pk)
    interacoes = InteracaoLog.objects.filter(**{entidade_tipo: entidade}).select_related('registrado_por')

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
            'model': CoordenadorRegional,
            'fields': ['nome', 'telefone', 'email', 'regiao_sigla', 'cidade_nome', 'instagram', 'prioridade', 'frequencia_relacionamento', 'observacoes'],
            'redirect': 'liderancas:coordenador_list',
            'label': 'Coordenadores',
        },
        'cabo': {
            'model': CaboEleitoral,
            'fields': ['nome', 'telefone', 'email', 'regiao_sigla', 'cidade_nome', 'instagram', 'prioridade', 'frequencia_relacionamento', 'observacoes'],
            'redirect': 'liderancas:cabo_list',
            'label': 'Cabos Eleitorais',
        },
        'apoiador': {
            'model': Apoiador,
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
                    obj_data['cidade_base'] = cidade
                    obj_data['regiao'] = regiao
                    CoordenadorRegional.objects.create(**obj_data)
                elif entidade_tipo == 'cabo':
                    obj_data['cidade'] = cidade
                    coord = CoordenadorRegional.objects.filter(regiao=regiao).first()
                    if coord:
                        obj_data['coordenador'] = coord
                    CaboEleitoral.objects.create(**obj_data)
                elif entidade_tipo == 'apoiador':
                    obj_data['cidade'] = cidade
                    tipo_map = dict((v, k) for k, v in Apoiador.TIPO_CHOICES)
                    tipo_raw = row.get('Tipo', '').strip()
                    obj_data['tipo'] = tipo_map.get(tipo_raw, tipo_raw.lower() if tipo_raw else 'comunitario')
                    obj_data['origem_contato'] = row.get('Origem', '').strip()
                    infl_map = {'Alto': 'alto', 'Médio': 'medio', 'Baixo': 'baixo'}
                    infl_raw = row.get('Influência', row.get('Influencia', 'medio')).strip()
                    obj_data['grau_influencia'] = infl_map.get(infl_raw, infl_raw.lower())
                    status_map = {'Ativo': 'ativo', 'Inativo': 'inativo', 'Pendente': 'pendente'}
                    status_raw = row.get('Status', 'ativo').strip()
                    obj_data['status'] = status_map.get(status_raw, status_raw.lower())
                    Apoiador.objects.create(**obj_data)

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

@secao_required('liderancas')
def dashboard(request):
    now = timezone.now()
    last_7 = now - timedelta(days=7)
    last_30 = now - timedelta(days=30)

    # Totais
    total_coord = CoordenadorRegional.objects.count()
    total_cabos = CaboEleitoral.objects.count()
    total_apoiadores = Apoiador.objects.count()

    # Apoiadores por tipo
    apoiadores_por_tipo = list(
        Apoiador.objects.values('tipo').annotate(total=Count('id')).order_by('-total')
    )
    tipo_map = dict(Apoiador.TIPO_CHOICES)
    for item in apoiadores_por_tipo:
        item['label'] = tipo_map.get(item['tipo'], item['tipo'])

    # Apoiadores por status
    apoiadores_por_status = list(
        Apoiador.objects.values('status').annotate(total=Count('id')).order_by('-total')
    )
    status_map = dict(Apoiador.STATUS_CHOICES)
    for item in apoiadores_por_status:
        item['label'] = status_map.get(item['status'], item['status'])

    # Por região (top 10)
    apoiadores_por_regiao = list(
        Apoiador.objects.values('cidade__regiao__sigla').annotate(total=Count('id')).order_by('-total')[:10]
    )

    # Interações recentes
    interacoes_7d = InteracaoLog.objects.filter(data__gte=last_7).count()
    interacoes_30d = InteracaoLog.objects.filter(data__gte=last_30).count()

    # Últimas interações
    ultimas_interacoes = InteracaoLog.objects.select_related(
        'registrado_por', 'coordenador', 'cabo', 'apoiador'
    )[:10]

    # Sem contato há mais de 30 dias
    sem_contato_apoiadores = Apoiador.objects.annotate(
        ultima=Max('interacoes__data')
    ).filter(
        Q(ultima__lt=last_30) | Q(ultima__isnull=True)
    ).count()

    return render(request, 'liderancas/dashboard.html', {
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


# ==================== MOBILIZAÇÃO ====================

@secao_required('equipes:mobilizacao')
def mobilizacao_list(request):
    voluntarios = Voluntario.objects.select_related('regiao', 'cidade', 'cadastrado_por').all()

    busca = request.GET.get('busca', '')
    regiao_id = request.GET.get('regiao', '')
    cidade_id = request.GET.get('cidade', '')
    disponibilidade = request.GET.get('disponibilidade', '')

    if busca:
        voluntarios = voluntarios.filter(
            Q(nome__icontains=busca) | Q(telefone__icontains=busca)
        )
    if regiao_id:
        voluntarios = voluntarios.filter(regiao_id=regiao_id)
    if cidade_id:
        voluntarios = voluntarios.filter(cidade_id=cidade_id)
    if disponibilidade:
        voluntarios = voluntarios.filter(disponibilidades__contains=disponibilidade)

    # Exportar CSV
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="mobilizacao.csv"'
        response.charset = 'utf-8-sig'
        writer = csv.writer(response)
        writer.writerow(['Nome', 'Telefone', 'Região', 'Cidade', 'Disponibilidades', 'Observações', 'Cadastrado por', 'Data'])
        disp_map = dict(Voluntario.DISPONIBILIDADE_CHOICES)
        for v in voluntarios:
            disps = ', '.join(disp_map.get(d, d) for d in v.disponibilidades)
            writer.writerow([
                v.nome,
                v.telefone,
                v.regiao.sigla if v.regiao else '',
                v.cidade.nome if v.cidade else '',
                disps,
                v.observacoes,
                v.cadastrado_por.get_full_name() if v.cadastrado_por else '',
                v.created_at.strftime('%d/%m/%Y %H:%M'),
            ])
        return response

    paginator, page_obj = _paginate(request, voluntarios)

    cidades_filtro = []
    if regiao_id:
        cidades_filtro = Cidade.objects.filter(regiao_id=regiao_id).order_by('nome')

    qs_params = request.GET.copy()
    qs_params.pop('page', None)

    return render(request, 'liderancas/mobilizacao_list.html', {
        'page_obj': page_obj,
        'regioes': Regiao.objects.all().order_by('sigla'),
        'cidades_filtro': cidades_filtro,
        'disponibilidade_choices': Voluntario.DISPONIBILIDADE_CHOICES,
        'busca': busca,
        'regiao_filtro': regiao_id,
        'cidade_filtro': cidade_id,
        'disponibilidade_filtro': disponibilidade,
        'total': paginator.count,
        'query_string': qs_params.urlencode(),
    })


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
        vol.delete()
        messages.success(request, 'Voluntário removido com sucesso.')
    return redirect('liderancas:mobilizacao_list')
