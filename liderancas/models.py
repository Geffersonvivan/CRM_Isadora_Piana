from django.conf import settings
from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def deleted(self):
        return self.filter(is_active=False)


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).active()

    def all_with_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db)

    def deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db).deleted()


class SoftDeleteMixin(models.Model):
    is_active = models.BooleanField(default=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
    )

    objects = SoftDeleteManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def soft_delete(self, user=None):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=['is_active', 'deleted_at', 'deleted_by'])

    def restore(self):
        self.is_active = True
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_active', 'deleted_at', 'deleted_by'])


class MacroRegiao(models.Model):
    nome = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    populacao = models.IntegerField(default=0)
    geojson = models.JSONField(null=True, blank=True)
    cor = models.CharField(max_length=7, default='#3388ff')

    class Meta:
        verbose_name = 'Macro Região'
        verbose_name_plural = 'Macro Regiões'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Regiao(models.Model):
    nome = models.CharField(max_length=100)
    sigla = models.CharField(max_length=20, unique=True)
    nome_completo = models.CharField(max_length=255, blank=True)
    slug = models.SlugField(unique=True, null=True, blank=True)
    macro_regiao = models.ForeignKey(
        MacroRegiao, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='regioes',
    )
    populacao = models.IntegerField(default=0)
    eleitores = models.IntegerField(default=0)
    geojson = models.JSONField(null=True, blank=True)
    cor = models.CharField(max_length=7, default='#3388ff')
    meta_votos = models.IntegerField(default=0)
    meta_doacoes = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Região'
        verbose_name_plural = 'Regiões'
        ordering = ['nome']

    def __str__(self):
        return f'{self.sigla} - {self.nome}'


class Cidade(models.Model):
    nome = models.CharField(max_length=100)
    regiao = models.ForeignKey(Regiao, on_delete=models.PROTECT, related_name='cidades')
    slug = models.SlugField(db_index=True, null=True, blank=True)
    codigo_ibge = models.CharField(max_length=10, unique=True, null=True, blank=True)
    populacao = models.IntegerField(default=0)
    eleitores = models.IntegerField(default=0)
    geojson = models.JSONField(null=True, blank=True)
    prefeito_nome = models.CharField(max_length=200, blank=True)
    prefeito_partido = models.CharField(max_length=50, blank=True)
    num_vereadores = models.IntegerField(default=0)
    num_vereadores_pl = models.IntegerField(default=0)
    presidente_pl = models.CharField(max_length=200, blank=True, verbose_name='Presidente Diretório PL')
    votos_sorgatto_2022 = models.IntegerField(default=0)
    meta_votos = models.IntegerField(default=0)
    meta_doacoes = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    zona_eleitoral = models.CharField(max_length=50, blank=True)

    latitude = models.FloatField(null=True, blank=True, verbose_name='Latitude')
    longitude = models.FloatField(null=True, blank=True, verbose_name='Longitude')

    CONTROLE_CHOICES = [
        ('aliado', 'Aliado'),
        ('neutro', 'Neutro'),
        ('disputado', 'Em disputa'),
        ('adversario', 'Adversário'),
    ]
    controle = models.CharField(
        max_length=12, choices=CONTROLE_CHOICES, blank=True,
        verbose_name='Controle político',
        help_text='Quem domina a cidade politicamente (vazio = não classificado).',
    )
    controle_manual = models.BooleanField(
        default=False,
        help_text='Marcado à mão — a auto-detecção não sobrescreve.',
    )
    adversario_nome = models.CharField(max_length=200, blank=True, verbose_name='Adversário (quem controla)')
    adversario_partido = models.CharField(max_length=50, blank=True, verbose_name='Partido do adversário')

    class Meta:
        ordering = ['nome']
        unique_together = [['slug', 'regiao']]

    def save(self, *args, **kwargs):
        if not self.latitude or not self.longitude:
            try:
                import urllib.request, json, urllib.parse
                cidade_encoded = urllib.parse.quote(f"{self.nome}, Santa Catarina, Brasil")
                url = f"https://nominatim.openstreetmap.org/search?q={cidade_encoded}&format=json&limit=1"
                req = urllib.request.Request(url, headers={'User-Agent': 'CRM-Sorgatto-App'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    if data:
                        self.latitude = float(data[0]['lat'])
                        self.longitude = float(data[0]['lon'])
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome


class Bairro(models.Model):
    nome = models.CharField(max_length=200)
    slug = models.SlugField(db_index=True)
    cidade = models.ForeignKey(Cidade, on_delete=models.CASCADE, related_name='bairros')
    populacao = models.IntegerField(default=0)
    geojson = models.JSONField(null=True, blank=True)
    meta_votos = models.IntegerField(default=0)
    meta_doacoes = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Bairro'
        verbose_name_plural = 'Bairros'
        ordering = ['nome']
        unique_together = [['slug', 'cidade']]

    def __str__(self):
        return f'{self.nome} — {self.cidade}'


class ZonaEleitoral(models.Model):
    numero = models.CharField(max_length=10)
    cidade = models.ForeignKey(Cidade, on_delete=models.CASCADE, related_name='zonas_eleitorais')
    eleitores = models.IntegerField(default=0)
    local = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Zona Eleitoral'
        verbose_name_plural = 'Zonas Eleitorais'
        ordering = ['numero']

    def __str__(self):
        return f'Zona {self.numero} — {self.cidade}'


class CoordenadorRegional(SoftDeleteMixin, models.Model):
    PRIORIDADE_CHOICES = [
        ('alta', 'Alta'),
        ('media', 'Média'),
        ('baixa', 'Baixa'),
    ]
    FREQUENCIA_CHOICES = [
        ('semanal', 'Semanal'),
        ('quinzenal', 'Quinzenal'),
        ('mensal', 'Mensal'),
        ('eventual', 'Eventual'),
    ]

    nome = models.CharField(max_length=200)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    regiao = models.ForeignKey(Regiao, on_delete=models.PROTECT, related_name='coordenadores')
    cidade_base = models.ForeignKey(
        Cidade, on_delete=models.PROTECT, related_name='coordenadores',
        verbose_name='Cidade Base',
    )
    instagram = models.CharField(max_length=100, blank=True)
    prioridade = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES, default='media', verbose_name='Prioridade Comunicação')
    frequencia_relacionamento = models.CharField(
        max_length=15, choices=FREQUENCIA_CHOICES, default='mensal',
        verbose_name='Frequência de Relacionamento',
    )
    observacoes = models.TextField(blank=True, verbose_name='Observações')

    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='coordenadores_cadastrados',
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coordenadores_atualizados',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Coordenador Regional'
        verbose_name_plural = 'Coordenadores Regionais'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} — {self.regiao.sigla}'


class CaboEleitoral(SoftDeleteMixin, models.Model):
    PRIORIDADE_CHOICES = [
        ('alta', 'Alta'),
        ('media', 'Média'),
        ('baixa', 'Baixa'),
    ]

    FREQUENCIA_CHOICES = [
        ('semanal', 'Semanal'),
        ('quinzenal', 'Quinzenal'),
        ('mensal', 'Mensal'),
        ('eventual', 'Eventual'),
    ]

    nome = models.CharField(max_length=200)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    cidade = models.ForeignKey(Cidade, on_delete=models.PROTECT, related_name='cabos_eleitorais')
    coordenador = models.ForeignKey(
        CoordenadorRegional,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cabos',
    )
    instagram = models.CharField(max_length=100, blank=True)
    prioridade = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES, default='media', verbose_name='Prioridade Comunicação')
    frequencia_relacionamento = models.CharField(
        max_length=15, choices=FREQUENCIA_CHOICES, default='mensal',
        verbose_name='Frequência de Relacionamento',
    )
    observacoes = models.TextField(blank=True, verbose_name='Observações')

    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='cabos_cadastrados',
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cabos_atualizados',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cabo Eleitoral'
        verbose_name_plural = 'Cabos Eleitorais'
        ordering = ['nome']

    def save(self, *args, **kwargs):
        if not self.coordenador_id:
            coord = CoordenadorRegional.objects.filter(regiao=self.cidade.regiao).first()
            if coord:
                self.coordenador = coord
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.nome} — {self.cidade}'


class Apoiador(SoftDeleteMixin, models.Model):
    TIPO_CHOICES = [
        ('politico', 'Apoiador Político'),
        ('empresarial', 'Apoiador Empresarial'),
        ('comunitario', 'Apoiador Comunitário'),
        ('associacao', 'Líder de Associação'),
        ('estrategico', 'Eleitor Estratégico'),
        ('imprensa', 'Imprensa'),
        ('pwa', 'Apoiador PWA'),
    ]

    PRIORIDADE_CHOICES = [
        ('alta', 'Alta'),
        ('media', 'Média'),
        ('baixa', 'Baixa'),
    ]


    INFLUENCIA_CHOICES = [
        ('alto', 'Alto'),
        ('medio', 'Médio'),
        ('baixo', 'Baixo'),
    ]

    FREQUENCIA_CHOICES = [
        ('semanal', 'Semanal'),
        ('quinzenal', 'Quinzenal'),
        ('mensal', 'Mensal'),
        ('eventual', 'Eventual'),
    ]

    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('inativo', 'Inativo'),
        ('pendente', 'Pendente'),
    ]

    CARGO_CHOICES = [
        ('prefeito', 'Prefeito'),
        ('vice_prefeito', 'Vice-Prefeito'),
        ('vereador', 'Vereador'),
        ('presidente_diretorio', 'Presidente Diretório'),
        ('ex_politico', 'Ex-Político'),
        ('outro', 'Outro'),
    ]

    nome = models.CharField(max_length=200)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    cidade = models.ForeignKey(Cidade, on_delete=models.PROTECT, related_name='apoiadores')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    cargo = models.CharField(
        max_length=25, choices=CARGO_CHOICES, blank=True,
        verbose_name='Cargo Político',
    )
    votos_referencia = models.IntegerField(
        default=0, verbose_name='Votos de referência',
        help_text='Votos que este político obteve na última eleição (base da máquina de voto).',
    )
    meta_votos_transferir = models.IntegerField(
        default=0, verbose_name='Meta de votos a transferir',
        help_text='Quantos votos deste político a campanha quer transferir para o LS.',
    )
    origem_contato = models.CharField(max_length=200, blank=True, verbose_name='Origem do Contato')
    instagram = models.CharField(max_length=100, blank=True)
    prioridade = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES, default='media', verbose_name='Prioridade Comunicação')
    grau_influencia = models.CharField(
        max_length=10, choices=INFLUENCIA_CHOICES, default='medio',
        verbose_name='Grau de Influência',
    )
    frequencia_relacionamento = models.CharField(
        max_length=15, choices=FREQUENCIA_CHOICES, default='mensal',
        verbose_name='Frequência de Relacionamento',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ativo')
    observacoes = models.TextField(blank=True, verbose_name='Observações')

    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='apoiadores_cadastrados',
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='apoiadores_atualizados',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Apoiador'
        verbose_name_plural = 'Apoiadores'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Voluntario(models.Model):
    DISPONIBILIDADE_CHOICES = [
        ('panfletagem', 'Panfletagem'),
        ('bandeira', 'Bandeira'),
        ('carreata', 'Carreata'),
        ('comicio', 'Comício'),
        ('evento', 'Evento'),
        ('boca_urna', 'Boca de Urna'),
    ]

    nome = models.CharField(max_length=200)
    telefone = models.CharField(max_length=20)
    regiao = models.ForeignKey(
        Regiao, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='voluntarios',
    )
    cidade = models.ForeignKey(
        Cidade, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='voluntarios',
    )
    disponibilidades = models.JSONField(
        default=list, blank=True,
        verbose_name='Disponibilidades',
    )
    endereco = models.CharField(max_length=300, blank=True, verbose_name='Endereço')
    observacoes = models.TextField(blank=True, verbose_name='Observações')
    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, related_name='voluntarios_cadastrados',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Voluntário'
        verbose_name_plural = 'Voluntários'
        ordering = ['-created_at']

    def __str__(self):
        return self.nome

    def get_disponibilidades_display(self):
        mapa = dict(self.DISPONIBILIDADE_CHOICES)
        return [mapa.get(d, d) for d in self.disponibilidades]


class Egresso(SoftDeleteMixin, models.Model):
    nome = models.CharField(max_length=200)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    instagram = models.CharField(max_length=100, blank=True, verbose_name='Redes Sociais')
    cidade_nome = models.CharField(max_length=150, blank=True, verbose_name='Cidade (texto)')
    estado = models.CharField(max_length=2, blank=True, verbose_name='UF')
    cidade = models.ForeignKey(
        Cidade, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='egressos',
        verbose_name='Cidade (SC)',
    )
    curso = models.CharField(max_length=150, blank=True)
    instituicao = models.CharField(max_length=150, blank=True, verbose_name='Instituição')
    situacao_curso = models.CharField(max_length=50, blank=True, verbose_name='Situação do Curso')
    observacoes = models.TextField(blank=True, verbose_name='Observações')

    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='egressos_cadastrados',
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='egressos_atualizados',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Egresso'
        verbose_name_plural = 'Egressos'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Lassberg(SoftDeleteMixin, models.Model):
    nome = models.CharField(max_length=200)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    cidade_nome = models.CharField(max_length=150, blank=True, verbose_name='Cidade (texto)')
    estado = models.CharField(max_length=30, blank=True, verbose_name='Estado')
    cidade = models.ForeignKey(
        Cidade, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='lassbergs',
        verbose_name='Cidade (SC)',
    )
    observacoes = models.TextField(blank=True, verbose_name='Observações')

    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lassbergs_cadastrados',
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lassbergs_atualizados',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Lassberg'
        verbose_name_plural = 'Lassberg'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class InteracaoLog(models.Model):
    TIPO_CHOICES = [
        ('ligacao', 'Ligação'),
        ('visita', 'Visita'),
        ('reuniao', 'Reunião'),
        ('whatsapp', 'WhatsApp'),
        ('email', 'E-mail'),
        ('evento', 'Evento'),
        ('outro', 'Outro'),
    ]

    coordenador = models.ForeignKey(
        CoordenadorRegional, on_delete=models.CASCADE,
        null=True, blank=True, related_name='interacoes',
    )
    cabo = models.ForeignKey(
        CaboEleitoral, on_delete=models.CASCADE,
        null=True, blank=True, related_name='interacoes',
    )
    apoiador = models.ForeignKey(
        Apoiador, on_delete=models.CASCADE,
        null=True, blank=True, related_name='interacoes',
    )
    egresso = models.ForeignKey(
        Egresso, on_delete=models.CASCADE,
        null=True, blank=True, related_name='interacoes',
    )
    lassberg = models.ForeignKey(
        Lassberg, on_delete=models.CASCADE,
        null=True, blank=True, related_name='interacoes',
    )

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    descricao = models.TextField(verbose_name='Descrição')
    data = models.DateTimeField(default=timezone.now, verbose_name='Data da Interação')
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, related_name='interacoes_registradas',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Interação'
        verbose_name_plural = 'Interações'
        ordering = ['-data']

    def __str__(self):
        target = self.entidade
        return f'{self.get_tipo_display()} — {target} ({self.data:%d/%m/%Y})'

    @property
    def entidade(self):
        return self.coordenador or self.cabo or self.apoiador or self.egresso or self.lassberg

    @property
    def entidade_tipo(self):
        if self.coordenador_id:
            return 'coordenador'
        if self.cabo_id:
            return 'cabo'
        if self.apoiador_id:
            return 'apoiador'
        if self.egresso_id:
            return 'egresso'
        if self.lassberg_id:
            return 'lassberg'
        return ''
