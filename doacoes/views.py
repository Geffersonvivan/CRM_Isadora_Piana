from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from core.models import Configuracao
from core.views import api_cidades as core_api_cidades
from usuarios.views import secao_required
from .models import Doacao, ComissaoResgate
from .forms import DoacaoForm
from liderancas.models import Regiao, Cidade


@secao_required('demandas:doacoes')
def doacao_list(request):
    qs = Doacao.objects.select_related('apoiador', 'coordenador', 'regiao', 'cidade')

    busca = request.GET.get('busca', '')
    status = request.GET.get('status', '')
    forma = request.GET.get('forma', '')
    regiao_id = request.GET.get('regiao', '')
    cidade_id = request.GET.get('cidade', '')

    if busca:
        qs = qs.filter(
            Q(doador_nome__icontains=busca) |
            Q(doador_cpf__icontains=busca) |
            Q(doador_telefone__icontains=busca)
        )
    if status:
        qs = qs.filter(status=status)
    if forma:
        qs = qs.filter(forma_pagamento=forma)
    if regiao_id:
        qs = qs.filter(regiao_id=regiao_id)
    if cidade_id:
        qs = qs.filter(cidade_id=cidade_id)

    total = qs.count()
    totais = qs.filter(status='confirmada').aggregate(
        total_bruto=Sum('valor'),
        total_liquido=Sum('valor_liquido'),
        total_comissoes=Sum('comissao_plataforma') + Sum('comissao_coordenador') + Sum('comissao_apoiador'),
    )

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))

    regioes = Regiao.objects.all()
    cidades = Cidade.objects.filter(regiao_id=regiao_id) if regiao_id else Cidade.objects.none()

    return render(request, 'doacoes/doacao_list.html', {
        'page': page,
        'total': total,
        'totais': totais,
        'regioes': regioes,
        'cidades': cidades,
        'busca': busca,
        'status_filtro': status,
        'forma_filtro': forma,
        'regiao_filtro': regiao_id,
        'cidade_filtro': cidade_id,
    })


@secao_required('demandas:doacoes')
def doacao_create(request):
    if request.method == 'POST':
        form = DoacaoForm(request.POST, request.FILES)
        if form.is_valid():
            doacao = form.save(commit=False)
            regiao_id = request.POST.get('regiao')
            if regiao_id:
                doacao.regiao_id = regiao_id
            doacao.save()
            messages.success(request, 'Doação registrada com sucesso.')
            return redirect('doacoes:doacao_list')
    else:
        form = DoacaoForm()
    return render(request, 'doacoes/doacao_form.html', {
        'form': form,
        'titulo': 'Nova Doação',
    })


@secao_required('demandas:doacoes')
def doacao_edit(request, pk):
    doacao = get_object_or_404(Doacao, pk=pk)
    if request.method == 'POST':
        form = DoacaoForm(request.POST, request.FILES, instance=doacao)
        if form.is_valid():
            d = form.save(commit=False)
            regiao_id = request.POST.get('regiao')
            if regiao_id:
                d.regiao_id = regiao_id
            d.save()
            messages.success(request, 'Doação atualizada com sucesso.')
            return redirect('doacoes:doacao_list')
    else:
        form = DoacaoForm(instance=doacao)
    return render(request, 'doacoes/doacao_form.html', {
        'form': form,
        'titulo': 'Editar Doação',
        'doacao': doacao,
    })


@secao_required('demandas:doacoes')
def doacao_delete(request, pk):
    doacao = get_object_or_404(Doacao, pk=pk)
    if request.method == 'POST':
        doacao.delete()
        messages.success(request, 'Doação excluída.')
        return redirect('doacoes:doacao_list')
    return redirect('doacoes:doacao_list')


@secao_required('demandas:doacoes')
def doacao_detalhe(request, pk):
    doacao = get_object_or_404(Doacao, pk=pk)
    return JsonResponse({
        'id': doacao.pk,
        'doador_nome': doacao.doador_nome,
        'doador_cpf': doacao.doador_cpf,
        'doador_telefone': doacao.doador_telefone,
        'doador_email': doacao.doador_email,
        'valor': str(doacao.valor),
        'data': doacao.data.strftime('%d/%m/%Y %H:%M') if doacao.data else '',
        'forma_pagamento': doacao.get_forma_pagamento_display(),
        'status': doacao.get_status_display(),
        'apoiador': str(doacao.apoiador) if doacao.apoiador else '',
        'coordenador': str(doacao.coordenador) if doacao.coordenador else '',
        'regiao': str(doacao.regiao) if doacao.regiao else '',
        'cidade': str(doacao.cidade) if doacao.cidade else '',
        'comissao_plataforma': str(doacao.comissao_plataforma),
        'comissao_coordenador': str(doacao.comissao_coordenador),
        'comissao_apoiador': str(doacao.comissao_apoiador),
        'valor_liquido': str(doacao.valor_liquido),
        'observacoes': doacao.observacoes,
        'comprovante_url': doacao.comprovante.url if doacao.comprovante else '',
    })


@secao_required('demandas:doacoes')
def comissao_list(request):
    qs = ComissaoResgate.objects.select_related('coordenador', 'apoiador')
    tipo = request.GET.get('tipo', '')
    status = request.GET.get('status', '')

    if tipo:
        qs = qs.filter(tipo=tipo)
    if status:
        qs = qs.filter(status=status)

    total_pendente = qs.filter(status='pendente').aggregate(t=Sum('valor'))['t'] or 0
    total_pago = qs.filter(status='pago').aggregate(t=Sum('valor'))['t'] or 0

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'doacoes/comissao_list.html', {
        'page': page,
        'total_pendente': total_pendente,
        'total_pago': total_pago,
        'tipo_filtro': tipo,
        'status_filtro': status,
    })


@secao_required('demandas:doacoes')
def comissao_pagar(request, pk):
    comissao = get_object_or_404(ComissaoResgate, pk=pk)
    if request.method == 'POST':
        comissao.status = 'pago'
        comissao.data_pagamento = timezone.now()
        comissao.save()
        messages.success(request, 'Comissão marcada como paga.')
    return redirect('doacoes:comissao_list')


@secao_required('demandas:doacoes')
def dashboard_doacoes(request):
    config = Configuracao.get()
    confirmadas = Doacao.objects.filter(status='confirmada')
    todas = Doacao.objects.all()

    # Cards
    total_doacoes = todas.count()
    total_confirmadas = confirmadas.count()
    total_arrecadado = confirmadas.aggregate(t=Sum('valor'))['t'] or 0
    total_liquido = confirmadas.aggregate(t=Sum('valor_liquido'))['t'] or 0
    total_comissoes = (
        (confirmadas.aggregate(t=Sum('comissao_plataforma'))['t'] or 0) +
        (confirmadas.aggregate(t=Sum('comissao_coordenador'))['t'] or 0) +
        (confirmadas.aggregate(t=Sum('comissao_apoiador'))['t'] or 0)
    )
    pendentes = todas.filter(status='pendente').count()
    estornadas = todas.filter(status='estornada').count()

    # Por forma de pagamento
    por_forma = list(
        confirmadas.values('forma_pagamento')
        .annotate(total=Sum('valor'), qtd=Count('id'))
        .order_by('-total')
    )

    # Top doadores (por CPF)
    top_doadores = list(
        confirmadas.values('doador_nome', 'doador_cpf')
        .annotate(total=Sum('valor'), qtd=Count('id'))
        .order_by('-total')[:10]
    )

    # Por mês
    por_mes = list(
        confirmadas.annotate(mes=TruncMonth('data'))
        .values('mes')
        .annotate(total=Sum('valor'), qtd=Count('id'))
        .order_by('mes')
    )

    import json
    chart_forma_labels = json.dumps([dict(Doacao.FORMA_PAGAMENTO_CHOICES).get(f['forma_pagamento'], f['forma_pagamento']) for f in por_forma])
    chart_forma_data = json.dumps([float(f['total']) for f in por_forma])
    chart_doadores_labels = json.dumps([d['doador_nome'] for d in top_doadores])
    chart_doadores_data = json.dumps([float(d['total']) for d in top_doadores])
    chart_mes_labels = json.dumps([m['mes'].strftime('%b/%Y') for m in por_mes])
    chart_mes_data = json.dumps([float(m['total']) for m in por_mes])

    return render(request, 'doacoes/dashboard.html', {
        'meta_doacoes': config.meta_doacoes,
        'meta_doacoes_fmt': f'{config.meta_doacoes:,.0f}'.replace(',', '.'),
        'percentual_meta': round(float(total_arrecadado) / config.meta_doacoes * 100, 1) if config.meta_doacoes > 0 else 0,
        'total_doacoes': total_doacoes,
        'total_confirmadas': total_confirmadas,
        'total_arrecadado': total_arrecadado,
        'total_liquido': total_liquido,
        'total_comissoes': total_comissoes,
        'pendentes': pendentes,
        'estornadas': estornadas,
        'chart_forma_labels': chart_forma_labels,
        'chart_forma_data': chart_forma_data,
        'chart_doadores_labels': chart_doadores_labels,
        'chart_doadores_data': chart_doadores_data,
        'chart_mes_labels': chart_mes_labels,
        'chart_mes_data': chart_mes_data,
    })


api_cidades_regiao = core_api_cidades
