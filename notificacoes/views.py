import re
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .models import Notificacao


@login_required
def api_count(request):
    """Returns unread notification count for the current user."""
    count = Notificacao.objects.filter(
        destinatario=request.user, lida=False
    ).count()
    return JsonResponse({'count': count})


@login_required
def api_list(request):
    """Returns recent notifications for the current user."""
    notifs = Notificacao.objects.filter(
        destinatario=request.user
    ).select_related('remetente', 'tarefa')[:30]

    return JsonResponse({'notificacoes': [
        {
            'id': n.id,
            'tipo': n.tipo,
            'texto': n.texto,
            'tarefa_id': n.tarefa_id,
            'tarefa_titulo': n.tarefa.titulo if n.tarefa else '',
            'url': n.url,
            'remetente': n.remetente.get_full_name() if n.remetente else '',
            'remetente_initials': (
                (n.remetente.first_name[:1] + n.remetente.last_name[:1]).upper()
                if n.remetente else '??'
            ),
            'lida': n.lida,
            'created_at': _relative_date(n.created_at),
        }
        for n in notifs
    ]})


@login_required
@require_POST
def api_mark_read(request):
    """Mark one or all notifications as read."""
    notif_id = request.POST.get('id')
    if notif_id:
        Notificacao.objects.filter(
            id=notif_id, destinatario=request.user
        ).update(lida=True)
    else:
        Notificacao.objects.filter(
            destinatario=request.user, lida=False
        ).update(lida=True)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def api_dismiss(request):
    """Remove (dispensa) uma notificação do usuário."""
    notif_id = request.POST.get('id')
    if notif_id:
        Notificacao.objects.filter(id=notif_id, destinatario=request.user).delete()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def api_clear_read(request):
    """Remove todas as notificações já lidas do usuário."""
    Notificacao.objects.filter(destinatario=request.user, lida=True).delete()
    return JsonResponse({'ok': True})


def _relative_date(dt):
    from django.utils import timezone
    now = timezone.now()
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return 'agora'
    if seconds < 3600:
        return f'{seconds // 60}min'
    if seconds < 86400:
        return f'{seconds // 3600}h'
    days = seconds // 86400
    if days == 1:
        return 'ontem'
    if days < 7:
        return f'{days}d'
    return dt.strftime('%d/%m/%Y')


def criar_notificacao_lead_pwa(remetente, qtd):
    """Avisa os aprovadores (perfil admin ou seção liderancas:aprovar) que
    chegaram novos leads do app aguardando aprovação."""
    from usuarios.models import Usuario
    if qtd <= 0:
        return
    texto = ('cadastrou um novo lead no app' if qtd == 1
             else f'cadastrou {qtd} novos leads no app') + ' — aguardando aprovação'
    remetente_id = getattr(remetente, 'id', None)
    for u in Usuario.objects.filter(is_active=True):
        if u.id == remetente_id:
            continue
        try:
            if not u.pode_acessar('liderancas:aprovar'):
                continue
        except Exception:
            continue
        Notificacao.objects.create(
            destinatario=u, remetente=remetente, tipo='lead_pwa',
            tarefa=None, url='/liderancas/?aprovacao=pendente', texto=texto,
        )


def criar_notificacao_voluntario_pwa(remetente, qtd):
    """Avisa os aprovadores de Equipes (seção equipes:aprovar) que chegaram
    novos voluntários do app aguardando aprovação."""
    from usuarios.models import Usuario
    if qtd <= 0:
        return
    texto = ('cadastrou um novo voluntário no app' if qtd == 1
             else f'cadastrou {qtd} novos voluntários no app') + ' — aguardando aprovação'
    remetente_id = getattr(remetente, 'id', None)
    for u in Usuario.objects.filter(is_active=True):
        if u.id == remetente_id:
            continue
        try:
            if not u.pode_acessar('equipes:aprovar'):
                continue
        except Exception:
            continue
        Notificacao.objects.create(
            destinatario=u, remetente=remetente, tipo='lead_pwa',
            tarefa=None, url='/liderancas/mobilizacao/?aprovacao=pendente', texto=texto,
        )


def criar_notificacoes_mencao(texto, tarefa, comentario, remetente):
    """Extract @mentions from text and create notifications."""
    from usuarios.models import Usuario

    # Find all @mentions
    mentions = re.findall(r'@([\wÀ-ÿ]+(?: [\wÀ-ÿ]+)*)', texto)
    if not mentions:
        return

    for mention_name in mentions:
        # Try to find user by full name
        parts = mention_name.strip().split()
        if not parts:
            continue

        users = Usuario.objects.filter(
            first_name__iexact=parts[0]
        )
        if len(parts) >= 2:
            users = users.filter(last_name__iexact=parts[-1])

        for user in users:
            if user.id == remetente.id:
                continue  # Don't notify yourself
            Notificacao.objects.create(
                destinatario=user,
                remetente=remetente,
                tipo='mencao',
                tarefa=tarefa,
                comentario=comentario,
                texto=f'te mencionou em "{tarefa.titulo[:50]}"',
            )


def criar_notificacao_resposta(comentario_parent, comentario_novo, remetente):
    """Notify the author of a parent comment when someone replies."""
    if not comentario_parent.autor or comentario_parent.autor == remetente:
        return

    Notificacao.objects.create(
        destinatario=comentario_parent.autor,
        remetente=remetente,
        tipo='resposta',
        tarefa=comentario_novo.tarefa,
        comentario=comentario_novo,
        texto=f'respondeu ao seu comentário em "{comentario_novo.tarefa.titulo[:50]}"',
    )


def criar_notificacao_atribuicao(tarefa, remetente):
    """Notify user when assigned as responsible."""
    if not tarefa.responsavel or tarefa.responsavel == remetente:
        return

    # Avoid duplicate
    if Notificacao.objects.filter(
        destinatario=tarefa.responsavel, tarefa=tarefa,
        tipo='atribuicao', lida=False
    ).exists():
        return

    Notificacao.objects.create(
        destinatario=tarefa.responsavel,
        remetente=remetente,
        tipo='atribuicao',
        tarefa=tarefa,
        texto=f'te atribuiu como responsável em "{tarefa.titulo[:50]}"',
    )


def criar_notificacao_participante(tarefa, user, remetente):
    """Notify user when added as participant."""
    if user == remetente:
        return

    if Notificacao.objects.filter(
        destinatario=user, tarefa=tarefa,
        tipo='participante', lida=False
    ).exists():
        return

    Notificacao.objects.create(
        destinatario=user,
        remetente=remetente,
        tipo='participante',
        tarefa=tarefa,
        texto=f'te adicionou como participante em "{tarefa.titulo[:50]}"',
    )


def criar_notificacao_mudanca(tarefa, remetente, campo, valor_display):
    """Notify responsible and participants when status/priority changes."""
    from usuarios.models import Usuario

    CAMPO_LABELS = {
        'fase': 'status',
        'prioridade': 'prioridade',
    }
    label = CAMPO_LABELS.get(campo, campo)
    texto = f'alterou {label} para "{valor_display}" em "{tarefa.titulo[:40]}"'

    destinatarios = set()
    if tarefa.responsavel_id:
        destinatarios.add(tarefa.responsavel_id)
    for p in tarefa.participantes.values_list('id', flat=True):
        destinatarios.add(p)
    destinatarios.discard(remetente.id)

    for uid in destinatarios:
        Notificacao.objects.create(
            destinatario_id=uid,
            remetente=remetente,
            tipo='atribuicao',
            tarefa=tarefa,
            texto=texto,
        )


def criar_notificacoes_prazo():
    """Create notifications for tasks with deadline approaching (tomorrow) or overdue."""
    from tarefas.models import Tarefa
    from datetime import date, timedelta

    amanha = date.today() + timedelta(days=1)
    hoje = date.today()

    # Prazo amanhã
    tarefas_amanha = Tarefa.objects.filter(
        prazo=amanha,
        excluida_em__isnull=True,
    ).exclude(fase='concluida').select_related('responsavel').prefetch_related('participantes')

    for tarefa in tarefas_amanha:
        _notificar_prazo(tarefa, 'vence amanhã')

    # Prazo hoje
    tarefas_hoje = Tarefa.objects.filter(
        prazo=hoje,
        excluida_em__isnull=True,
    ).exclude(fase='concluida').select_related('responsavel').prefetch_related('participantes')

    for tarefa in tarefas_hoje:
        _notificar_prazo(tarefa, 'vence hoje')

    # Prazo vencido (ontem)
    ontem = hoje - timedelta(days=1)
    tarefas_vencidas = Tarefa.objects.filter(
        prazo=ontem,
        excluida_em__isnull=True,
    ).exclude(fase='concluida').select_related('responsavel').prefetch_related('participantes')

    for tarefa in tarefas_vencidas:
        _notificar_prazo(tarefa, 'está vencida')


def _notificar_prazo(tarefa, msg):
    """Send prazo notification to responsible and participants."""
    destinatarios = set()
    if tarefa.responsavel_id:
        destinatarios.add(tarefa.responsavel_id)
    for p in tarefa.participantes.values_list('id', flat=True):
        destinatarios.add(p)

    texto = f'"{tarefa.titulo[:50]}" {msg}'

    for uid in destinatarios:
        if not Notificacao.objects.filter(
            destinatario_id=uid, tarefa=tarefa,
            tipo='prazo', lida=False, texto=texto,
        ).exists():
            Notificacao.objects.create(
                destinatario_id=uid,
                tipo='prazo',
                tarefa=tarefa,
                texto=texto,
            )
