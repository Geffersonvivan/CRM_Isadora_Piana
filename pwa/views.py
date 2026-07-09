import os
import json
from functools import wraps
from django.conf import settings as django_settings
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse, FileResponse
from django.db import IntegrityError
from django.db.models import Count
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from core.views import api_cidades as core_api_cidades
from core.services import calcular_scores_rede, score_usuario
from django.db.models import Q
from liderancas.models import Lideranca, Cidade, Voluntario
from .forms import ApoiadorPWAForm, ReplicadorForm, VoluntarioPWAForm


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

    # Meu placar (apoiadores cadastrados por mim — só aprovados contam)
    diretos_map, convidados_map = calcular_scores_rede()
    _, _, meu_total, _ = score_usuario(user.id, diretos_map, convidados_map)

    # Meus últimos cadastros
    ultimos = Lideranca.objects.filter(
        papel='apoiador', cadastrado_por=user,
    ).select_related('cidade')[:5]

    return render(request, 'pwa/dashboard.html', {
        'meu_total': meu_total,
        'ultimos': ultimos,
    })


@ensure_csrf_cookie
@pwa_login_required
def cadastro_apoiador(request):
    # POST tradicional é só fallback (sem JS). O fluxo normal usa a fila offline
    # do app.js → /app/api/sync/. Garantimos o cookie CSRF para o sync funcionar.
    if request.method == 'POST':
        form = ApoiadorPWAForm(request.POST, user=request.user)
        if form.is_valid():
            apoiador = form.save(commit=False)
            apoiador.cadastrado_por = request.user
            # Cadastro de campo nasce pendente na fila de moderação (CLAUDE.md §3.1),
            # igual ao api_sync e ao fallback de voluntário — não pular a moderação.
            apoiador.origem = 'pwa'
            apoiador.aprovacao = 'pendente'
            apoiador.status = 'ativo'
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


@ensure_csrf_cookie
@pwa_login_required
def cadastro_voluntario(request):
    # POST tradicional é fallback (sem JS). O fluxo normal usa a fila offline
    # do app_voluntario.js → /app/api/sync-voluntario/.
    if request.method == 'POST':
        form = VoluntarioPWAForm(request.POST)
        if form.is_valid():
            vol = form.save(commit=False)
            vol.cadastrado_por = request.user
            vol.origem = 'pwa'
            vol.aprovacao = 'pendente'
            vol.save()
            messages.success(request, f'{vol.nome} cadastrado para mobilização!')
            return redirect('pwa:cadastro_voluntario')
    else:
        form = VoluntarioPWAForm()
    return render(request, 'pwa/cadastro_voluntario.html', {'form': form})


api_cidades = core_api_cidades


@pwa_login_required
@require_POST
def api_sync(request):
    """Recebe a fila de cadastros offline (JSON) e cria as Lideranças.
    Idempotente por `client_id` (UUID gerado no aparelho) — reenvio não duplica."""
    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    contato_mode = django_settings.CAMPANHA.get('PWA_CADASTRO_CONTATO', False)
    tipos_validos = {c[0] for c in Lideranca.TIPO_CHOICES}
    niveis_validos = {c[0] for c in Lideranca.NIVEL_CHOICES}
    votos_validos = {c[0] for c in Lideranca.INTENCAO_VOTO_CHOICES}
    results = []
    criados = 0
    for rec in (payload.get('records') or [])[:200]:
        cid = (rec.get('client_id') or '').strip()
        if not cid:
            results.append({'client_id': rec.get('client_id'), 'status': 'erro', 'error': 'sem client_id'})
            continue
        if Lideranca.all_objects.filter(pwa_client_id=cid).exists():
            results.append({'client_id': cid, 'status': 'ok'})  # já sincronizado
            continue
        nome = (rec.get('nome') or '').strip()
        cidade_id = rec.get('cidade_id')
        if not nome or not cidade_id:
            results.append({'client_id': cid, 'status': 'erro', 'error': 'Nome e cidade são obrigatórios'})
            continue
        cidade = Cidade.objects.select_related('regiao').filter(pk=cidade_id).first()
        if not cidade:
            results.append({'client_id': cid, 'status': 'erro', 'error': 'Cidade inválida'})
            continue
        # Categoria é múltipla e opcional; só valores válidos entram, vazio fica
        # vazio, e o principal (tipo/nivel) é derivado no save() do model.
        campos_extra = {}
        if contato_mode:
            # Isadora: Categoria = níveis + Vota? = intenção de voto.
            niveis_rec = rec.get('niveis')
            if not isinstance(niveis_rec, list):
                niveis_rec = [rec.get('nivel')] if rec.get('nivel') else []
            campos_extra['niveis'] = [n for n in (str(x).strip() for x in niveis_rec) if n in niveis_validos]
            voto = (rec.get('intencao_voto') or '').strip()
            campos_extra['intencao_voto'] = voto if voto in votos_validos else ''
        else:
            # Demais marcas: aceita a lista `tipos` (novo) ou o `tipo` único (filas antigas).
            tipos_rec = rec.get('tipos')
            if not isinstance(tipos_rec, list):
                tipos_rec = [rec.get('tipo')] if rec.get('tipo') else []
            campos_extra['tipos'] = [t for t in (str(x).strip() for x in tipos_rec) if t in tipos_validos]
        try:
            Lideranca.objects.create(
                papel='apoiador', nome=nome, cidade=cidade, regiao=cidade.regiao,
                telefone=(rec.get('telefone') or '').strip(),
                observacoes=(rec.get('observacoes') or '').strip(),
                status='ativo', cadastrado_por=request.user, pwa_client_id=cid,
                origem='pwa', aprovacao='pendente', **campos_extra,
            )
            criados += 1
            results.append({'client_id': cid, 'status': 'ok'})
        except IntegrityError:
            results.append({'client_id': cid, 'status': 'ok'})  # corrida: já criado
        except Exception as e:  # noqa
            results.append({'client_id': cid, 'status': 'erro', 'error': str(e)[:120]})

    if criados:
        from notificacoes.views import criar_notificacao_lead_pwa
        criar_notificacao_lead_pwa(request.user, criados)

    return JsonResponse({'results': results})


@pwa_login_required
@require_POST
def api_sync_voluntario(request):
    """Recebe a fila offline de voluntários (JSON) e cria os Voluntários.
    Idempotente por `client_id`; entram como 'pendente' (origem pwa)."""
    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    disp_validas = {c[0] for c in Voluntario.DISPONIBILIDADE_CHOICES}
    results = []
    criados = 0
    for rec in (payload.get('records') or [])[:200]:
        cid = (rec.get('client_id') or '').strip()
        if not cid:
            results.append({'client_id': rec.get('client_id'), 'status': 'erro', 'error': 'sem client_id'})
            continue
        if Voluntario.all_objects.filter(pwa_client_id=cid).exists():
            results.append({'client_id': cid, 'status': 'ok'})
            continue
        nome = (rec.get('nome') or '').strip()
        telefone = (rec.get('telefone') or '').strip()
        cidade_id = rec.get('cidade_id')
        if not nome or not telefone or not cidade_id:
            results.append({'client_id': cid, 'status': 'erro', 'error': 'Nome, telefone e cidade são obrigatórios'})
            continue
        cidade = Cidade.objects.select_related('regiao').filter(pk=cidade_id).first()
        if not cidade:
            results.append({'client_id': cid, 'status': 'erro', 'error': 'Cidade inválida'})
            continue
        disp = [d for d in (rec.get('disponibilidades') or []) if d in disp_validas]
        try:
            Voluntario.objects.create(
                nome=nome, telefone=telefone, cidade=cidade, regiao=cidade.regiao,
                disponibilidades=disp, observacoes=(rec.get('observacoes') or '').strip(),
                cadastrado_por=request.user, pwa_client_id=cid,
                origem='pwa', aprovacao='pendente',
            )
            criados += 1
            results.append({'client_id': cid, 'status': 'ok'})
        except IntegrityError:
            results.append({'client_id': cid, 'status': 'ok'})
        except Exception as e:  # noqa
            results.append({'client_id': cid, 'status': 'erro', 'error': str(e)[:120]})

    if criados:
        from notificacoes.views import criar_notificacao_voluntario_pwa
        criar_notificacao_voluntario_pwa(request.user, criados)

    return JsonResponse({'results': results})


@pwa_login_required
@require_POST
def api_transcrever(request):
    """Transcreve um áudio (online) via Whisper e devolve o texto p/ Observações.
    Requer OPENAI_API_KEY no servidor (configurável: WHISPER_MODEL / WHISPER_BASE_URL)."""
    audio = request.FILES.get('audio')
    if not audio:
        return JsonResponse({'error': 'Nenhum áudio enviado.'}, status=400)

    key = getattr(django_settings, 'OPENAI_API_KEY', '')
    if not key:
        return JsonResponse({'error': 'Transcrição não configurada no servidor.'}, status=503)

    import requests
    base = getattr(django_settings, 'WHISPER_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    model = getattr(django_settings, 'WHISPER_MODEL', 'whisper-1')
    try:
        resp = requests.post(
            f'{base}/audio/transcriptions',
            headers={'Authorization': f'Bearer {key}'},
            files={'file': (audio.name or 'audio.m4a', audio.read(), audio.content_type or 'audio/m4a')},
            data={'model': model, 'language': 'pt', 'response_format': 'json'},
            timeout=90,
        )
    except requests.RequestException:
        return JsonResponse({'error': 'Falha de rede ao transcrever.'}, status=502)

    if resp.status_code != 200:
        return JsonResponse({'error': f'Serviço de transcrição retornou {resp.status_code}.'}, status=502)
    try:
        data = resp.json()
    except ValueError:
        return JsonResponse({'error': 'Resposta inválida do serviço de transcrição.'}, status=502)
    return JsonResponse({'text': (data.get('text') or '').strip()})


def manifest_json(request):
    """Manifest do PWA com a marca injetada da config (o JSON estático é a base
    neutra). Nome/descrição/cores mudam por marca sem tocar no arquivo."""
    path = os.path.join(django_settings.BASE_DIR, 'static', 'pwa', 'manifest.json')
    with open(path, encoding='utf-8') as f:
        manifest = json.load(f)
    c = django_settings.CAMPANHA
    curto = f"{c['CANDIDATO_PRIMEIRO_NOME']} {c['PARTIDO_NUMERO']}"
    manifest['name'] = f"{curto} — Operação de Campo"
    manifest['short_name'] = curto
    manifest['description'] = (
        f"Cadastro de apoiadores e voluntários — Campanha {c['CANDIDATO_NOME']}, "
        f"{c['PARTIDO_SIGLA']} {c['PARTIDO_NUMERO']}, {c['UF']}"
    )
    grafite = c['CORES'].get('--navy-900')
    if grafite:
        manifest['background_color'] = grafite
        manifest['theme_color'] = grafite
    return JsonResponse(manifest, content_type='application/manifest+json')


def service_worker(request):
    path = os.path.join(django_settings.BASE_DIR, 'static', 'pwa', 'sw.js')
    return FileResponse(open(path, 'rb'), content_type='application/javascript')
