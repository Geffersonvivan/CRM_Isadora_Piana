from django.conf import settings
from django.db import models
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone


class Tarefa(models.Model):
    # "Área" da campanha (setor dono da tarefa). Mantemos o nome de campo `tipo`
    # por compatibilidade, mas o significado e os rótulos são de ÁREA/setor.
    TIPO_CHOICES = [
        ('financeiro', 'Financeiro'),
        ('administrativo', 'Administrativo'),
        ('comunicacao', 'Comunicação'),
        ('mobilizacao', 'Mobilização'),
        ('estrategico', 'Estratégico'),
        ('eventos', 'Eventos'),
    ]
    AREA_CHOICES = TIPO_CHOICES  # alias semântico

    FASE_CHOICES = [
        ('a_fazer', 'A Fazer'),
        ('em_andamento', 'Em Andamento'),
        ('aguardando', 'Aguardando'),
        ('concluida', 'Concluída'),
    ]

    PRIORIDADE_CHOICES = [
        ('baixa', 'Baixa'),
        ('media', 'Média'),
        ('alta', 'Alta'),
        ('urgente', 'Urgente'),
    ]

    titulo = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='administrativo', verbose_name='Área')
    fase = models.CharField(max_length=20, choices=FASE_CHOICES, default='a_fazer', db_index=True)
    prioridade = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES, default='media')
    ordem = models.PositiveIntegerField(default=0)

    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='tarefas_responsavel',
        verbose_name='Responsável',
        db_index=True,
    )
    participantes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='tarefas_participante',
        verbose_name='Participantes',
    )

    regiao = models.ForeignKey(
        'liderancas.Regiao',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='tarefas',
        db_index=True,
    )
    cidade = models.ForeignKey(
        'liderancas.Cidade',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='tarefas',
    )
    cabos = models.ManyToManyField(
        'liderancas.Lideranca',
        blank=True,
        related_name='tarefas',
        limit_choices_to={'papel': 'cabo'},
        verbose_name='Cabos Eleitorais',
    )

    data_hora_inicio = models.DateTimeField(null=True, blank=True, verbose_name='Hora de início')
    data_hora_termino = models.DateTimeField(null=True, blank=True, verbose_name='Hora de término')
    prazo = models.DateField(null=True, blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)
    observacoes = models.TextField(blank=True, verbose_name='Observações')

    # Link genérico (documento, referência, planilha…) — clicável na lista.
    link = models.URLField(blank=True, max_length=500, verbose_name='Link')
    # Link da reunião (videochamada) — vira botão "Entrar" na lista.
    link_reuniao = models.URLField(blank=True, max_length=500, verbose_name='Link da reunião')

    compromisso = models.ForeignKey(
        'agenda.Compromisso',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='tarefas',
        verbose_name='Compromisso vinculado',
    )
    # Follow-up atrelado a um contato/apoiador específico da planilha. Vínculo pelo
    # pk (id interno), não por telefone/nome — some com ambiguidade de homônimos.
    contato = models.ForeignKey(
        'liderancas.Lideranca',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='follow_ups',
        verbose_name='Contato (follow-up)',
    )

    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='tarefas_cadastradas',
        db_index=True,
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='tarefas_atualizadas',
    )
    excluida_em = models.DateTimeField(null=True, blank=True, verbose_name='Excluída em', db_index=True)
    excluida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='tarefas_excluidas',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tarefa'
        verbose_name_plural = 'Tarefas'
        ordering = ['ordem', '-prioridade', 'prazo']

    def __str__(self):
        return self.titulo

    @property
    def is_vencida(self):
        if self.prazo and self.fase != 'concluida':
            from datetime import date
            return self.prazo < date.today()
        return False

    @property
    def vence_hoje(self):
        if self.prazo and self.fase != 'concluida':
            from datetime import date
            return self.prazo == date.today()
        return False


class Comentario(models.Model):
    tarefa = models.ForeignKey(
        Tarefa,
        on_delete=models.CASCADE,
        related_name='comentarios',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='respostas',
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        db_index=True,
    )
    texto = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Comentário'
        verbose_name_plural = 'Comentários'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.autor} — {self.tarefa}'


class AnexoComentario(models.Model):
    comentario = models.ForeignKey(
        Comentario,
        on_delete=models.CASCADE,
        related_name='anexos',
    )
    arquivo = models.FileField(upload_to='tarefas/anexos/%Y/%m/')
    nome_original = models.CharField(max_length=255)
    tamanho = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'

    def __str__(self):
        return self.nome_original

    @property
    def extensao(self):
        return self.nome_original.rsplit('.', 1)[-1].lower() if '.' in self.nome_original else ''

    @property
    def is_imagem(self):
        return self.extensao in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'svg')


class TarefaHistorico(models.Model):
    tarefa = models.ForeignKey(
        Tarefa,
        on_delete=models.CASCADE,
        related_name='historico',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    campo = models.CharField(max_length=50)
    valor_anterior = models.TextField(blank=True, default='')
    valor_novo = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Histórico da Tarefa'
        verbose_name_plural = 'Históricos das Tarefas'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.tarefa} — {self.campo} ({self.created_at:%d/%m/%Y %H:%M})'


class ItemChecklist(models.Model):
    """Item marcável de uma tarefa (checklist). Sub-item leve — NÃO é uma Tarefa
    (não entra no board). Pode ser convertido em Tarefa depois (vira_tarefa)."""
    tarefa = models.ForeignKey(
        Tarefa,
        on_delete=models.CASCADE,
        related_name='itens_checklist',
    )
    texto = models.CharField(max_length=300)
    concluido = models.BooleanField(default=False)
    ordem = models.PositiveIntegerField(default=0)
    concluido_em = models.DateTimeField(null=True, blank=True)
    concluido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='itens_checklist_concluidos',
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='itens_checklist_criados',
    )
    # Quando o item é convertido em uma Tarefa própria, guardamos o vínculo.
    vira_tarefa = models.ForeignKey(
        Tarefa,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='origem_item_checklist',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Item de Checklist'
        verbose_name_plural = 'Itens de Checklist'
        ordering = ['ordem', 'created_at']

    def __str__(self):
        return f'{self.tarefa} — {self.texto[:40]}'


# ── Follow-up: fecha o ciclo no histórico do contato ─────────────
# Quando uma tarefa vinculada a um contato (follow-up) é concluída, registra
# uma interação na Lideranca. Só dispara para tarefas com contato — as demais
# marcas nunca preenchem esse FK, então isto é naturalmente exclusivo da Isadora.

@receiver(pre_save, sender=Tarefa)
def _tarefa_captura_fase_antiga(sender, instance, **kwargs):
    if instance.pk:
        instance._old_fase = (
            Tarefa.objects.filter(pk=instance.pk)
            .values_list('fase', flat=True).first()
        )
    else:
        instance._old_fase = None


@receiver(post_save, sender=Tarefa)
def _tarefa_followup_interacao(sender, instance, created, **kwargs):
    if created or not instance.contato_id:
        return
    if instance.fase != 'concluida' or getattr(instance, '_old_fase', None) == 'concluida':
        return
    from liderancas.models import InteracaoLog
    InteracaoLog.objects.create(
        lideranca_id=instance.contato_id,
        tipo='outro',
        descricao=f'Follow-up concluído: {instance.titulo}',
        registrado_por=instance.atualizado_por or instance.cadastrado_por,
    )


