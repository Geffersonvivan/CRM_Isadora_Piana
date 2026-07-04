from django.conf import settings
from django.db import models


class Notificacao(models.Model):
    TIPO_CHOICES = [
        ('mencao', 'Menção em comentário'),
        ('atribuicao', 'Atribuído como responsável'),
        ('participante', 'Adicionado como participante'),
        ('resposta', 'Resposta ao seu comentário'),
        ('prazo', 'Prazo próximo do vencimento'),
        ('lead_pwa', 'Novo lead do app'),
    ]

    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notificacoes',
        db_index=True,
    )
    remetente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notificacoes_enviadas',
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    tarefa = models.ForeignKey(
        'tarefas.Tarefa',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='notificacoes',
    )
    comentario = models.ForeignKey(
        'tarefas.Comentario',
        on_delete=models.CASCADE,
        null=True, blank=True,
    )
    # Link genérico p/ notificações que não são de tarefa (ex.: lead do app)
    url = models.CharField(max_length=300, blank=True)
    texto = models.CharField(max_length=300)
    lida = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notificação'
        verbose_name_plural = 'Notificações'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.destinatario} — {self.texto}'
