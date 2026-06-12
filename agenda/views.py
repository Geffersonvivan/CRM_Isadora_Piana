from django.db import models
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import render_to_string
from usuarios.views import admin_required, secao_required
from liderancas.models import CoordenadorRegional, CaboEleitoral, Apoiador
from tarefas.models import Tarefa
from .models import Compromisso, Evento, Roteiro, RoteiroPonto
from .forms import CompromissoForm, EventoForm, RoteiroForm, RoteiroPontoFormSet


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


# ==================== COMPROMISSOS ====================

@secao_required('demandas:agenda')
def compromisso_list(request):
    compromissos = Compromisso.objects.select_related('regiao', 'cidade').all()
    return render(request, 'agenda/compromisso_list.html', {
        'compromissos': compromissos,
    })


@secao_required('demandas:agenda')
def compromisso_create(request):
    if request.method == 'POST' and _is_ajax(request):
        form = CompromissoForm(request.POST)
        if form.is_valid():
            comp = form.save(commit=False)
            comp.cadastrado_por = request.user
            comp.save()
            form.save_m2m()
            interacoes = comp.gerar_interacoes(request.user)
            return JsonResponse({'success': True, 'interacoes': interacoes})
        html = render_to_string('agenda/_compromisso_form.html', {
            'form': form, 'titulo': 'Novo Compromisso',
        }, request=request)
        return JsonResponse({'success': False, 'html': html})

    if _is_ajax(request):
        # Pré-preenchimento vindo das listas de contatos (?apoiador=ID etc.)
        import json as json_mod
        initial, selecionados = {}, None
        contato, chave = None, None
        for param, model in (('apoiador', Apoiador), ('cabo', CaboEleitoral), ('coordenador', CoordenadorRegional)):
            if request.GET.get(param):
                contato = model.objects.filter(pk=request.GET[param]).first()
                chave = param
                break
        if contato:
            cidade_ref = getattr(contato, 'cidade', None) or getattr(contato, 'cidade_base', None)
            initial = {'tipo': 'visita', 'titulo': f'Visita — {contato.nome}'}
            if cidade_ref:
                initial['regiao'] = cidade_ref.regiao_id
                initial['cidade'] = cidade_ref.pk
            plural = {'apoiador': 'apoiadores', 'cabo': 'cabos', 'coordenador': 'coordenadores'}[chave]
            selecionados = {'coordenadores': [], 'cabos': [], 'apoiadores': []}
            selecionados[plural] = [contato.pk]
        elif request.GET.get('cidade'):
            # Vindo das sugestões do roteiro: cidade (e data) pré-definidas
            from liderancas.models import Cidade
            cid = Cidade.objects.filter(pk=request.GET['cidade']).first()
            if cid:
                initial = {'tipo': 'visita', 'regiao': cid.regiao_id, 'cidade': cid.pk}
        if request.GET.get('data'):
            initial['data'] = request.GET['data']
        form = CompromissoForm(initial=initial)
        if selecionados:
            form.participantes_selecionados = json_mod.dumps(selecionados)
        html = render_to_string('agenda/_compromisso_form.html', {
            'form': form, 'titulo': 'Novo Compromisso',
        }, request=request)
        return JsonResponse({'html': html})

    # Fallback non-AJAX
    if request.method == 'POST':
        form = CompromissoForm(request.POST)
        if form.is_valid():
            comp = form.save(commit=False)
            comp.cadastrado_por = request.user
            comp.save()
            form.save_m2m()
            comp.gerar_interacoes(request.user)
            messages.success(request, 'Compromisso cadastrado com sucesso.')
            return redirect('agenda:compromisso_list')
    else:
        form = CompromissoForm()
    return render(request, 'agenda/compromisso_form.html', {
        'form': form, 'titulo': 'Novo Compromisso',
    })


@secao_required('demandas:agenda')
def compromisso_edit(request, pk):
    comp = get_object_or_404(Compromisso, pk=pk)

    if request.method == 'POST' and _is_ajax(request):
        form = CompromissoForm(request.POST, instance=comp)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.atualizado_por = request.user
            obj.save()
            form.save_m2m()
            interacoes = obj.gerar_interacoes(request.user)
            return JsonResponse({'success': True, 'interacoes': interacoes})
        tarefas_vinculadas = comp.tarefas.select_related('responsavel').all()
        html = render_to_string('agenda/_compromisso_form.html', {
            'form': form, 'titulo': f'Editar: {comp.titulo}', 'editing': True, 'pk': pk,
            'tarefas_vinculadas': tarefas_vinculadas,
        }, request=request)
        return JsonResponse({'success': False, 'html': html})

    if _is_ajax(request):
        form = CompromissoForm(instance=comp)
        tarefas_vinculadas = comp.tarefas.select_related('responsavel').all()
        html = render_to_string('agenda/_compromisso_form.html', {
            'form': form, 'titulo': f'Editar: {comp.titulo}', 'editing': True, 'pk': pk,
            'tarefas_vinculadas': tarefas_vinculadas,
        }, request=request)
        return JsonResponse({'html': html})

    # Fallback non-AJAX
    if request.method == 'POST':
        form = CompromissoForm(request.POST, instance=comp)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.atualizado_por = request.user
            obj.save()
            form.save_m2m()
            obj.gerar_interacoes(request.user)
            messages.success(request, 'Compromisso atualizado com sucesso.')
            return redirect('agenda:compromisso_list')
    else:
        form = CompromissoForm(instance=comp)
    return render(request, 'agenda/compromisso_form.html', {
        'form': form, 'titulo': f'Editar: {comp.titulo}',
    })


@secao_required('demandas:agenda')
def compromisso_delete(request, pk):
    comp = get_object_or_404(Compromisso, pk=pk)
    if request.method == 'POST':
        comp.delete()
        if _is_ajax(request):
            return JsonResponse({'success': True})
        messages.success(request, 'Compromisso removido com sucesso.')
    return redirect('agenda:compromisso_list')


@secao_required('demandas:agenda')
def compromisso_print(request):
    de = request.GET.get('de')
    ate = request.GET.get('ate')
    compromissos = Compromisso.objects.select_related('regiao', 'cidade').all()
    if de:
        compromissos = compromissos.filter(data_hora_inicio__date__gte=de)
    if ate:
        compromissos = compromissos.filter(data_hora_inicio__date__lte=ate)
    return render(request, 'agenda/compromisso_print.html', {
        'compromissos': compromissos,
        'de': de,
        'ate': ate,
    })


# ==================== ROTEIROS ====================

@secao_required('demandas:roteiros')
def roteiro_list(request):
    roteiros = Roteiro.objects.select_related('regiao').prefetch_related('pontos').all()
    return render(request, 'agenda/roteiro_list.html', {
        'roteiros': roteiros,
    })


@secao_required('demandas:roteiros')
def roteiro_create(request):
    if request.method == 'POST':
        form = RoteiroForm(request.POST)
        formset = RoteiroPontoFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            roteiro = form.save(commit=False)
            roteiro.cadastrado_por = request.user
            roteiro.save()
            formset.instance = roteiro
            formset.save()
            messages.success(request, 'Roteiro cadastrado com sucesso.')
            return redirect('agenda:roteiro_list')
    else:
        form = RoteiroForm()
        formset = RoteiroPontoFormSet()
    return render(request, 'agenda/roteiro_form.html', {
        'form': form,
        'formset': formset,
        'titulo': 'Novo Roteiro',
    })


@secao_required('demandas:roteiros')
def roteiro_edit(request, pk):
    roteiro = get_object_or_404(Roteiro, pk=pk)
    if request.method == 'POST':
        form = RoteiroForm(request.POST, instance=roteiro)
        formset = RoteiroPontoFormSet(request.POST, instance=roteiro)
        if form.is_valid() and formset.is_valid():
            obj = form.save(commit=False)
            obj.atualizado_por = request.user
            obj.save()
            formset.save()
            messages.success(request, 'Roteiro atualizado com sucesso.')
            return redirect('agenda:roteiro_list')
    else:
        form = RoteiroForm(instance=roteiro)
        formset = RoteiroPontoFormSet(instance=roteiro)
    return render(request, 'agenda/roteiro_form.html', {
        'form': form,
        'formset': formset,
        'titulo': f'Editar: {roteiro.titulo}',
    })


@secao_required('demandas:roteiros')
def roteiro_delete(request, pk):
    roteiro = get_object_or_404(Roteiro, pk=pk)
    if request.method == 'POST':
        roteiro.delete()
        messages.success(request, 'Roteiro removido com sucesso.')
    return redirect('agenda:roteiro_list')


@secao_required('demandas:roteiros')
def roteiro_detail(request, pk):
    import json as json_mod
    roteiro = get_object_or_404(
        Roteiro.objects.select_related('regiao').prefetch_related(
            'pontos__compromisso__cidade', 'pontos__compromisso__regiao'
        ),
        pk=pk,
    )

    # Pontos com coordenadas para o mapa (ordem do roteiro)
    pontos_mapa = []
    for ponto in roteiro.pontos.all():
        cid = ponto.compromisso.cidade
        if cid.latitude and cid.longitude:
            pontos_mapa.append({
                'ordem': ponto.ordem,
                'titulo': ponto.compromisso.titulo,
                'cidade': cid.nome,
                'hora': ponto.compromisso.data_hora_inicio.strftime('%H:%M'),
                'lat': cid.latitude,
                'lng': cid.longitude,
            })

    return render(request, 'agenda/roteiro_detail.html', {
        'roteiro': roteiro,
        'pontos_mapa_json': json_mod.dumps(pontos_mapa),
        'sugestoes': _sugestoes_cidades(roteiro.regiao),
    })


def _sugestoes_cidades(regiao, limite=8):
    """Cidades da região ordenadas por contatos com relacionamento vencido —
    matéria-prima para escolher onde criar os pontos do roteiro."""
    from django.db.models import Max
    from django.utils import timezone as tz
    from liderancas.views import FREQ_PRAZOS
    agora = tz.now()
    por_cidade = {}
    fontes = (
        CaboEleitoral.objects.filter(cidade__regiao=regiao).select_related('cidade'),
        Apoiador.objects.filter(cidade__regiao=regiao).select_related('cidade'),
    )
    for qs in fontes:
        for c in qs.annotate(ultima=Max('interacoes__data')):
            prazo = FREQ_PRAZOS.get(c.frequencia_relacionamento, 30)
            dias = (agora - c.ultima).days if c.ultima else None
            if dias is not None and dias <= prazo:
                continue
            info = por_cidade.setdefault(c.cidade, {'vencidos': 0, 'nunca': 0, 'alta': 0})
            info['vencidos'] += 1
            if dias is None:
                info['nunca'] += 1
            if c.prioridade == 'alta':
                info['alta'] += 1
    ranking = sorted(por_cidade.items(), key=lambda kv: (-kv[1]['alta'], -kv[1]['vencidos']))
    return [{'cidade': cid, **info} for cid, info in ranking[:limite]]


def _dist2(c1, c2):
    return (c1.latitude - c2.latitude) ** 2 + (c1.longitude - c2.longitude) ** 2


@secao_required('demandas:roteiros')
def roteiro_otimizar(request, pk):
    """Reordena os pontos pelo vizinho mais próximo (lat/long das cidades)."""
    roteiro = get_object_or_404(Roteiro, pk=pk)
    if request.method == 'POST':
        pontos = list(roteiro.pontos.select_related('compromisso__cidade'))
        com_coord = [p for p in pontos if p.compromisso.cidade.latitude and p.compromisso.cidade.longitude]
        sem_coord = [p for p in pontos if p not in com_coord]
        if len(com_coord) >= 2:
            com_coord.sort(key=lambda p: p.ordem)
            ordenados = [com_coord.pop(0)]
            while com_coord:
                atual = ordenados[-1].compromisso.cidade
                com_coord.sort(key=lambda p: _dist2(atual, p.compromisso.cidade))
                ordenados.append(com_coord.pop(0))
            for i, ponto in enumerate(ordenados + sem_coord, start=1):
                if ponto.ordem != i:
                    ponto.ordem = i
                    ponto.save(update_fields=['ordem'])
            messages.success(request, 'Ordem otimizada pela proximidade entre as cidades. Revise os horários dos compromissos.')
        else:
            messages.warning(request, 'É preciso ao menos 2 paradas com cidades georreferenciadas.')
    return redirect('agenda:roteiro_detail', pk=pk)


@secao_required('demandas:roteiros')
def roteiro_print(request, pk):
    roteiro = get_object_or_404(
        Roteiro.objects.select_related('regiao').prefetch_related(
            'pontos__compromisso__cidade', 'pontos__compromisso__regiao'
        ),
        pk=pk,
    )
    return render(request, 'agenda/roteiro_print.html', {
        'roteiro': roteiro,
    })


# ==================== API ====================

@secao_required('demandas:agenda')
def api_compromissos_json(request):
    from django.db.models import Count
    start = request.GET.get('start')
    end = request.GET.get('end')
    qs = Compromisso.objects.select_related('cidade', 'regiao').annotate(
        tarefas_count=Count('tarefas')
    )
    if start:
        qs = qs.filter(data_hora_inicio__gte=start)
    if end:
        qs = qs.filter(data_hora_inicio__lte=end)
    events = []
    for c in qs:
        events.append({
            'id': c.pk,
            'title': c.titulo,
            'start': c.data_hora_inicio.isoformat(),
            'end': c.data_hora_fim.isoformat(),
            'color': c.cor,
            'order': 0,
            'extendedProps': {
                'tipo': c.get_tipo_display(),
                'status': c.get_status_display(),
                'cidade': str(c.cidade),
                'regiao': c.regiao.sigla,
                'pk': c.pk,
                'tarefas_count': c.tarefas_count,
            },
        })
    return JsonResponse(events, safe=False)


def _contatos_payload(qs):
    """Serializa contatos com prioridade e dias desde a última interação,
    ordenando: prioridade alta primeiro, depois nunca contatados, depois mais atrasados."""
    from django.db.models import Max
    from django.utils import timezone as tz
    agora = tz.now()
    out = []
    for c in qs.annotate(ult=Max('interacoes__data')):
        dias = (agora - c.ult).days if c.ult else None
        out.append({
            'id': c.id, 'nome': c.nome, 'telefone': c.telefone,
            'instagram': c.instagram, 'prioridade': c.prioridade, 'dias': dias,
        })
    ordem_pr = {'alta': 0, 'media': 1, 'baixa': 2}
    out.sort(key=lambda x: (ordem_pr.get(x['prioridade'], 1), 0 if x['dias'] is None else 1, -(x['dias'] or 0)))
    return out


@secao_required('demandas:agenda')
def api_coordenadores_regiao(request, regiao_id):
    qs = CoordenadorRegional.objects.filter(regiao_id=regiao_id)
    return JsonResponse(_contatos_payload(qs), safe=False)


@secao_required('demandas:agenda')
def api_cabos_cidade(request, cidade_id):
    qs = CaboEleitoral.objects.filter(cidade_id=cidade_id)
    return JsonResponse(_contatos_payload(qs), safe=False)


@secao_required('demandas:agenda')
def api_apoiadores_cidade(request, cidade_id):
    qs = Apoiador.objects.filter(cidade_id=cidade_id)
    return JsonResponse(_contatos_payload(qs), safe=False)


@secao_required('demandas:agenda')
def api_compromissos_por_data(request):
    data = request.GET.get('data')
    if not data:
        return JsonResponse([], safe=False)
    comps = Compromisso.objects.filter(
        data_hora_inicio__date=data
    ).values('id', 'titulo', 'data_hora_inicio')
    result = []
    for c in comps:
        result.append({
            'id': c['id'],
            'titulo': f"{c['data_hora_inicio']:%H:%M} — {c['titulo']}",
        })
    return JsonResponse(result, safe=False)


@secao_required('demandas:agenda')
def api_tarefas_calendario(request):
    """Retorna tarefas agrupadas por dia como eventos do FullCalendar."""
    from collections import defaultdict
    from datetime import date as date_type

    start = request.GET.get('start')
    end = request.GET.get('end')
    qs = Tarefa.objects.filter(
        prazo__isnull=False,
        excluida_em__isnull=True,
    ).exclude(fase='concluida').select_related('responsavel', 'regiao', 'cidade')
    if start:
        qs = qs.filter(prazo__gte=start[:10])
    if end:
        qs = qs.filter(prazo__lte=end[:10])

    today = date_type.today()
    por_dia = defaultdict(lambda: {'total': 0, 'vencidas': 0, 'ids': []})
    for t in qs:
        dia = t.prazo.isoformat()
        por_dia[dia]['total'] += 1
        por_dia[dia]['ids'].append(t.pk)
        if t.prazo < today:
            por_dia[dia]['vencidas'] += 1

    events = []
    for dia, info in por_dia.items():
        tem_vencida = info['vencidas'] > 0
        events.append({
            'id': f'tarefas-{dia}',
            'title': f'\U0001f4cb {info["total"]} tarefa{"s" if info["total"] > 1 else ""}',
            'start': dia,
            'allDay': True,
            'display': 'block',
            'color': '#ef4444' if tem_vencida else '#64748b',
            'borderColor': '#ef4444' if tem_vencida else '#64748b',
            'classNames': ['fc-tarefa-event'],
            'order': 1,
            'extendedProps': {
                'is_tarefa': True,
                'is_tarefa_resumo': True,
                'total': info['total'],
                'vencidas': info['vencidas'],
                'tarefa_ids': info['ids'],
            },
        })
    return JsonResponse(events, safe=False)


@secao_required('demandas:agenda')
def api_tarefas_por_dia(request):
    """Retorna tarefas de um dia específico para o popover do calendário."""
    data = request.GET.get('data')
    if not data:
        return JsonResponse([], safe=False)
    from datetime import date as date_type
    today = date_type.today()
    qs = Tarefa.objects.filter(
        prazo=data,
        excluida_em__isnull=True,
    ).exclude(fase='concluida').select_related('responsavel').order_by('prioridade', 'titulo')
    PRIO_COLORS = {
        'baixa': '#22c55e', 'media': '#3b82f6',
        'alta': '#f97316', 'urgente': '#ef4444',
    }
    items = []
    for t in qs:
        items.append({
            'id': t.pk,
            'titulo': t.titulo,
            'responsavel': t.responsavel.get_full_name() if t.responsavel else '',
            'fase': t.get_fase_display(),
            'prioridade': t.get_prioridade_display(),
            'cor': PRIO_COLORS.get(t.prioridade, '#3b82f6'),
            'vencida': t.prazo < today,
        })
    return JsonResponse(items, safe=False)


@secao_required('demandas:agenda')
def api_tarefas_compromisso(request, pk):
    """Lista tarefas vinculadas a um compromisso."""
    comp = get_object_or_404(Compromisso, pk=pk)
    tarefas = comp.tarefas.select_related('responsavel').filter(
        excluida_em__isnull=True
    ).order_by('fase', 'ordem')
    items = []
    for t in tarefas:
        items.append({
            'id': t.id,
            'titulo': t.titulo,
            'fase': t.fase,
            'concluida': t.fase == 'concluida',
            'prioridade': t.prioridade,
            'responsavel': t.responsavel.get_full_name() if t.responsavel else '',
        })
    total = len(items)
    concluidas = sum(1 for i in items if i['concluida'])
    return JsonResponse({
        'tarefas': items,
        'total': total,
        'concluidas': concluidas,
    })


@secao_required('demandas:agenda')
def api_criar_tarefa_compromisso(request, pk):
    """Cria uma tarefa vinculada a um compromisso."""
    import json
    from django.utils import timezone
    from tarefas.models import Tarefa

    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    comp = get_object_or_404(Compromisso, pk=pk)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    titulo = data.get('titulo', '').strip()
    if not titulo:
        return JsonResponse({'ok': False, 'error': 'Título obrigatório'}, status=400)

    tarefa = Tarefa.objects.create(
        titulo=titulo,
        tipo='outro',
        fase='a_fazer',
        prioridade=data.get('prioridade', 'media'),
        regiao=comp.regiao,
        cidade=comp.cidade,
        compromisso=comp,
        cadastrado_por=request.user,
    )

    return JsonResponse({
        'ok': True,
        'tarefa': {
            'id': tarefa.id,
            'titulo': tarefa.titulo,
            'fase': tarefa.fase,
            'concluida': False,
            'prioridade': tarefa.prioridade,
            'responsavel': '',
        },
    })


@secao_required('demandas:agenda')
def api_toggle_tarefa_compromisso(request, tarefa_id):
    """Alterna tarefa entre a_fazer e concluida."""
    from django.utils import timezone
    from tarefas.models import Tarefa, TarefaHistorico

    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)

    if tarefa.fase == 'concluida':
        old_fase = 'Concluída'
        tarefa.fase = 'a_fazer'
        tarefa.concluida_em = None
        new_fase = 'A Fazer'
    else:
        old_fase = tarefa.get_fase_display()
        tarefa.fase = 'concluida'
        tarefa.concluida_em = timezone.now()
        new_fase = 'Concluída'

    tarefa.atualizado_por = request.user
    tarefa.save(update_fields=['fase', 'concluida_em', 'atualizado_por', 'updated_at'])

    TarefaHistorico.objects.create(
        tarefa=tarefa,
        usuario=request.user,
        campo='fase',
        valor_anterior=old_fase,
        valor_novo=new_fase,
    )

    return JsonResponse({
        'ok': True,
        'concluida': tarefa.fase == 'concluida',
        'fase': tarefa.fase,
    })


@secao_required('demandas:agenda')
def api_followup_compromisso(request, pk):
    """Cria tarefa(s) de follow-up pós-compromisso."""
    import json
    from datetime import timedelta
    from django.utils import timezone

    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    comp = get_object_or_404(Compromisso, pk=pk)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    itens = data.get('itens', [])
    if not itens:
        return JsonResponse({'ok': False, 'error': 'Nenhum item selecionado'}, status=400)

    prazo_base = (comp.data_hora_inicio.date() + timedelta(days=2))

    # Mapear tipo do compromisso → tipo da tarefa
    tipo_map = {
        'reuniao': 'reuniao',
        'evento': 'evento',
        'visita': 'visita',
        'comicio': 'evento',
        'entrevista': 'comunicacao',
        'viagem': 'articulacao',
        'pessoal': 'outro',
    }

    criadas = []
    for item in itens:
        titulo = item.get('titulo', '').strip()
        if not titulo:
            continue
        tarefa = Tarefa.objects.create(
            titulo=f'{titulo} — {comp.titulo}',
            descricao=comp.descricao,
            tipo=tipo_map.get(comp.tipo, 'outro'),
            fase='a_fazer',
            prioridade=comp.prioridade if comp.prioridade != 'media' else 'media',
            prazo=prazo_base,
            regiao=comp.regiao,
            cidade=comp.cidade,
            observacoes=comp.observacoes,
            compromisso=comp,
            cadastrado_por=request.user,
        )
        criadas.append({
            'id': tarefa.id,
            'titulo': tarefa.titulo,
            'prazo': tarefa.prazo.strftime('%d/%m/%Y'),
        })

    return JsonResponse({'ok': True, 'criadas': criadas, 'total': len(criadas)})


# ==================== EVENTOS ====================

@secao_required('demandas:eventos')
def evento_list(request):
    from liderancas.models import Regiao, Cidade
    eventos = Evento.objects.select_related('cidade', 'cidade__regiao').all()

    busca = request.GET.get('busca', '').strip()
    tipo_filtro = request.GET.get('tipo', '')
    relevancia_filtro = request.GET.get('relevancia', '')
    status_filtro = request.GET.get('status', '')
    regiao_filtro = request.GET.get('regiao', '')
    cidade_filtro = request.GET.get('cidade', '')

    if busca:
        eventos = eventos.filter(
            models.Q(nome__icontains=busca) |
            models.Q(local__icontains=busca)
        )
    if tipo_filtro:
        eventos = eventos.filter(tipo=tipo_filtro)
    if relevancia_filtro:
        eventos = eventos.filter(relevancia=relevancia_filtro)
    if status_filtro:
        eventos = eventos.filter(status=status_filtro)
    if regiao_filtro:
        eventos = eventos.filter(cidade__regiao_id=regiao_filtro)
    if cidade_filtro:
        eventos = eventos.filter(cidade_id=cidade_filtro)

    # Paginação
    from django.core.paginator import Paginator
    paginator = Paginator(eventos, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Query string sem page
    qd = request.GET.copy()
    qd.pop('page', None)
    query_string = qd.urlencode()

    # Cidades para filtro dinâmico
    cidades_filtro = []
    if regiao_filtro:
        cidades_filtro = Cidade.objects.filter(regiao_id=regiao_filtro).order_by('nome')

    return render(request, 'agenda/evento_list.html', {
        'page_obj': page_obj,
        'total': paginator.count,
        'busca': busca,
        'tipo_filtro': tipo_filtro,
        'tipo_choices': Evento.TIPO_CHOICES,
        'relevancia_filtro': relevancia_filtro,
        'relevancia_choices': Evento.RELEVANCIA_CHOICES,
        'status_filtro': status_filtro,
        'status_choices': Evento.STATUS_CHOICES,
        'regiao_filtro': regiao_filtro,
        'regioes': Regiao.objects.all().order_by('sigla'),
        'cidade_filtro': cidade_filtro,
        'cidades_filtro': cidades_filtro,
        'query_string': query_string,
    })


@secao_required('demandas:eventos')
def evento_create(request):
    if request.method == 'POST':
        form = EventoForm(request.POST, request.FILES)
        if form.is_valid():
            evento = form.save(commit=False)
            evento.cadastrado_por = request.user
            evento.save()
            messages.success(request, 'Evento cadastrado com sucesso!')
            return redirect('agenda:evento_list')
    else:
        form = EventoForm()
    return render(request, 'agenda/evento_form.html', {
        'form': form,
        'titulo': 'Novo Evento',
    })


@secao_required('demandas:eventos')
def evento_edit(request, pk):
    evento = get_object_or_404(Evento, pk=pk)
    if request.method == 'POST':
        form = EventoForm(request.POST, request.FILES, instance=evento)
        if form.is_valid():
            form.save()
            messages.success(request, 'Evento atualizado com sucesso!')
            return redirect('agenda:evento_list')
    else:
        form = EventoForm(instance=evento)
    return render(request, 'agenda/evento_form.html', {
        'form': form,
        'titulo': f'Editar Evento — {evento.nome}',
    })


@secao_required('demandas:eventos')
def evento_delete(request, pk):
    evento = get_object_or_404(Evento, pk=pk)
    if request.method == 'POST':
        evento.delete()
        messages.success(request, 'Evento excluído.')
    return redirect('agenda:evento_list')


def api_eventos_calendario(request):
    """Retorna eventos confirmados para o FullCalendar."""
    eventos = Evento.objects.filter(
        status='confirmado'
    ).select_related('cidade')
    result = []
    for e in eventos:
        start = str(e.data)
        if e.horario_inicio:
            start = f'{e.data}T{e.horario_inicio}'
        end = None
        if e.horario_fim:
            end = f'{e.data}T{e.horario_fim}'
        result.append({
            'id': f'evento-{e.id}',
            'title': f'📌 {e.nome}',
            'start': start,
            'end': end,
            'color': '#e91e8b',
            'textColor': '#fff',
            'allDay': not e.horario_inicio,
            'order': 0,
            'extendedProps': {
                'tipo': 'evento_externo',
                'local': f'{e.cidade} — {e.local}' if e.local else str(e.cidade),
                'relevancia': e.get_relevancia_display(),
                'publico': e.publico_estimado,
            },
        })
    return JsonResponse(result, safe=False)


def api_evento_detalhe(request, pk):
    """Retorna detalhes de um evento para o modal."""
    e = get_object_or_404(Evento.objects.select_related('cidade', 'cidade__regiao'), pk=pk)
    return JsonResponse({
        'id': e.id,
        'nome': e.nome,
        'tipo': e.get_tipo_display(),
        'data': e.data.strftime('%d/%m/%Y'),
        'horario': f'{e.horario_inicio:%H:%M} — {e.horario_fim:%H:%M}' if e.horario_inicio and e.horario_fim else (f'{e.horario_inicio:%H:%M}' if e.horario_inicio else '-'),
        'cidade': str(e.cidade),
        'local': e.local or '-',
        'publico_estimado': e.publico_estimado,
        'relevancia': e.get_relevancia_display(),
        'status': e.get_status_display(),
        'observacoes': e.observacoes,
        'resultado': e.resultado,
        'imagem': e.imagem.url if e.imagem else None,
    })


def api_roteiro_dia(request):
    """Retorna compromissos + eventos de um dia para montar roteiro."""
    from datetime import date as date_cls
    data_str = request.GET.get('data')
    if not data_str:
        return JsonResponse({'error': 'data obrigatória'}, status=400)

    data = date_cls.fromisoformat(data_str)

    # Compromissos do dia
    from django.utils import timezone
    from datetime import datetime, time
    inicio_dia = timezone.make_aware(datetime.combine(data, time.min))
    fim_dia = timezone.make_aware(datetime.combine(data, time.max))

    compromissos = Compromisso.objects.filter(
        data_hora_inicio__range=(inicio_dia, fim_dia)
    ).select_related('regiao', 'cidade').order_by('data_hora_inicio')

    # Eventos confirmados do dia
    eventos = Evento.objects.filter(
        data=data, status='confirmado'
    ).select_related('cidade')

    itens = []
    for c in compromissos:
        inicio_local = timezone.localtime(c.data_hora_inicio)
        fim_local = timezone.localtime(c.data_hora_fim)
        itens.append({
            'id': c.id,
            'tipo_item': 'compromisso',
            'titulo': c.titulo,
            'horario': f'{inicio_local:%H:%M} — {fim_local:%H:%M}',
            'hora_sort': inicio_local.strftime('%H:%M'),
            'cidade': str(c.cidade),
            'cidade_lat': c.cidade.latitude,
            'cidade_lon': c.cidade.longitude,
            'endereco': c.endereco or '',
            'regiao': c.regiao.sigla if c.regiao else '',
            'tipo': c.get_tipo_display(),
            'cor': c.cor,
        })

    for e in eventos:
        itens.append({
            'id': e.id,
            'tipo_item': 'evento',
            'titulo': f'📌 {e.nome}',
            'horario': f'{e.horario_inicio:%H:%M} — {e.horario_fim:%H:%M}' if e.horario_inicio and e.horario_fim else (f'{e.horario_inicio:%H:%M}' if e.horario_inicio else 'Dia todo'),
            'hora_sort': e.horario_inicio.strftime('%H:%M') if e.horario_inicio else '00:00',
            'cidade': str(e.cidade),
            'cidade_lat': e.cidade.latitude,
            'cidade_lon': e.cidade.longitude,
            'endereco': e.local or '',
            'regiao': '',
            'tipo': e.get_tipo_display(),
            'cor': '#e91e8b',
        })

    itens.sort(key=lambda x: x['hora_sort'])

    # Verificar se já existe roteiro para este dia
    roteiro_existente = Roteiro.objects.filter(data=data).first()
    roteiro_info = None
    if roteiro_existente:
        roteiro_info = {
            'id': roteiro_existente.id,
            'motorista': roteiro_existente.motorista,
            'observacoes': roteiro_existente.observacoes,
            'status': roteiro_existente.get_status_display(),
        }

    return JsonResponse({
        'data': data.strftime('%d/%m/%Y'),
        'data_iso': data_str,
        'itens': itens,
        'roteiro': roteiro_info,
    })


@secao_required('demandas:agenda')
def api_salvar_roteiro(request):
    """Salvar roteiro a partir do modal."""
    import json
    import traceback
    if request.method != 'POST':
        return JsonResponse({'error': 'POST obrigatório'}, status=405)

    try:
        body = json.loads(request.body)
        data_str = body.get('data')
        motorista = body.get('motorista', '')
        observacoes = body.get('observacoes', '')
        pontos = body.get('pontos', [])

        from datetime import date as date_cls
        from liderancas.models import Regiao
        data = date_cls.fromisoformat(data_str)

        # Determinar região principal
        regiao = None
        for ponto in pontos:
            if ponto.get('tipo_item') == 'compromisso':
                comp = Compromisso.objects.filter(id=ponto['id']).select_related('regiao').first()
                if comp and comp.regiao:
                    regiao = comp.regiao
                    break
        if not regiao:
            regiao = Regiao.objects.first()

        # Criar ou atualizar roteiro
        roteiro, created = Roteiro.objects.update_or_create(
            data=data,
            defaults={
                'titulo': f'Roteiro {data:%d/%m/%Y}',
                'regiao': regiao,
                'motorista': motorista,
                'observacoes': observacoes,
                'cadastrado_por': request.user,
            }
        )

        # Limpar pontos antigos e recriar
        roteiro.pontos.all().delete()
        for i, ponto in enumerate(pontos):
            if ponto.get('tipo_item') == 'compromisso':
                RoteiroPonto.objects.create(
                    roteiro=roteiro,
                    compromisso_id=ponto['id'],
                    ordem=i + 1,
                )

        return JsonResponse({
            'ok': True,
            'roteiro_id': roteiro.id,
            'message': 'Roteiro salvo com sucesso!' if created else 'Roteiro atualizado!',
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e), 'trace': traceback.format_exc()}, status=500)
