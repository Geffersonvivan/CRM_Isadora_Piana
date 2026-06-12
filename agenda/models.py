from django.conf import settings
from django.db import models
from liderancas.models import Regiao, Cidade


class Compromisso(models.Model):
    TIPO_CHOICES = [
        ('reuniao', 'Reunião'),
        ('evento', 'Evento'),
        ('visita', 'Visita'),
        ('comicio', 'Comício'),
        ('entrevista', 'Entrevista'),
        ('viagem', 'Viagem'),
        ('pessoal', 'Pessoal'),
    ]
    PRIORIDADE_CHOICES = [
        ('alta', 'Alta'),
        ('media', 'Média'),
        ('baixa', 'Baixa'),
    ]
    STATUS_CHOICES = [
        ('confirmado', 'Confirmado'),
        ('pendente', 'Pendente'),
        ('cancelado', 'Cancelado'),
        ('realizado', 'Realizado'),
    ]
    TIPO_COR = {
        'reuniao': '#0073ea',
        'evento': '#a25ddc',
        'visita': '#00c875',
        'comicio': '#e2445c',
        'entrevista': '#fdab3d',
        'viagem': '#579bfc',
        'pessoal': '#c4c4c4',
    }

    titulo = models.CharField(max_length=200, verbose_name='Título')
    descricao = models.TextField(blank=True, verbose_name='Descrição')
    data_hora_inicio = models.DateTimeField('Início')
    data_hora_fim = models.DateTimeField('Fim')
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES)
    regiao = models.ForeignKey(
        Regiao, on_delete=models.PROTECT, related_name='compromissos',
        verbose_name='Região',
    )
    cidade = models.ForeignKey(
        Cidade, on_delete=models.PROTECT, related_name='compromissos',
    )
    endereco = models.CharField('Endereço', max_length=300, blank=True)
    contato_local_nome = models.CharField(
        'Nome do Contato Local', max_length=200, blank=True,
    )
    contato_local_telefone = models.CharField(
        'Telefone do Contato', max_length=20, blank=True,
    )
    participantes = models.TextField(blank=True)
    coordenadores = models.ManyToManyField(
        'liderancas.CoordenadorRegional', blank=True, related_name='compromissos',
        verbose_name='Coordenadores participantes',
    )
    cabos = models.ManyToManyField(
        'liderancas.CaboEleitoral', blank=True, related_name='compromissos',
        verbose_name='Cabos participantes',
    )
    apoiadores = models.ManyToManyField(
        'liderancas.Apoiador', blank=True, related_name='compromissos',
        verbose_name='Apoiadores participantes',
    )
    interacoes_geradas = models.BooleanField(
        default=False,
        help_text='Interações já criadas para os participantes ao realizar o compromisso.',
    )
    prioridade = models.CharField(
        max_length=10, choices=PRIORIDADE_CHOICES, default='media',
    )
    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='pendente',
    )
    observacoes = models.TextField('Observações', blank=True)

    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='compromissos_cadastrados',
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='compromissos_atualizados',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Compromisso'
        verbose_name_plural = 'Compromissos'
        ordering = ['data_hora_inicio']

    @property
    def cor(self):
        return self.TIPO_COR.get(self.tipo, '#002776')

    def gerar_interacoes(self, user=None):
        """Cria InteracaoLog para cada participante quando o compromisso é realizado.

        Idempotente: roda uma única vez por compromisso (interacoes_geradas).
        Retorna o número de interações criadas.
        """
        if self.status != 'realizado' or self.interacoes_geradas:
            return 0
        from liderancas.models import InteracaoLog
        tipo_map = {
            'visita': 'visita', 'reuniao': 'reuniao', 'evento': 'evento',
            'comicio': 'evento', 'entrevista': 'outro', 'viagem': 'visita',
            'pessoal': 'outro',
        }
        tipo = tipo_map.get(self.tipo, 'outro')
        descricao = (
            f'Compromisso realizado: {self.titulo} — '
            f'{self.cidade.nome} ({self.data_hora_inicio:%d/%m/%Y})'
        )
        criadas = 0
        for m2m, fk in (('coordenadores', 'coordenador'), ('cabos', 'cabo'), ('apoiadores', 'apoiador')):
            for contato in getattr(self, m2m).all():
                InteracaoLog.objects.create(
                    **{fk: contato},
                    tipo=tipo,
                    descricao=descricao,
                    data=self.data_hora_inicio,
                    registrado_por=user,
                )
                criadas += 1
        if criadas:
            self.interacoes_geradas = True
            self.save(update_fields=['interacoes_geradas'])
        return criadas

    def __str__(self):
        return f'{self.titulo} — {self.data_hora_inicio:%d/%m/%Y %H:%M}'


class Roteiro(models.Model):
    STATUS_CHOICES = [
        ('planejado', 'Planejado'),
        ('em_andamento', 'Em Andamento'),
        ('concluido', 'Concluído'),
    ]

    data = models.DateField()
    titulo = models.CharField(max_length=200, verbose_name='Título')
    regiao = models.ForeignKey(
        Regiao, on_delete=models.PROTECT, related_name='roteiros',
        verbose_name='Região Principal',
    )
    motorista = models.CharField(max_length=200, blank=True)
    observacoes = models.TextField('Observações', blank=True)
    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='planejado',
    )

    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='roteiros_cadastrados',
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='roteiros_atualizados',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Roteiro'
        verbose_name_plural = 'Roteiros'
        ordering = ['-data']

    def __str__(self):
        return f'{self.titulo} — {self.data:%d/%m/%Y}'


class RoteiroPonto(models.Model):
    roteiro = models.ForeignKey(
        Roteiro, on_delete=models.CASCADE, related_name='pontos',
    )
    compromisso = models.ForeignKey(
        Compromisso, on_delete=models.CASCADE, related_name='roteiro_pontos',
    )
    ordem = models.PositiveIntegerField(default=0)
    observacao_ponto = models.TextField('Observação do Ponto', blank=True)

    class Meta:
        verbose_name = 'Ponto do Roteiro'
        verbose_name_plural = 'Pontos do Roteiro'
        ordering = ['ordem']
        unique_together = [('roteiro', 'compromisso')]

    def __str__(self):
        return f'{self.ordem}. {self.compromisso.titulo}'


class Evento(models.Model):
    TIPO_CHOICES = [
        ('inauguracao', 'Inauguração'),
        ('festa', 'Festa'),
        ('feira', 'Feira'),
        ('encontro', 'Encontro'),
        ('solenidade', 'Solenidade'),
        ('audiencia', 'Audiência Pública'),
        ('debate', 'Debate'),
        ('palestra', 'Palestra'),
        ('show', 'Show / Apresentação'),
        ('esportivo', 'Evento Esportivo'),
        ('religioso', 'Evento Religioso'),
        ('outro', 'Outro'),
    ]
    RELEVANCIA_CHOICES = [
        ('alta', 'Alta'),
        ('media', 'Média'),
        ('baixa', 'Baixa'),
    ]
    STATUS_CHOICES = [
        ('identificado', 'Identificado'),
        ('avaliando', 'Avaliando'),
        ('confirmado', 'Presença Confirmada'),
        ('descartado', 'Descartado'),
        ('participou', 'Participou'),
    ]

    nome = models.CharField(max_length=300, verbose_name='Nome do Evento')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    data = models.DateField(verbose_name='Data')
    horario_inicio = models.TimeField(verbose_name='Horário Início', null=True, blank=True)
    horario_fim = models.TimeField(verbose_name='Horário Fim', null=True, blank=True)
    cidade = models.ForeignKey(
        Cidade, on_delete=models.PROTECT, related_name='eventos',
    )
    local = models.CharField(max_length=300, blank=True, verbose_name='Local / Endereço')
    publico_estimado = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Público Estimado',
    )
    relevancia = models.CharField(
        max_length=10, choices=RELEVANCIA_CHOICES, default='media',
        verbose_name='Relevância Política',
    )
    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='identificado',
    )
    observacoes = models.TextField(
        blank=True, verbose_name='Observações',
        help_text='Quem organiza, adversários confirmados, oportunidade de fala, etc.',
    )
    resultado = models.TextField(
        blank=True, verbose_name='Resultado / Avaliação',
        help_text='Preencher após a participação.',
    )
    imagem = models.ImageField(
        upload_to='eventos/', blank=True, null=True,
        verbose_name='Imagem do Evento',
    )
    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='eventos_cadastrados',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Evento'
        verbose_name_plural = 'Eventos'
        ordering = ['data', 'horario_inicio']

    def __str__(self):
        return f'{self.nome} — {self.data:%d/%m/%Y}'
