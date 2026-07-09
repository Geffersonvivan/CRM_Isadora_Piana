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


def q_apoiadores_aprovados(prefix=''):
    """Q canônico do apoiador que conta como oficial (CLAUDE.md §3.1): papel
    apoiador, ativo e aprovado. `prefix` permite usar em agregações por relação
    reversa, ex.: q_apoiadores_aprovados('liderancas') ou 'cidades__liderancas'.
    Fonte única — evita o predicado de moderação copiado em ~25 querysets."""
    p = f'{prefix}__' if prefix else ''
    return models.Q(**{
        f'{p}papel': 'apoiador', f'{p}status': 'ativo', f'{p}aprovacao': 'aprovado',
    })


class LiderancaQuerySet(SoftDeleteQuerySet):
    def aprovados(self):
        """Só o que é base oficial (CLAUDE.md §3.1)."""
        return self.filter(aprovacao='aprovado')

    def apoiadores_aprovados(self):
        """Apoiadores que contam para placares/mapa/exports oficiais."""
        return self.filter(q_apoiadores_aprovados())


class LiderancaManager(SoftDeleteManager):
    def get_queryset(self):
        return LiderancaQuerySet(self.model, using=self._db).active()

    def aprovados(self):
        return self.get_queryset().aprovados()

    def apoiadores_aprovados(self):
        return self.get_queryset().apoiadores_aprovados()


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
    num_vereadores_partido = models.IntegerField(default=0)
    presidente_diretorio = models.CharField(max_length=200, blank=True, verbose_name='Presidente Diretório NOVO')
    votos_referencia_2022 = models.IntegerField(default=0)
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
                req = urllib.request.Request(url, headers={'User-Agent': 'CRM-Base-Eleitoral'})
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


class Lideranca(SoftDeleteMixin, models.Model):
    """Cadastro unificado de pessoas da rede política.
    Substitui CoordenadorRegional, CaboEleitoral e Apoiador — o campo `papel`
    discrimina o tipo. Campos específicos de apoiador ficam vazios para os demais."""

    objects = LiderancaManager()
    all_objects = LiderancaQuerySet.as_manager()

    PAPEL_CHOICES = [
        ('coordenador', 'Coordenador Regional'),
        ('cabo', 'Cabo Eleitoral'),
        ('apoiador', 'Apoiador'),
    ]
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
    # Específicos de apoiador
    TIPO_CHOICES = [
        ('politico', 'Apoiador Político'),
        ('empresarial', 'Apoiador Empresarial'),
        ('comunitario', 'Apoiador Comunitário'),
        ('associacao', 'Líder de Associação'),
        ('estrategico', 'Eleitor Estratégico'),
        ('imprensa', 'Imprensa'),
        ('pwa', 'Apoiador PWA'),
    ]
    INFLUENCIA_CHOICES = [
        ('alto', 'Alto'),
        ('medio', 'Médio'),
        ('baixo', 'Baixo'),
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
    # Campos vindos da PLANILHA CENTRAL ISA (base de eleitores/apoiadores)
    INTENCAO_VOTO_CHOICES = [
        ('sim', 'Sim'),
        ('talvez', 'Talvez'),
        ('nao', 'Não'),
        ('nao_contactado', 'Não contactado'),
    ]
    # Vocabulário de nível/engajamento (usado pela Isadora). "Contato" substituiu
    # o antigo "Lead" (migration renomeia os registros existentes).
    NIVEL_CHOICES = [
        ('contato', 'Contato'),
        ('eleitor', 'Eleitor'),
        ('multiplicador', 'Multiplicador'),
        ('voluntario', 'Voluntário'),
    ]
    CANAL_CHOICES = [
        ('facebook', 'Facebook'),
        ('whatsapp', 'WhatsApp'),
        ('instagram', 'Instagram'),
        ('tiktok', 'Tiktok'),
        ('twitter', 'Twitter'),
    ]

    papel = models.CharField(max_length=12, choices=PAPEL_CHOICES, db_index=True)

    # Comuns a todos
    nome = models.CharField(max_length=200)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    instagram = models.CharField(max_length=100, blank=True)
    # Opcional: contatos de fora de SC (ou sem cidade na planilha) entram sem
    # cidade; a cidade/UF crua vai para observações na importação.
    cidade = models.ForeignKey(Cidade, on_delete=models.PROTECT, related_name='liderancas',
                               null=True, blank=True)
    regiao = models.ForeignKey(
        Regiao, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='liderancas',
        verbose_name='Região de atuação',
        help_text='Usada pelo coordenador como área de atuação; nos demais, deriva da cidade.',
    )
    coordenador_responsavel = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='liderados', limit_choices_to={'papel': 'coordenador'},
        verbose_name='Coordenador Responsável',
    )
    prioridade = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES, default='media', verbose_name='Prioridade Comunicação')
    frequencia_relacionamento = models.CharField(
        max_length=15, choices=FREQUENCIA_CHOICES, default='mensal',
        verbose_name='Frequência de Relacionamento',
    )
    observacoes = models.TextField(blank=True, verbose_name='Observações')

    # Específicos de apoiador (ficam vazios/zerados para coordenador e cabo)
    # `tipo` = categoria PRINCIPAL (1º item de `tipos`), mantida em sincronia no
    # save() para os consumidores single-value (lista, filtro, export, detector).
    # `tipos` guarda TODAS as categorias marcadas (o apoiador pode ter várias).
    tipo = models.CharField(
        max_length=20, choices=TIPO_CHOICES, blank=True,
        verbose_name='Categoria do Apoiador',
    )
    tipos = models.JSONField(
        default=list, blank=True,
        verbose_name='Categorias do Apoiador',
        help_text='Uma ou mais categorias; a primeira é a principal.',
    )
    cargo = models.CharField(max_length=25, choices=CARGO_CHOICES, blank=True, verbose_name='Cargo Político')
    votos_referencia = models.IntegerField(default=0, verbose_name='Votos de referência')
    meta_votos_transferir = models.IntegerField(default=0, verbose_name='Meta de votos a transferir')
    origem_contato = models.CharField(max_length=200, blank=True, verbose_name='Origem do Contato')
    grau_influencia = models.CharField(
        max_length=10, choices=INFLUENCIA_CHOICES, blank=True,
        verbose_name='Grau de Influência',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, blank=True)

    # ── Campos da PLANILHA CENTRAL ISA (atendimento & relacionamento) ──
    # Mesclados do arquivo "PLANILHA CENTRAL ISA DEPUTADA.xlsx" (aba ELEITORES).
    # Todos opcionais — não afetam cadastros existentes nem o funil de moderação.
    atendente = models.CharField(
        max_length=100, blank=True, verbose_name='Atendente',
        help_text='Quem fez/conduz o atendimento deste contato (texto livre/legado/import).',
    )                                                       # planilha: ATENDENTE
    # Atendente estruturado: puxa os usuários cadastrados do sistema. O campo de
    # texto acima fica para import/legado; a lista/edição inline usam este vínculo.
    atendente_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='liderancas_atendidas',
        verbose_name='Atendente (usuário)',
    )
    intencao_voto = models.CharField(
        max_length=15, choices=INTENCAO_VOTO_CHOICES, blank=True,
        verbose_name='Intenção de voto',
    )                                                       # planilha: VOTO
    # `nivel` = nível PRINCIPAL (1º de `niveis`), mantido em sincronia no save()
    # para os consumidores single-value (lista, filtro, dashboard). `niveis`
    # guarda TODOS os níveis marcados (o cadastro do PWA pode marcar vários).
    nivel = models.CharField(
        max_length=15, choices=NIVEL_CHOICES, blank=True, verbose_name='Nível',
    )                                                       # planilha: NÍVEL
    niveis = models.JSONField(
        default=list, blank=True, verbose_name='Níveis',
        help_text='Um ou mais níveis; o primeiro é o principal.',
    )
    uf = models.CharField(
        max_length=2, blank=True, default='SC', verbose_name='UF',
    )                                                       # planilha: UF
    contato_feito = models.BooleanField(
        default=False, verbose_name='Contato feito?',
    )                                                       # planilha: Contato Feito?
    data_contato = models.DateField(
        null=True, blank=True, verbose_name='Data do contato',
    )                                                       # planilha: DATA CONTATO
    canal_atendimento = models.CharField(
        max_length=12, choices=CANAL_CHOICES, blank=True,
        verbose_name='Canal do último atendimento',
    )                                                       # planilha: CANAL DO ÚLTIMO ATENDIMENTO
    vaquinha_enviada = models.BooleanField(
        default=False, verbose_name='Link da vaquinha enviado?',
    )                                                       # planilha: Já mandou link da VAQUINHA?
    doou = models.BooleanField(
        default=False, verbose_name='Doou?',
    )                                                       # planilha: DOOU?
    filiado_partido = models.CharField(
        max_length=100, blank=True, verbose_name='Filiado a algum partido?',
    )                                                       # planilha: FILIADO A ALGUM PARTIDO?
    quem_e_eleitor = models.CharField(
        max_length=255, blank=True, verbose_name='Quem é o eleitor?',
    )                                                       # planilha: QUEM É O ELEITOR?
    facebook = models.CharField(
        max_length=200, blank=True, verbose_name='Facebook',
    )                                                       # planilha: FACEBOOK
    endereco = models.CharField(
        max_length=300, blank=True, verbose_name='Endereço (entrega de material)',
    )                                                       # planilha: ENDEREÇO
    material_entregue = models.BooleanField(
        default=False, verbose_name='Material entregue?',
    )                                                       # planilha: MATERIAL ENTREGUE?
    idade = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Idade',
    )                                                       # planilha: IDADE
    segmentos = models.CharField(
        max_length=255, blank=True, verbose_name='Segmentos/Interesses',
    )                                                       # planilha: SEGMENTOS/INTERESSES
    # Coluna "HISTÓRICO DO ATENDIMENTO" da planilha → registrada via InteracaoLog.

    # Idempotência do cadastro offline via PWA (UUID gerado no aparelho)
    pwa_client_id = models.CharField(
        max_length=64, null=True, blank=True, unique=True, db_index=True,
        verbose_name='ID do cadastro PWA',
    )

    # Moderação: leads do PWA entram como 'pendente' e precisam de aprovação
    # para contar como base oficial (export/contagens). 'rejeitado' fica oculto.
    APROVACAO_CHOICES = [
        ('pendente', 'Pendente'),
        ('aprovado', 'Aprovado'),
        ('rejeitado', 'Rejeitado'),
    ]
    ORIGEM_CHOICES = [
        ('crm', 'CRM'),
        ('pwa', 'App PWA'),
        ('import', 'Importação'),
    ]
    aprovacao = models.CharField(
        max_length=10, choices=APROVACAO_CHOICES, default='aprovado', db_index=True,
        verbose_name='Aprovação',
    )
    origem = models.CharField(max_length=10, choices=ORIGEM_CHOICES, default='crm')
    aprovado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='liderancas_aprovadas',
    )
    aprovado_em = models.DateTimeField(null=True, blank=True)
    motivo_rejeicao = models.TextField(blank=True, verbose_name='Motivo da rejeição')

    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='liderancas_cadastradas',
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='liderancas_atualizadas',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Liderança'
        verbose_name_plural = 'Lideranças'
        ordering = ['nome']
        indexes = [
            models.Index(fields=['papel', 'is_active']),
        ]

    def save(self, *args, **kwargs):
        # Cabo sem coordenador → tenta um coordenador da mesma região (paridade com o modelo antigo)
        if self.papel == 'cabo' and not self.coordenador_responsavel_id and self.cidade_id:
            coord = Lideranca.objects.filter(
                papel='coordenador', regiao=self.cidade.regiao,
            ).first()
            if coord:
                self.coordenador_responsavel = coord
        # Categoria: `tipo` (principal) e `tipos` (lista) andam juntos.
        # Quem escreve a lista manda; quem escreve só o valor único preenche a lista.
        if self.tipos:
            self.tipos = list(dict.fromkeys(self.tipos))  # sem duplicatas, ordem preservada
            self.tipo = self.tipos[0]
        elif self.tipo:
            self.tipos = [self.tipo]
        # Nível: `niveis` (lista) e `nivel` (principal) andam juntos — igual tipos/tipo.
        if self.niveis:
            self.niveis = list(dict.fromkeys(self.niveis))
            self.nivel = self.niveis[0]
        elif self.nivel:
            self.niveis = [self.nivel]
        super().save(*args, **kwargs)

    def get_tipos_display(self):
        """Rótulos de todas as categorias marcadas (fallback ao tipo único)."""
        rotulos = dict(self.TIPO_CHOICES)
        lista = self.tipos or ([self.tipo] if self.tipo else [])
        return ' · '.join(rotulos.get(t, t) for t in lista)

    def __str__(self):
        return f'{self.nome} ({self.get_papel_display()})'


class Voluntario(SoftDeleteMixin, models.Model):
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

    # Idempotência do cadastro offline via PWA
    pwa_client_id = models.CharField(
        max_length=64, null=True, blank=True, unique=True, db_index=True,
        verbose_name='ID do cadastro PWA',
    )
    # Moderação (igual aos leads): cadastros do app entram como 'pendente'
    aprovacao = models.CharField(
        max_length=10, choices=Lideranca.APROVACAO_CHOICES, default='aprovado', db_index=True,
        verbose_name='Aprovação',
    )
    origem = models.CharField(max_length=10, choices=Lideranca.ORIGEM_CHOICES, default='crm')
    aprovado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='voluntarios_aprovados',
    )
    aprovado_em = models.DateTimeField(null=True, blank=True)
    motivo_rejeicao = models.TextField(blank=True, verbose_name='Motivo da rejeição')

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

    lideranca = models.ForeignKey(
        'Lideranca', on_delete=models.CASCADE,
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
        return self.lideranca

    @property
    def entidade_tipo(self):
        if self.lideranca_id:
            return self.lideranca.papel
        return ''
