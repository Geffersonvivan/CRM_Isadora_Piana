import os
from functools import wraps
from django.conf import settings as django_settings
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse, FileResponse
from django.db.models import Count
from django.utils import timezone
from core.views import api_cidades as core_api_cidades
from core.services import calcular_scores_rede, score_usuario
from liderancas.models import Apoiador, Cidade
from .forms import ApoiadorPWAForm, ReplicadorForm, VoluntarioPWAForm, DoacaoPWAForm


def pwa_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('pwa:login')
        return view_func(request, *args, **kwargs)
    return wrapper


def pwa_login(request):
    if request.user.is_authenticated:
        return redirect('pwa:dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('pwa:dashboard')
        else:
            messages.error(request, 'Usuário ou senha inválidos.')
    return render(request, 'pwa/login.html')


def pwa_logout(request):
    logout(request)
    return redirect('pwa:login')


@pwa_login_required
def dashboard(request):
    user = request.user

    from usuarios.models import Usuario

    diretos_map, convidados_map = calcular_scores_rede()

    # Meu placar (diretos + rede)
    meus_diretos, meus_rede, meu_total, _ = score_usuario(user.id, diretos_map, convidados_map)

    # Ranking geral (top 10) — score = cadastros diretos + cadastros dos replicadores
    vinculo_map = dict(Usuario.VINCULO_CHOICES)
    pwa_users = Usuario.objects.filter(
        vinculo__in=['coordenador', 'cabo', 'replicador'],
    ).select_related('regiao')

    ranking = []
    for u in pwa_users:
        diretos, rede, total, _ = score_usuario(u.id, diretos_map, convidados_map)
        if total > 0:
            vinculo_label = vinculo_map.get(u.vinculo, u.vinculo or '')
            regiao_sigla = u.regiao.sigla if u.regiao else ''
            ranking.append({
                'cadastrado_por__id': u.id,
                'cadastrado_por__first_name': u.first_name,
                'cadastrado_por__last_name': u.last_name,
                'cadastrado_por__vinculo_display': f'{vinculo_label} {regiao_sigla}'.strip() if vinculo_label else '',
                'total': total,
                'diretos': diretos,
                'rede': rede,
            })

    ranking.sort(key=lambda x: x['total'], reverse=True)

    # Posição do usuário
    minha_posicao = None
    for i, r in enumerate(ranking, 1):
        if r['cadastrado_por__id'] == user.id:
            minha_posicao = i
            break

    ranking = ranking[:10]

    # Meus últimos cadastros
    ultimos = Apoiador.objects.filter(cadastrado_por=user).select_related('cidade')[:5]

    # Meus replicadores
    meus_replicadores = user.convidados.all().annotate(
        total_apoiadores=Count('apoiadores_cadastrados')
    ).order_by('-total_apoiadores')

    return render(request, 'pwa/dashboard.html', {
        'meu_total': meu_total,
        'minha_posicao': minha_posicao,
        'ranking': ranking,
        'ultimos': ultimos,
        'meus_replicadores': meus_replicadores,
    })


@pwa_login_required
def cadastro_apoiador(request):
    if request.method == 'POST':
        form = ApoiadorPWAForm(request.POST, user=request.user)
        if form.is_valid():
            apoiador = form.save(commit=False)
            apoiador.cadastrado_por = request.user
            apoiador.save()
            messages.success(request, f'{apoiador.nome} cadastrado com sucesso!')
            return redirect('pwa:cadastro_apoiador')
    else:
        form = ApoiadorPWAForm(user=request.user)
    return render(request, 'pwa/cadastro_apoiador.html', {'form': form})


@pwa_login_required
def cadastro_replicador(request):
    if request.method == 'POST':
        form = ReplicadorForm(request.POST, user=request.user)
        if form.is_valid():
            novo_user, senha = form.save(convidado_por=request.user)
            return render(request, 'pwa/replicador_criado.html', {
                'novo_user': novo_user,
                'senha': senha,
            })
    else:
        form = ReplicadorForm(user=request.user)
    return render(request, 'pwa/cadastro_replicador.html', {'form': form})


@pwa_login_required
def cadastro_voluntario(request):
    if request.method == 'POST':
        form = VoluntarioPWAForm(request.POST)
        if form.is_valid():
            vol = form.save(commit=False)
            vol.regiao = form.cleaned_data['regiao']
            vol.disponibilidades = form.cleaned_data['disponibilidades']
            vol.cadastrado_por = request.user
            vol.save()
            messages.success(request, f'{vol.nome} cadastrado para mobilização!')
            return redirect('pwa:cadastro_voluntario')
    else:
        form = VoluntarioPWAForm()
    return render(request, 'pwa/cadastro_voluntario.html', {'form': form})


@pwa_login_required
def cadastro_doacao(request):
    if request.method == 'POST':
        form = DoacaoPWAForm(request.POST)
        if form.is_valid():
            doacao = form.save(commit=False)
            doacao.data = timezone.now()
            doacao.status = 'pendente'
            regiao_id = request.POST.get('regiao')
            if regiao_id:
                doacao.regiao_id = regiao_id
            # Vincular ao apoiador do usuário logado, se existir
            apoiador = Apoiador.objects.filter(cadastrado_por=request.user).first()
            if apoiador:
                doacao.apoiador = apoiador
            doacao.save()
            messages.success(request, f'Doação de R$ {doacao.valor} registrada com sucesso!')
            return redirect('pwa:cadastro_doacao')
    else:
        form = DoacaoPWAForm()
    return render(request, 'pwa/cadastro_doacao.html', {'form': form})


api_cidades = core_api_cidades


def manifest_json(request):
    path = os.path.join(django_settings.BASE_DIR, 'static', 'pwa', 'manifest.json')
    return FileResponse(open(path, 'rb'), content_type='application/manifest+json')


def service_worker(request):
    path = os.path.join(django_settings.BASE_DIR, 'static', 'pwa', 'sw.js')
    return FileResponse(open(path, 'rb'), content_type='application/javascript')
