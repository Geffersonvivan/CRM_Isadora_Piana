import json
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from core.views import api_cidades as core_api_cidades
from .models import Usuario
from .forms import UsuarioCreateForm, UsuarioEditForm, UsuarioPWACreateForm, UsuarioPWAEditForm


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if not request.user.is_authenticated:
            if is_ajax:
                return JsonResponse({'error': 'Não autenticado'}, status=401)
            return redirect('login')
        if request.user.perfil != 'admin' and not request.user.is_superuser:
            if is_ajax:
                return JsonResponse({'error': 'Acesso restrito'}, status=403)
            messages.error(request, 'Acesso restrito a administradores.')
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


def secao_required(secao):
    """Decorator that checks if user has access to a specific section."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            if not request.user.is_authenticated:
                if is_ajax:
                    return JsonResponse({'error': 'Não autenticado'}, status=401)
                return redirect('login')
            if not request.user.pode_acessar(secao):
                if is_ajax:
                    return JsonResponse({'error': 'Acesso restrito'}, status=403)
                messages.error(request, 'Você não tem permissão para acessar esta seção.')
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


@secao_required('config:usuarios')
def usuario_list(request):
    usuarios = Usuario.objects.exclude(vinculo__in=['coordenador', 'cabo', 'replicador'])
    perfil = request.GET.get('perfil')
    busca = request.GET.get('busca')

    if perfil:
        usuarios = usuarios.filter(perfil=perfil)
    if busca:
        from django.db.models import Q
        usuarios = usuarios.filter(
            Q(username__icontains=busca) |
            Q(first_name__icontains=busca) |
            Q(last_name__icontains=busca) |
            Q(email__icontains=busca)
        )

    return render(request, 'usuarios/list.html', {
        'usuarios': usuarios,
        'perfil_choices': Usuario.PERFIL_CHOICES,
        'perfil_filtro': perfil or '',
        'busca': busca or '',
    })


@secao_required('config:usuarios')
def usuario_create(request):
    if request.method == 'POST':
        form = UsuarioCreateForm(request.POST, request.FILES)
        if form.is_valid():
            usuario = form.save()
            messages.success(request, 'Usuário criado com sucesso.')
            return redirect('usuarios:edit', pk=usuario.pk)
    else:
        form = UsuarioCreateForm()
    return render(request, 'usuarios/form.html', {
        'form': form,
        'titulo': 'Novo Usuário',
        'is_create': True,
        'perfil_secoes_json': json.dumps(Usuario.SECOES_PADRAO),
    })


@secao_required('config:usuarios')
def usuario_edit(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == 'POST':
        form = UsuarioEditForm(request.POST, request.FILES, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuário atualizado com sucesso.')
            return redirect('usuarios:list')
    else:
        form = UsuarioEditForm(instance=usuario)
    return render(request, 'usuarios/form.html', {
        'form': form,
        'titulo': f'Editar: {usuario}',
        'usuario_obj': usuario,
        'is_create': False,
        'perfil_secoes_json': json.dumps(Usuario.SECOES_PADRAO),
    })


@secao_required('config:usuarios')
def usuario_toggle(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=['is_active'])
    status = 'ativado' if usuario.is_active else 'desativado'
    messages.success(request, f'Usuário {usuario} {status}.')
    return redirect('usuarios:list')


# ==================== USUÁRIOS PWA ====================

@secao_required('config:usuarios')
def usuario_pwa_list(request):
    from django.db.models import Q, Count
    usuarios = Usuario.objects.filter(vinculo__in=['coordenador', 'cabo', 'replicador']).annotate(
        total_apoiadores=Count('liderancas_cadastradas', filter=Q(liderancas_cadastradas__papel='apoiador', liderancas_cadastradas__aprovacao='aprovado'))
    )

    busca = request.GET.get('busca', '')
    vinculo = request.GET.get('vinculo', '')

    if busca:
        usuarios = usuarios.filter(
            Q(first_name__icontains=busca) | Q(last_name__icontains=busca) |
            Q(username__icontains=busca) | Q(telefone__icontains=busca)
        )
    if vinculo:
        usuarios = usuarios.filter(vinculo=vinculo)

    return render(request, 'usuarios/pwa_list.html', {
        'usuarios': usuarios,
        'vinculo_choices': Usuario.VINCULO_CHOICES,
        'vinculo_filtro': vinculo,
        'busca': busca,
        'total': usuarios.count(),
    })


@secao_required('config:usuarios')
def usuario_pwa_create(request):
    if request.method == 'POST':
        form = UsuarioPWACreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuário PWA criado com sucesso.')
            return redirect('usuarios:pwa_list')
    else:
        form = UsuarioPWACreateForm()
    return render(request, 'usuarios/pwa_form.html', {
        'form': form,
        'titulo': 'Novo Usuário PWA',
    })


@secao_required('config:usuarios')
def usuario_pwa_edit(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == 'POST':
        form = UsuarioPWAEditForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuário PWA atualizado com sucesso.')
            return redirect('usuarios:pwa_list')
    else:
        form = UsuarioPWAEditForm(instance=usuario)
    return render(request, 'usuarios/pwa_form.html', {
        'form': form,
        'titulo': f'Editar: {usuario}',
    })


api_cidades_por_regiao = core_api_cidades
