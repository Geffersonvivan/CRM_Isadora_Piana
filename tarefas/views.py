import json
from datetime import date, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, F, Count
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse, NoReverseMatch
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from core.views import api_cidades as core_api_cidades
from usuarios.views import secao_required
from liderancas.models import Cidade, Regiao, Lideranca
from usuarios.models import Usuario
from .models import Tarefa, Comentario, TarefaHistorico, AnexoComentario, ItemChecklist
from notificacoes.views import (
    criar_notificacoes_mencao, criar_notificacao_resposta,
    criar_notificacao_atribuicao, criar_notificacao_participante,
    criar_notificacao_mudanca,
)
from .forms import TarefaForm, ComentarioForm


# ── Helpers ──────────────────────────────────────────────────────

def _tarefas_ativas():
    """Queryset base: apenas tarefas não excluídas."""
    return Tarefa.objects.filter(excluida_em__isnull=True)


def _user_can_access(user, tarefa):
    """Verifica se o usuário pode acessar/editar a tarefa.
    Regra: só as áreas marcadas. Nenhuma área marcada = não vê nenhuma tarefa
    (mesmo critério das seções). Admin/superuser veem tudo."""
    if user.perfil == 'admin' or user.is_superuser:
        return True
    areas = getattr(user, 'areas_tarefas', None) or []
    return bool(areas) and tarefa.tipo in areas


def _multi(request, key):
    """Lê um parâmetro multi-valor da query (separado por vírgula), sem vazios."""
    return [v for v in (x.strip() for x in request.GET.get(key, '').split(',')) if v]


def _lideranca_edit_url(contato):
    """URL da ficha/edição do contato conforme o papel (apoiador/coordenador/cabo)."""
    if not contato:
        return ''
    try:
        return reverse(f'liderancas:{contato.papel}_edit', args=[contato.pk])
    except NoReverseMatch:
        return ''


def _serialize_item_checklist(i):
    """Serializa um ItemChecklist para o front."""
    return {
        'id': i.id,
        'texto': i.texto,
        'concluido': i.concluido,
        'ordem': i.ordem,
        'vira_tarefa_id': i.vira_tarefa_id or None,
    }


def _filtrar_por_usuario(queryset, user):
    """Aplica filtro de permissão no queryset.
    Regra: só as áreas marcadas. Nenhuma área marcada = nenhuma tarefa visível
    (mesmo critério das seções). Admin/superuser veem tudo."""
    if user.perfil == 'admin' or user.is_superuser:
        return queryset
    areas = getattr(user, 'areas_tarefas', None) or []
    if not areas:
        return queryset.none()
    return queryset.filter(tipo__in=areas).distinct()


def _registrar_historico(tarefa, user, campo, anterior, novo):
    """Registra alteração no histórico."""
    if str(anterior) != str(novo):
        TarefaHistorico.objects.create(
            tarefa=tarefa,
            usuario=user,
            campo=campo,
            valor_anterior=str(anterior) if anterior else '',
            valor_novo=str(novo) if novo else '',
        )


def _iniciais(nome):
    """Retorna até 2 iniciais maiúsculas de um nome."""
    parts = nome.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    elif parts:
        return parts[0][:2].upper()
    return '??'


def _anotar_coordenadores_cabos(tarefas):
    """Anota coordenador_nome, cabos_nomes e listas com iniciais nas tarefas (evita N+1)."""
    regiao_ids = set(t.regiao_id for t in tarefas if t.regiao_id)
    coord_por_regiao = {}
    if regiao_ids:
        for c in Lideranca.objects.filter(papel='coordenador', regiao_id__in=regiao_ids):
            coord_por_regiao.setdefault(c.regiao_id, []).append(c.nome)

    # cabos já vem via prefetch_related('cabos')
    for t in tarefas:
        coord_nomes = coord_por_regiao.get(t.regiao_id, [])
        t.coordenador_nome = ', '.join(coord_nomes)
        t.coordenadores_list = [{'nome': n, 'initials': _iniciais(n)} for n in coord_nomes]
        cabos = list(t.cabos.all())
        t.cabos_nomes = ', '.join(c.nome for c in cabos)
        t.cabos_list = [{'nome': c.nome, 'initials': _iniciais(c.nome)} for c in cabos]


# ── CRUD views ───────────────────────────────────────────────────

@secao_required('demandas:tarefas')
def tarefa_create(request):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    contato_obj = None
    if request.method == 'POST':
        form = TarefaForm(request.POST, user=request.user)
        if form.is_valid():
            tarefa = form.save(commit=False)
            tarefa.regiao = form.cleaned_data.get('regiao')
            tarefa.cadastrado_por = request.user
            tarefa.save()
            form.save_m2m()
            # Registrar criação no histórico
            TarefaHistorico.objects.create(
                tarefa=tarefa,
                usuario=request.user,
                campo='criacao',
                valor_anterior='',
                valor_novo=tarefa.titulo,
            )
            if is_ajax:
                return JsonResponse({'success': True})
            messages.success(request, 'Tarefa criada com sucesso.')
            return redirect('tarefas:lista')
        if is_ajax:
            html = render_to_string('tarefas/_tarefa_form.html', {'form': form, 'action': request.path}, request=request)
            return JsonResponse({'success': False, 'html': html})
    else:
        # ?prazo=YYYY-MM-DD (vindo do seletor do dia na Agenda) cai no dia escolhido
        initial = {}
        if request.GET.get('prazo'):
            initial['prazo'] = request.GET['prazo']
        # ?contato=ID (vindo da planilha de lideranças): follow-up atrelado ao contato
        if request.GET.get('contato'):
            contato_obj = Lideranca.objects.filter(pk=request.GET['contato']).first()
            if contato_obj:
                initial['contato'] = contato_obj.pk
                initial['titulo'] = f'Follow-up — {contato_obj.nome}'
                if contato_obj.cidade_id:
                    initial['cidade'] = contato_obj.cidade_id
                    initial['regiao'] = contato_obj.cidade.regiao_id
        form = TarefaForm(initial=initial, user=request.user)
        if is_ajax:
            html = render_to_string('tarefas/_tarefa_form.html', {'form': form, 'action': request.path, 'contato': contato_obj}, request=request)
            return JsonResponse({'html': html})
    return render(request, 'tarefas/tarefa_form.html', {
        'form': form,
        'titulo': 'Novo follow-up' if contato_obj else 'Nova Tarefa',
        'contato': contato_obj,
        'contato_url': _lideranca_edit_url(contato_obj),
    })


@secao_required('demandas:tarefas')
def tarefa_edit(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    if request.method == 'POST':
        # Snapshot old values
        old_vals = {
            'titulo': tarefa.titulo, 'descricao': tarefa.descricao,
            'tipo': tarefa.tipo, 'fase': tarefa.fase, 'prioridade': tarefa.prioridade,
            'responsavel': tarefa.responsavel_id, 'regiao': tarefa.regiao_id,
            'cidade': tarefa.cidade_id, 'prazo': str(tarefa.prazo) if tarefa.prazo else '',
            'link': tarefa.link, 'link_reuniao': tarefa.link_reuniao,
            'observacoes': tarefa.observacoes,
        }
        form = TarefaForm(request.POST, instance=tarefa, user=request.user)
        if form.is_valid():
            tarefa = form.save(commit=False)
            tarefa.regiao = form.cleaned_data.get('regiao')
            tarefa.atualizado_por = request.user
            tarefa.save()
            form.save_m2m()
            # Register history for changed fields
            new_vals = {
                'titulo': tarefa.titulo, 'descricao': tarefa.descricao,
                'tipo': tarefa.tipo, 'fase': tarefa.fase, 'prioridade': tarefa.prioridade,
                'responsavel': tarefa.responsavel_id, 'regiao': tarefa.regiao_id,
                'cidade': tarefa.cidade_id, 'prazo': str(tarefa.prazo) if tarefa.prazo else '',
                'link': tarefa.link, 'link_reuniao': tarefa.link_reuniao,
                'observacoes': tarefa.observacoes,
            }
            for fld, old_v in old_vals.items():
                new_v = new_vals[fld]
                if str(old_v) != str(new_v):
                    _registrar_historico(tarefa, request.user, fld, old_v, new_v)
            messages.success(request, 'Tarefa atualizada com sucesso.')
            return redirect('tarefas:tarefa_detail', pk=pk)
    else:
        form = TarefaForm(instance=tarefa, user=request.user)
    return render(request, 'tarefas/tarefa_form.html', {
        'form': form,
        'titulo': f'Editar: {tarefa.titulo}',
    })


@secao_required('demandas:tarefas')
def tarefa_detail(request, pk):
    tarefa = get_object_or_404(
        Tarefa.objects.select_related('responsavel', 'regiao', 'cidade', 'cadastrado_por'),
        pk=pk,
    )
    if not _user_can_access(request.user, tarefa):
        messages.error(request, 'Sem permissão para acessar esta tarefa.')
        return redirect('tarefas:lista')
    comentarios = tarefa.comentarios.select_related('autor').all()
    form_comentario = ComentarioForm()
    return render(request, 'tarefas/tarefa_detail.html', {
        'tarefa': tarefa,
        'comentarios': comentarios,
        'form_comentario': form_comentario,
    })


@secao_required('demandas:tarefas')
def tarefa_delete(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        messages.error(request, 'Sem permissão.')
        return redirect('tarefas:lista')
    if request.method == 'POST':
        tarefa.excluida_em = timezone.now()
        tarefa.excluida_por = request.user
        tarefa.save()
        _registrar_historico(tarefa, request.user, 'excluida', 'ativa', 'excluída')
        messages.success(request, 'Tarefa movida para excluídas.')
    return redirect('tarefas:lista')


# ── Lista (principal) ────────────────────────────────────────────

@never_cache
@secao_required('demandas:tarefas')
def lista(request):
    tarefas_qs = _tarefas_ativas().select_related(
        'responsavel', 'regiao', 'cidade', 'compromisso'
    ).prefetch_related('participantes', 'cabos').annotate(
        chk_total=Count('itens_checklist', distinct=True),
        chk_done=Count('itens_checklist', filter=Q(itens_checklist__concluido=True), distinct=True),
    )

    tarefas_qs = _filtrar_por_usuario(tarefas_qs, request.user)

    # Filtros multi-seleção (server-side): OU dentro do filtro, E entre filtros.
    f_fase = _multi(request, 'fase')
    f_area = _multi(request, 'area')
    f_prio = _multi(request, 'prio')
    f_resp = _multi(request, 'resp')
    if f_fase:
        tarefas_qs = tarefas_qs.filter(fase__in=f_fase)
    if f_area:
        tarefas_qs = tarefas_qs.filter(tipo__in=f_area)
    if f_prio:
        tarefas_qs = tarefas_qs.filter(prioridade__in=f_prio)
    resp_ids = [int(x) for x in f_resp if x.isdigit()]
    if resp_ids:
        tarefas_qs = tarefas_qs.filter(responsavel_id__in=resp_ids)

    # Follow-ups de um contato específico (?contato=ID vindo da planilha)
    contato_filtro = None
    if request.GET.get('contato'):
        contato_filtro = Lideranca.objects.filter(pk=request.GET['contato']).first()
        if contato_filtro:
            tarefas_qs = tarefas_qs.filter(contato=contato_filtro)

    # Ranqueado por prazo: as que vencem antes no topo; sem prazo vão para o fim.
    # Empate mantém a ordem manual (ordem) e a prioridade como desempate.
    tarefas_qs = tarefas_qs.order_by(F('prazo').asc(nulls_last=True), 'ordem', '-prioridade')

    total_tarefas = tarefas_qs.count()

    usuarios = Usuario.objects.exclude(
        vinculo__in=['coordenador', 'cabo', 'replicador']
    ).order_by('first_name')
    regioes = Regiao.objects.all().order_by('sigla')

    # Setores que o usuário pode escolher (admin = todos; restrito = só os seus)
    user = request.user
    if user.perfil == 'admin' or user.is_superuser:
        tipo_choices = Tarefa.AREA_CHOICES
    else:
        areas = getattr(user, 'areas_tarefas', None) or []
        tipo_choices = (
            [(v, label) for v, label in Tarefa.AREA_CHOICES if v in areas]
            if areas else Tarefa.AREA_CHOICES
        )

    # Paginação no banco (LIMIT/OFFSET): materializa e anota coord/cabos só na
    # página exibida, não a base inteira antes de paginar.
    page_number = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', '50')
    if per_page == 'all':
        per_page = total_tarefas or 1
    else:
        try:
            per_page = int(per_page)
        except (ValueError, TypeError):
            per_page = 50
    paginator = Paginator(tarefas_qs, per_page)
    page_obj = paginator.get_page(page_number)
    page_obj.object_list = list(page_obj.object_list)
    _anotar_coordenadores_cabos(page_obj.object_list)
    per_page_atual = request.GET.get('per_page', '50')

    return render(request, 'tarefas/lista.html', {
        'tarefas': page_obj,
        'page_obj': page_obj,
        'per_page': per_page_atual,
        'total_tarefas': total_tarefas,
        'usuarios': usuarios,
        'tipo_choices': tipo_choices,
        'fase_choices': Tarefa.FASE_CHOICES,
        'prioridade_choices': Tarefa.PRIORIDADE_CHOICES,
        'regioes': regioes,
        'form': TarefaForm(user=request.user),
        'filtros_sel': {'fase': f_fase, 'area': f_area, 'prio': f_prio, 'resp': f_resp},
        'contato_filtro': contato_filtro,
    })


# ── Excluídas ────────────────────────────────────────────────────

@secao_required('demandas:tarefas')
def excluidas(request):
    """List soft-deleted tasks."""
    tarefas = list(_filtrar_por_usuario(Tarefa.objects.filter(
        excluida_em__isnull=False
    ), request.user).select_related(
        'responsavel', 'regiao', 'cidade', 'excluida_por'
    ).prefetch_related('participantes', 'cabos').order_by('-excluida_em'))

    _anotar_coordenadores_cabos(tarefas)

    # Paginação
    page_number = request.GET.get('page', 1)
    paginator = Paginator(tarefas, 50)
    page_obj = paginator.get_page(page_number)

    return render(request, 'tarefas/excluidas.html', {
        'tarefas': page_obj,
        'page_obj': page_obj,
    })


@secao_required('demandas:tarefas')
def concluidas(request):
    """List concluded tasks."""
    tarefas = list(_filtrar_por_usuario(Tarefa.objects.filter(
        fase='concluida',
        excluida_em__isnull=True,
    ), request.user).select_related(
        'responsavel', 'regiao', 'cidade', 'cadastrado_por'
    ).prefetch_related('participantes', 'cabos').order_by('-concluida_em'))

    _anotar_coordenadores_cabos(tarefas)

    # Paginação
    page_number = request.GET.get('page', 1)
    paginator = Paginator(tarefas, 50)
    page_obj = paginator.get_page(page_number)

    return render(request, 'tarefas/concluidas.html', {
        'tarefas': page_obj,
        'page_obj': page_obj,
    })


# ── APIs JSON ────────────────────────────────────────────────────

@secao_required('demandas:tarefas')
@require_POST
def api_mover(request):
    try:
        data = json.loads(request.body)
        tarefa_id = data.get('tarefa_id')
        nova_fase = data.get('fase')
        nova_ordem = data.get('ordem', 0)

        tarefa = Tarefa.objects.get(pk=tarefa_id)
        if not _user_can_access(request.user, tarefa):
            return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)

        old_fase = tarefa.fase
        tarefa.fase = nova_fase
        tarefa.ordem = nova_ordem

        if nova_fase == 'concluida' and not tarefa.concluida_em:
            tarefa.concluida_em = timezone.now()
        elif nova_fase != 'concluida':
            tarefa.concluida_em = None

        tarefa.atualizado_por = request.user
        tarefa.save()
        _registrar_historico(tarefa, request.user, 'fase', old_fase, nova_fase)
        return JsonResponse({'ok': True})
    except (Tarefa.DoesNotExist, json.JSONDecodeError, KeyError):
        return JsonResponse({'ok': False}, status=400)


@secao_required('demandas:tarefas')
@require_POST
def api_comentar(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    form = ComentarioForm(request.POST)
    if form.is_valid():
        comentario = form.save(commit=False)
        comentario.tarefa = tarefa
        comentario.autor = request.user
        parent_id = request.POST.get('parent_id')
        if parent_id:
            comentario.parent_id = int(parent_id)
        comentario.save()
        # Registrar no histórico
        tipo_hist = 'resposta_comentario' if comentario.parent_id else 'comentario'
        preview = comentario.texto[:80] + ('...' if len(comentario.texto) > 80 else '')
        TarefaHistorico.objects.create(
            tarefa=tarefa,
            usuario=request.user,
            campo=tipo_hist,
            valor_anterior='',
            valor_novo=preview,
        )
        # Notifications
        criar_notificacoes_mencao(comentario.texto, tarefa, comentario, request.user)
        if comentario.parent_id:
            parent_comment = Comentario.objects.select_related('autor').filter(pk=comentario.parent_id).first()
            if parent_comment:
                criar_notificacao_resposta(parent_comment, comentario, request.user)
        # Handle file attachments (max 10MB per file)
        MAX_UPLOAD_SIZE = 10 * 1024 * 1024
        anexos_data = []
        for f in request.FILES.getlist('anexos'):
            if f.size > MAX_UPLOAD_SIZE:
                continue
            anexo = AnexoComentario.objects.create(
                comentario=comentario,
                arquivo=f,
                nome_original=f.name,
                tamanho=f.size,
            )
            anexos_data.append({
                'id': anexo.id,
                'nome': anexo.nome_original,
                'url': anexo.arquivo.url,
                'tamanho': anexo.tamanho,
                'is_imagem': anexo.is_imagem,
            })
        user = request.user
        return JsonResponse({
            'ok': True,
            'id': comentario.id,
            'autor': user.get_full_name() or user.username,
            'autor_initials': (user.first_name[:1] + user.last_name[:1]).upper(),
            'texto': comentario.texto,
            'data': comentario.created_at.strftime('%d/%m/%Y %H:%M'),
            'parent_id': comentario.parent_id,
            'anexos': anexos_data,
        })
    return JsonResponse({'ok': False}, status=400)


@secao_required('demandas:tarefas')
@require_POST
def api_comentario_editar(request, pk):
    """Edit own comment."""
    comentario = get_object_or_404(Comentario, pk=pk)
    if comentario.autor != request.user:
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)
    texto = (data.get('texto') or '').strip()
    if not texto:
        return JsonResponse({'ok': False, 'error': 'Texto obrigatório'}, status=400)
    comentario.texto = texto
    comentario.save()
    return JsonResponse({'ok': True, 'texto': comentario.texto})


@secao_required('demandas:tarefas')
@require_POST
def api_comentario_excluir(request, pk):
    """Delete own comment."""
    comentario = get_object_or_404(Comentario, pk=pk)
    if comentario.autor != request.user:
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    tarefa = comentario.tarefa
    # Register in history
    TarefaHistorico.objects.create(
        tarefa=tarefa,
        usuario=request.user,
        campo='comentario_excluido',
        valor_anterior=comentario.texto[:80],
        valor_novo='',
    )
    # Delete replies too
    comentario.respostas.all().delete()
    comentario.delete()
    return JsonResponse({'ok': True})


@secao_required('demandas:tarefas')
def api_tarefa_detail(request, pk):
    tarefa = get_object_or_404(Tarefa.objects.select_related(
        'responsavel', 'regiao', 'cidade', 'cadastrado_por', 'atualizado_por', 'compromisso', 'contato'
    ), pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)

    # Nested comments: top-level + respostas
    all_comments = list(
        tarefa.comentarios.select_related('autor').order_by('created_at')
    )
    comments_by_parent = {}
    for c in all_comments:
        comments_by_parent.setdefault(c.parent_id, []).append(c)

    # Prefetch anexos
    comment_ids = [c.id for c in all_comments]
    anexos_by_comment = {}
    for a in AnexoComentario.objects.filter(comentario_id__in=comment_ids):
        anexos_by_comment.setdefault(a.comentario_id, []).append(a)

    def serialize_comment(c):
        autor_obj = c.autor
        anexos = anexos_by_comment.get(c.id, [])
        return {
            'id': c.id,
            'autor': autor_obj.get_full_name() if autor_obj else '',
            'autor_initials': ((autor_obj.first_name[:1] + autor_obj.last_name[:1]).upper()) if autor_obj else '??',
            'texto': c.texto,
            'data': c.created_at.strftime('%d/%m/%Y %H:%M'),
            'anexos': [
                {'id': a.id, 'nome': a.nome_original, 'url': a.arquivo.url,
                 'tamanho': a.tamanho, 'is_imagem': a.is_imagem}
                for a in anexos
            ],
            'respostas': [serialize_comment(r) for r in comments_by_parent.get(c.id, [])],
        }

    top_comments = comments_by_parent.get(None, [])

    participantes = list(tarefa.participantes.all())
    cabos = list(tarefa.cabos.all())

    # Coordenador
    coord_nomes = []
    if tarefa.regiao_id:
        coord_nomes = list(Lideranca.objects.filter(papel='coordenador',
            regiao_id=tarefa.regiao_id
        ).values_list('nome', flat=True))

    # Histórico
    historico = tarefa.historico.select_related('usuario').order_by('-created_at')[:50]

    # Checklist
    itens_checklist = list(tarefa.itens_checklist.all())
    checklist_concluidas = sum(1 for i in itens_checklist if i.concluido)

    return JsonResponse({
        'id': tarefa.id,
        'titulo': tarefa.titulo,
        'descricao': tarefa.descricao,
        'tipo': tarefa.tipo,
        'tipo_display': tarefa.get_tipo_display(),
        'fase': tarefa.fase,
        'fase_display': tarefa.get_fase_display(),
        'prioridade': tarefa.prioridade,
        'prioridade_display': tarefa.get_prioridade_display(),
        'responsavel_id': tarefa.responsavel_id or '',
        'responsavel_nome': tarefa.responsavel.get_full_name() if tarefa.responsavel else '',
        'participantes_ids': [p.id for p in participantes],
        'participantes_nomes': [p.get_full_name() or p.username for p in participantes],
        'participantes': [
            {'id': p.id, 'nome': p.get_full_name() or p.username, 'initials': (p.first_name[:1] + p.last_name[:1]).upper()}
            for p in participantes
        ],
        'regiao_id': tarefa.regiao_id or '',
        'regiao_nome': tarefa.regiao.sigla if tarefa.regiao else '',
        'cidade_id': tarefa.cidade_id or '',
        'cidade_nome': str(tarefa.cidade) if tarefa.cidade else '',
        'cabos_ids': [c.id for c in cabos],
        'cabos_nomes': ', '.join(c.nome for c in cabos),
        'coordenador_nome': ', '.join(coord_nomes),
        'data_hora_inicio': tarefa.data_hora_inicio.strftime('%d/%m/%Y %H:%M') if tarefa.data_hora_inicio else '',
        'data_hora_termino': tarefa.data_hora_termino.strftime('%d/%m/%Y %H:%M') if tarefa.data_hora_termino else '',
        'prazo': tarefa.prazo.isoformat() if tarefa.prazo else '',
        'prazo_display': tarefa.prazo.strftime('%d/%m/%Y') if tarefa.prazo else '',
        'concluida_em': tarefa.concluida_em.strftime('%d/%m/%Y %H:%M') if tarefa.concluida_em else '',
        'link': tarefa.link,
        'link_reuniao': tarefa.link_reuniao,
        'observacoes': tarefa.observacoes,
        'is_vencida': tarefa.is_vencida,
        'vence_hoje': tarefa.vence_hoje,
        'cadastrado_por': tarefa.cadastrado_por.get_full_name() if tarefa.cadastrado_por else '',
        'created_at': tarefa.created_at.strftime('%d/%m/%Y %H:%M'),
        'updated_at': tarefa.updated_at.strftime('%d/%m/%Y %H:%M') if tarefa.updated_at else '',
        'atualizado_por': tarefa.atualizado_por.get_full_name() if tarefa.atualizado_por else '',
        'contato_id': tarefa.contato_id or '',
        'contato_nome': tarefa.contato.nome if tarefa.contato else '',
        'contato_telefone': tarefa.contato.telefone if tarefa.contato else '',
        'contato_url': _lideranca_edit_url(tarefa.contato),
        'compromisso_id': tarefa.compromisso_id or '',
        'compromisso_titulo': tarefa.compromisso.titulo if tarefa.compromisso else '',
        'compromisso_data': tarefa.compromisso.data_hora_inicio.strftime('%d/%m/%Y %H:%M') if tarefa.compromisso else '',
        'comentarios': [serialize_comment(c) for c in top_comments],
        'historico': [
            {
                'usuario': h.usuario.get_full_name() if h.usuario else '',
                'campo': h.campo,
                'valor_anterior': h.valor_anterior,
                'valor_novo': h.valor_novo,
                'data': h.created_at.strftime('%d/%m/%Y %H:%M'),
            }
            for h in historico
        ],
        'checklist': [_serialize_item_checklist(i) for i in itens_checklist],
        'checklist_total': len(itens_checklist),
        'checklist_concluidas': checklist_concluidas,
    })


# ── Checklist da tarefa ──────────────────────────────────────────

def _checklist_payload(tarefa):
    itens = list(tarefa.itens_checklist.all())
    return {
        'ok': True,
        'checklist': [_serialize_item_checklist(i) for i in itens],
        'total': len(itens),
        'concluidas': sum(1 for i in itens if i.concluido),
    }


@secao_required('demandas:tarefas')
def api_checklist_listar(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    return JsonResponse(_checklist_payload(tarefa))


@secao_required('demandas:tarefas')
@require_POST
def api_checklist_criar(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    try:
        texto = (json.loads(request.body).get('texto') or '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'Corpo inválido'}, status=400)
    if not texto:
        return JsonResponse({'ok': False, 'error': 'Texto obrigatório'}, status=400)
    ultima = tarefa.itens_checklist.order_by('-ordem').first()
    ordem = (ultima.ordem + 1) if ultima else 0
    item = ItemChecklist.objects.create(
        tarefa=tarefa, texto=texto[:300], ordem=ordem, criado_por=request.user,
    )
    TarefaHistorico.objects.create(
        tarefa=tarefa, usuario=request.user, campo='checklist',
        valor_anterior='', valor_novo=f'Item adicionado: {item.texto[:60]}',
    )
    return JsonResponse({'ok': True, 'item': _serialize_item_checklist(item),
                         **_checklist_payload(tarefa)})


@secao_required('demandas:tarefas')
@require_POST
def api_checklist_toggle(request, item_id):
    item = get_object_or_404(ItemChecklist.objects.select_related('tarefa'), pk=item_id)
    if not _user_can_access(request.user, item.tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    item.concluido = not item.concluido
    if item.concluido:
        item.concluido_em = timezone.now()
        item.concluido_por = request.user
        TarefaHistorico.objects.create(
            tarefa=item.tarefa, usuario=request.user, campo='checklist',
            valor_anterior='', valor_novo=f'Concluído: {item.texto[:60]}',
        )
    else:
        item.concluido_em = None
        item.concluido_por = None
    item.save(update_fields=['concluido', 'concluido_em', 'concluido_por', 'updated_at'])
    return JsonResponse({'ok': True, 'concluido': item.concluido,
                         **_checklist_payload(item.tarefa)})


@secao_required('demandas:tarefas')
@require_POST
def api_checklist_editar(request, item_id):
    item = get_object_or_404(ItemChecklist.objects.select_related('tarefa'), pk=item_id)
    if not _user_can_access(request.user, item.tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    try:
        texto = (json.loads(request.body).get('texto') or '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'Corpo inválido'}, status=400)
    if not texto:
        return JsonResponse({'ok': False, 'error': 'Texto obrigatório'}, status=400)
    item.texto = texto[:300]
    item.save(update_fields=['texto', 'updated_at'])
    return JsonResponse({'ok': True, 'item': _serialize_item_checklist(item)})


@secao_required('demandas:tarefas')
@require_POST
def api_checklist_excluir(request, item_id):
    item = get_object_or_404(ItemChecklist.objects.select_related('tarefa'), pk=item_id)
    tarefa = item.tarefa
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    item.delete()
    return JsonResponse(_checklist_payload(tarefa))


@secao_required('demandas:tarefas')
@require_POST
def api_checklist_reordenar(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    try:
        ordem_ids = json.loads(request.body).get('ordem') or []
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'Corpo inválido'}, status=400)
    itens = {i.id: i for i in tarefa.itens_checklist.all()}
    to_update = []
    for pos, iid in enumerate(ordem_ids):
        it = itens.get(int(iid))
        if it and it.ordem != pos:
            it.ordem = pos
            to_update.append(it)
    if to_update:
        ItemChecklist.objects.bulk_update(to_update, ['ordem'])
    return JsonResponse(_checklist_payload(tarefa))


@secao_required('demandas:tarefas')
@require_POST
def api_checklist_virar_tarefa(request, item_id):
    """Converte o item do checklist numa Tarefa própria (herda área/território/
    responsável da tarefa-mãe). O item continua no checklist, ligado à nova tarefa."""
    item = get_object_or_404(ItemChecklist.objects.select_related('tarefa'), pk=item_id)
    origem = item.tarefa
    if not _user_can_access(request.user, origem):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    if item.vira_tarefa_id:
        return JsonResponse({'ok': False, 'error': 'Item já virou tarefa'}, status=400)
    nova = Tarefa.objects.create(
        titulo=item.texto[:200],
        tipo=origem.tipo,
        fase='a_fazer',
        prioridade=origem.prioridade,
        responsavel=origem.responsavel,
        regiao=origem.regiao,
        cidade=origem.cidade,
        cadastrado_por=request.user,
    )
    item.vira_tarefa = nova
    item.save(update_fields=['vira_tarefa', 'updated_at'])
    TarefaHistorico.objects.create(
        tarefa=origem, usuario=request.user, campo='checklist',
        valor_anterior='', valor_novo=f'Item virou tarefa: {item.texto[:60]}',
    )
    return JsonResponse({'ok': True, 'nova_tarefa_id': nova.id,
                         'item': _serialize_item_checklist(item)})


@secao_required('demandas:tarefas')
def api_tarefa_save(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    if request.method == 'POST':
        # Snapshot old values for history
        old_values = {
            'titulo': tarefa.titulo,
            'descricao': tarefa.descricao,
            'tipo': tarefa.tipo,
            'fase': tarefa.fase,
            'prioridade': tarefa.prioridade,
            'responsavel': tarefa.responsavel_id,
            'regiao': tarefa.regiao_id,
            'cidade': tarefa.cidade_id,
            'prazo': str(tarefa.prazo) if tarefa.prazo else '',
            'data_hora_inicio': str(tarefa.data_hora_inicio) if tarefa.data_hora_inicio else '',
            'data_hora_termino': str(tarefa.data_hora_termino) if tarefa.data_hora_termino else '',
            'observacoes': tarefa.observacoes,
        }
        form = TarefaForm(request.POST, instance=tarefa, user=request.user)
        if form.is_valid():
            tarefa = form.save(commit=False)
            tarefa.regiao = form.cleaned_data.get('regiao')
            tarefa.atualizado_por = request.user
            if tarefa.fase == 'concluida' and old_values['fase'] != 'concluida' and not tarefa.concluida_em:
                tarefa.concluida_em = timezone.now()
            elif tarefa.fase != 'concluida' and old_values['fase'] == 'concluida':
                tarefa.concluida_em = None
            tarefa.save()
            form.save_m2m()
            # Register history for all changed fields
            new_values = {
                'titulo': tarefa.titulo,
                'descricao': tarefa.descricao,
                'tipo': tarefa.tipo,
                'fase': tarefa.fase,
                'prioridade': tarefa.prioridade,
                'responsavel': tarefa.responsavel_id,
                'regiao': tarefa.regiao_id,
                'cidade': tarefa.cidade_id,
                'prazo': str(tarefa.prazo) if tarefa.prazo else '',
                'data_hora_inicio': str(tarefa.data_hora_inicio) if tarefa.data_hora_inicio else '',
                'data_hora_termino': str(tarefa.data_hora_termino) if tarefa.data_hora_termino else '',
                'observacoes': tarefa.observacoes,
            }
            for field, old_val in old_values.items():
                new_val = new_values[field]
                if str(old_val) != str(new_val):
                    _registrar_historico(tarefa, request.user, field, old_val, new_val)
            return JsonResponse({'ok': True})
        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
    return JsonResponse({'ok': False}, status=405)


@require_POST
@secao_required('demandas:tarefas')
def api_tarefa_patch(request, pk):
    """Update a single field of a task inline."""
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    field = data.get('field')
    value = data.get('value')

    allowed_fields = ['titulo', 'descricao', 'observacoes', 'tipo', 'fase', 'prioridade', 'responsavel', 'prazo', 'data_hora_inicio', 'data_hora_termino', 'regiao', 'cidade', 'link', 'link_reuniao']
    if field not in allowed_fields:
        return JsonResponse({'ok': False, 'error': 'Campo não permitido'}, status=400)

    if field == 'titulo':
        value = (value or '').strip()
        if not value or len(value) > 200:
            return JsonResponse({'ok': False, 'error': 'Título obrigatório (máx. 200)'}, status=400)

    if field in ('link', 'link_reuniao'):
        # Aceita colar "meet.google.com/..." sem esquema — prefixa https:// e valida.
        value = (value or '').strip()
        if value:
            if not value.startswith(('http://', 'https://')):
                value = 'https://' + value
            from django.core.validators import URLValidator
            from django.core.exceptions import ValidationError
            try:
                URLValidator()(value)
            except ValidationError:
                return JsonResponse({'ok': False, 'error': 'Link inválido'}, status=400)

    old_fase = tarefa.fase
    old_value = getattr(tarefa, field + '_id' if field in ('responsavel', 'regiao', 'cidade') else field, '')

    if field == 'regiao':
        if value:
            tarefa.regiao_id = int(value)
            tarefa.cidade = None
        else:
            tarefa.regiao = None
            tarefa.cidade = None
    elif field == 'cidade':
        if value:
            tarefa.cidade_id = int(value)
        else:
            tarefa.cidade = None
    elif field == 'responsavel':
        if value:
            tarefa.responsavel_id = int(value)
        else:
            tarefa.responsavel = None
    elif field == 'prazo':
        if value:
            tarefa.prazo = value
        else:
            tarefa.prazo = None
    elif field in ('data_hora_inicio', 'data_hora_termino'):
        if value:
            try:
                dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return JsonResponse({'ok': False, 'error': 'Formato inválido'}, status=400)
            setattr(tarefa, field, dt)
        else:
            setattr(tarefa, field, None)
    elif field == 'fase':
        tarefa.fase = value
        if value == 'concluida' and old_fase != 'concluida' and not tarefa.concluida_em:
            tarefa.concluida_em = timezone.now()
        elif value != 'concluida' and old_fase == 'concluida':
            tarefa.concluida_em = None
    else:
        setattr(tarefa, field, value)

    tarefa.atualizado_por = request.user
    tarefa.save()

    # Notifications
    if field == 'responsavel' and tarefa.responsavel:
        criar_notificacao_atribuicao(tarefa, request.user)
    if field in ('fase', 'prioridade'):
        display_map = {
            'fase': tarefa.get_fase_display(),
            'prioridade': tarefa.get_prioridade_display(),
        }
        criar_notificacao_mudanca(tarefa, request.user, field, display_map[field])

    # Registrar histórico
    _registrar_historico(tarefa, request.user, field, old_value, value)

    # Return display values
    display = value
    if field == 'tipo':
        display = tarefa.get_tipo_display()
    elif field == 'fase':
        display = tarefa.get_fase_display()
    elif field == 'prioridade':
        display = tarefa.get_prioridade_display()
    elif field == 'responsavel':
        display = tarefa.responsavel.get_full_name() if tarefa.responsavel else ''
    elif field == 'prazo':
        display = tarefa.prazo.strftime('%d/%m/%Y') if tarefa.prazo else ''
    elif field == 'data_hora_inicio':
        display = tarefa.data_hora_inicio.strftime('%d/%m/%Y %H:%M') if tarefa.data_hora_inicio else ''
    elif field == 'data_hora_termino':
        display = tarefa.data_hora_termino.strftime('%d/%m/%Y %H:%M') if tarefa.data_hora_termino else ''

    extra = {}
    if field in ('regiao', 'cidade'):
        tarefa.refresh_from_db()
        if field == 'regiao':
            display = tarefa.regiao.sigla if tarefa.regiao else ''
            coords = list(Lideranca.objects.filter(papel='coordenador', regiao_id=tarefa.regiao_id).values_list('nome', flat=True)) if tarefa.regiao_id else []
            extra['coordenador'] = ', '.join(coords)
            extra['coord_list'] = [{'nome': n, 'initials': _iniciais(n)} for n in coords]
            extra['has_cabos'] = tarefa.cabos.exists()
        elif field == 'cidade':
            display = str(tarefa.cidade) if tarefa.cidade else ''
            extra['has_cabos'] = tarefa.cabos.exists()

    return JsonResponse({'ok': True, 'display': display, 'value': value or '', **extra})


@require_POST
@secao_required('demandas:tarefas')
def api_tarefa_clear_cabos(request, pk):
    """Clear cabos M2M after user confirms."""
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)
    old_cabos = ', '.join(tarefa.cabos.values_list('nome', flat=True))
    tarefa.cabos.clear()
    _registrar_historico(tarefa, request.user, 'cabos', old_cabos, '')
    return JsonResponse({'ok': True})


@require_POST
@secao_required('demandas:tarefas')
def api_tarefa_create_inline(request):
    """Create a task inline with just a title."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    titulo = (data.get('titulo') or '').strip()
    if not titulo or len(titulo) > 200:
        return JsonResponse({'ok': False, 'error': 'Título obrigatório (máx. 200 caracteres)'}, status=400)

    tarefa = Tarefa.objects.create(
        titulo=titulo,
        fase='a_fazer',
        prioridade='media',
        tipo='outro',
        cadastrado_por=request.user,
    )

    return JsonResponse({
        'ok': True,
        'id': tarefa.id,
        'titulo': tarefa.titulo,
        'tipo': tarefa.tipo,
        'tipo_display': tarefa.get_tipo_display(),
        'fase': tarefa.fase,
        'fase_display': tarefa.get_fase_display(),
        'prioridade': tarefa.prioridade,
        'prioridade_display': tarefa.get_prioridade_display(),
    })


@require_POST
@secao_required('demandas:tarefas')
def api_tarefa_excluir(request):
    """Soft-delete one or more tasks."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    ids = data.get('ids', [])
    if not ids:
        return JsonResponse({'ok': False}, status=400)

    now = timezone.now()
    tarefas = Tarefa.objects.filter(pk__in=ids, excluida_em__isnull=True)
    tarefas = _filtrar_por_usuario(tarefas, request.user)
    count = tarefas.update(excluida_em=now, excluida_por=request.user)
    for t in Tarefa.objects.filter(pk__in=ids, excluida_em=now):
        _registrar_historico(t, request.user, 'excluida', 'ativa', 'excluída')
    return JsonResponse({'ok': True, 'count': count})


@require_POST
@secao_required('demandas:tarefas')
def api_tarefa_duplicar(request):
    """Duplicate one or more tasks."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    ids = data.get('ids', [])
    if not ids:
        return JsonResponse({'ok': False}, status=400)

    novas = []
    for tarefa in Tarefa.objects.filter(pk__in=ids, excluida_em__isnull=True).prefetch_related('participantes', 'cabos'):
        if not _user_can_access(request.user, tarefa):
            continue
        participantes = list(tarefa.participantes.all())
        cabos = list(tarefa.cabos.all())
        tarefa.pk = None
        tarefa.titulo = f'{tarefa.titulo} (cópia)'
        tarefa.fase = 'a_fazer'
        tarefa.concluida_em = None
        tarefa.cadastrado_por = request.user
        tarefa.atualizado_por = None
        tarefa.created_at = None
        tarefa.save()
        tarefa.participantes.set(participantes)
        tarefa.cabos.set(cabos)
        novas.append({'id': tarefa.id, 'titulo': tarefa.titulo})

    return JsonResponse({'ok': True, 'count': len(novas), 'tarefas': novas})


@require_POST
@secao_required('demandas:tarefas')
def api_tarefa_mover_fase(request):
    """Move tasks to a specific phase."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    ids = data.get('ids', [])
    fase = data.get('fase', '')
    valid_fases = [c[0] for c in Tarefa.FASE_CHOICES]
    if not ids or fase not in valid_fases:
        return JsonResponse({'ok': False, 'error': 'Fase inválida'}, status=400)

    now = timezone.now()
    for tarefa in Tarefa.objects.filter(pk__in=ids, excluida_em__isnull=True):
        if not _user_can_access(request.user, tarefa):
            continue
        old_fase = tarefa.fase
        tarefa.fase = fase
        tarefa.atualizado_por = request.user
        if fase == 'concluida' and not tarefa.concluida_em:
            tarefa.concluida_em = now
        elif fase != 'concluida':
            tarefa.concluida_em = None
        tarefa.save()
        _registrar_historico(tarefa, request.user, 'fase', old_fase, fase)

    return JsonResponse({'ok': True, 'count': len(ids)})


@require_POST
@secao_required('demandas:tarefas')
def api_tarefa_restaurar(request):
    """Restore soft-deleted tasks."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    ids = data.get('ids', [])
    if not ids:
        return JsonResponse({'ok': False}, status=400)

    Tarefa.objects.filter(pk__in=ids, excluida_em__isnull=False).update(
        excluida_em=None,
        excluida_por=None,
    )
    return JsonResponse({'ok': True, 'count': len(ids)})


@require_POST
@secao_required('demandas:tarefas')
def api_tarefa_excluir_permanente(request):
    """Permanently delete tasks."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    ids = data.get('ids', [])
    if not ids:
        return JsonResponse({'ok': False}, status=400)

    Tarefa.objects.filter(pk__in=ids, excluida_em__isnull=False).delete()
    return JsonResponse({'ok': True, 'count': len(ids)})


api_cidades = core_api_cidades


@secao_required('demandas:tarefas')
def api_cabos_por_cidade(request, cidade_id):
    cabos = Lideranca.objects.filter(papel='cabo', cidade_id=cidade_id).values('id', 'nome').order_by('nome')
    return JsonResponse(list(cabos), safe=False)


@require_POST
@secao_required('demandas:tarefas')
def api_tarefa_patch_participantes(request, pk):
    """Update participantes M2M for a task."""
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    old_ids = set(tarefa.participantes.values_list('id', flat=True))
    ids = data.get('ids', [])
    tarefa.participantes.set(ids)
    participantes = list(tarefa.participantes.all())
    # Notify newly added participants
    new_ids = set(ids) - old_ids
    for p in participantes:
        if p.id in new_ids:
            criar_notificacao_participante(tarefa, p, request.user)
    _registrar_historico(tarefa, request.user, 'participantes', str(list(old_ids)), str(ids))
    return JsonResponse({
        'ok': True,
        'participantes': [
            {'id': p.id, 'nome': p.get_full_name() or p.username, 'initials': (p.first_name[:1] + p.last_name[:1]).upper()}
            for p in participantes
        ],
    })


@require_POST
@secao_required('demandas:tarefas')
def api_tarefa_patch_cabos(request, pk):
    """Update cabos M2M for a task."""
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    old_nomes = list(tarefa.cabos.values_list('nome', flat=True))
    ids = data.get('ids', [])
    tarefa.cabos.set(ids)
    nomes = list(tarefa.cabos.values_list('nome', flat=True))
    _registrar_historico(tarefa, request.user, 'cabos', ', '.join(old_nomes), ', '.join(nomes))
    cabos_list = [{'nome': n, 'initials': _iniciais(n)} for n in nomes]
    return JsonResponse({'ok': True, 'display': ', '.join(nomes), 'cabos_list': cabos_list})


@secao_required('demandas:tarefas')
@require_POST
def api_tarefa_agendar(request, pk):
    """Cria um compromisso na Agenda a partir de uma tarefa."""
    from agenda.models import Compromisso

    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    dt = data.get('data')
    hora_inicio = data.get('hora_inicio')
    hora_fim = data.get('hora_fim')

    if not dt or not hora_inicio or not hora_fim:
        return JsonResponse({'ok': False, 'error': 'Data e horários são obrigatórios'}, status=400)

    try:
        data_hora_inicio = timezone.make_aware(datetime.strptime(f'{dt} {hora_inicio}', '%Y-%m-%d %H:%M'))
        data_hora_fim = timezone.make_aware(datetime.strptime(f'{dt} {hora_fim}', '%Y-%m-%d %H:%M'))
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Formato de data/hora inválido'}, status=400)

    regiao_id = tarefa.regiao_id or data.get('regiao_id')
    cidade_id = tarefa.cidade_id or data.get('cidade_id')
    if not regiao_id or not cidade_id:
        return JsonResponse({'ok': False, 'error': 'Região e cidade são obrigatórios'}, status=400)

    # Mapear tipo da tarefa → tipo do compromisso
    tipo_map = {
        'reuniao': 'reuniao',
        'evento': 'evento',
        'visita': 'visita',
        'articulacao': 'reuniao',
        'comunicacao': 'entrevista',
        'captacao': 'visita',
        'outro': 'reuniao',
    }

    compromisso = Compromisso.objects.create(
        titulo=tarefa.titulo,
        descricao=tarefa.descricao,
        data_hora_inicio=data_hora_inicio,
        data_hora_fim=data_hora_fim,
        tipo=tipo_map.get(tarefa.tipo, 'reuniao'),
        regiao_id=regiao_id,
        cidade_id=cidade_id,
        endereco=data.get('endereco', ''),
        prioridade=tarefa.prioridade if tarefa.prioridade != 'urgente' else 'alta',
        status='pendente',
        observacoes=tarefa.observacoes,
        cadastrado_por=request.user,
    )

    tarefa.compromisso = compromisso
    tarefa.save(update_fields=['compromisso'])

    _registrar_historico(tarefa, request.user, 'compromisso_vinculado', '', compromisso.titulo)

    return JsonResponse({
        'ok': True,
        'compromisso_id': compromisso.pk,
        'compromisso_titulo': compromisso.titulo,
        'compromisso_data': compromisso.data_hora_inicio.strftime('%d/%m/%Y %H:%M'),
    })


@secao_required('demandas:tarefas')
@require_POST
def api_tarefa_desagendar(request, pk):
    """Remove o vínculo entre tarefa e compromisso (não exclui o compromisso)."""
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if not _user_can_access(request.user, tarefa):
        return JsonResponse({'ok': False, 'error': 'Sem permissão'}, status=403)

    if tarefa.compromisso:
        titulo_ant = tarefa.compromisso.titulo
        tarefa.compromisso = None
        tarefa.save(update_fields=['compromisso'])
        _registrar_historico(tarefa, request.user, 'compromisso_desvinculado', titulo_ant, '')

    return JsonResponse({'ok': True})

