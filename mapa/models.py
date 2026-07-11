from django.db import models
from liderancas.models import Cidade


class Eleicao(models.Model):
    ANO_CHOICES = [(2018, '2018'), (2022, '2022'), (2026, '2026')]
    TIPO_CHOICES = [
        ('deputado_federal', 'Deputado Federal'),
        ('deputado_estadual', 'Deputado Estadual'),
        ('senador', 'Senador'),
        ('governador', 'Governador'),
        ('presidente', 'Presidente'),
        ('prefeito', 'Prefeito'),
        ('vereador', 'Vereador'),
    ]

    ano = models.IntegerField(choices=ANO_CHOICES)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    turno = models.IntegerField(default=1)

    class Meta:
        unique_together = ('ano', 'tipo', 'turno')
        verbose_name = 'Eleição'
        verbose_name_plural = 'Eleições'

    def __str__(self):
        return f'{self.get_tipo_display()} {self.ano} ({self.turno}T)'


class ResultadoCandidato(models.Model):
    eleicao = models.ForeignKey(Eleicao, on_delete=models.CASCADE, related_name='resultados')
    candidato_nome = models.CharField(max_length=255)
    candidato_numero = models.CharField(max_length=10)
    partido = models.CharField(max_length=150)
    cidade = models.ForeignKey(Cidade, on_delete=models.CASCADE, related_name='resultados_eleicao')
    votos = models.IntegerField(default=0)
    percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    eleito = models.BooleanField(default=False)
    is_candidato = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Resultado por Candidato'
        verbose_name_plural = 'Resultados por Candidato'
        indexes = [
            models.Index(fields=['eleicao', 'cidade']),
            models.Index(fields=['is_candidato']),
        ]

    def __str__(self):
        return f'{self.candidato_nome} ({self.partido}) - {self.cidade.nome}: {self.votos}'


class ResultadoZona(models.Model):
    eleicao = models.ForeignKey(Eleicao, on_delete=models.CASCADE, related_name='resultados_zona')
    candidato_nome = models.CharField(max_length=255)
    candidato_numero = models.CharField(max_length=10)
    partido = models.CharField(max_length=150)
    cidade = models.ForeignKey(Cidade, on_delete=models.CASCADE, related_name='resultados_zona')
    zona = models.CharField(max_length=10)
    votos = models.IntegerField(default=0)
    percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_candidato = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Resultado por Zona'
        verbose_name_plural = 'Resultados por Zona'
        indexes = [
            models.Index(fields=['eleicao', 'cidade', 'zona']),
        ]

    def __str__(self):
        return f'{self.candidato_nome} - Zona {self.zona} ({self.cidade.nome}): {self.votos}'


class IndicadorMunicipal(models.Model):
    cidade = models.ForeignKey(Cidade, on_delete=models.CASCADE, related_name='indicadores')
    pib = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name='PIB (R$ mil)')
    renda_per_capita = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Renda per capita')
    familias_bolsa_familia = models.IntegerField(default=0, verbose_name='Famílias no Bolsa Família')
    populacao = models.IntegerField(default=0)
    meis_ativos = models.IntegerField(default=0, verbose_name='MEIs ativos')
    populacao_urbana = models.IntegerField(default=0, verbose_name='Pop. urbana')
    populacao_rural = models.IntegerField(default=0, verbose_name='Pop. rural')
    idosos_60_mais = models.IntegerField(default=0, verbose_name='Idosos 60+')
    jovens_18_29 = models.IntegerField(default=0, verbose_name='Jovens 18-29')
    # Taxa de alfabetização (%) das pessoas de 15+ anos (IBGE Censo 2022). O nome
    # antigo era "anos_estudo_medio" (§5.3: rótulo ≠ conteúdo — corrigido).
    taxa_alfabetizacao = models.DecimalField(max_digits=4, decimal_places=1, default=0, verbose_name='Taxa de alfabetização (%)')
    ano_referencia = models.IntegerField(verbose_name='Ano de referência')
    # §5.4: proveniência do dado (ex.: 'IBGE Censo 2022', 'Portal da Transparência').
    fonte = models.CharField(max_length=200, blank=True, verbose_name='Fonte')

    class Meta:
        unique_together = ('cidade', 'ano_referencia')
        verbose_name = 'Indicador Municipal'
        verbose_name_plural = 'Indicadores Municipais'

    def __str__(self):
        return f'{self.cidade.nome} ({self.ano_referencia})'

    @property
    def pib_per_capita(self):
        """PIB per capita em R$ por habitante. `pib` é armazenado em R$ mil
        (verbose_name), logo ×1000 / população. Fonte única para popup, CSV e
        APIs — evita a divergência de 1000× já corrigida no balão (CLAUDE.md §5.3).
        Sem população (>0) → None (sem dado; não entra em cálculo/exibição)."""
        if not self.populacao or self.populacao <= 0:
            return None
        return float(self.pib) * 1000 / self.populacao


class AliadoChapa(models.Model):
    """Aliado de chapa (cargo diferente do LS) cujos redutos de 2022 servem de
    carona/palanque. Ex.: Jorginho (governador), Carol (senadora), Daniela (federal)."""
    nome = models.CharField(max_length=120)
    termos_busca = models.CharField(
        max_length=120,
        help_text='Termos que devem aparecer no nome do candidato em 2022 (ex.: "CAROL TONI").',
    )
    candidato_numero = models.CharField(
        max_length=10, blank=True,
        help_text='Número na urna em 2022. Quando preenchido, o cruzamento de votos é exato.',
    )
    cargo_2022 = models.CharField(
        max_length=30, blank=True, verbose_name='Cargo em 2022',
        help_text='governador, senador, deputado_federal ou deputado_estadual.',
    )
    partido = models.CharField(max_length=30, blank=True)
    cargo_2026 = models.CharField(max_length=60, blank=True, verbose_name='Cargo em 2026')
    cor = models.CharField(max_length=7, default='#2563eb')
    ativo = models.BooleanField(default=True, help_text='Marcado no mapa de Transferência.')
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Aliado de Chapa'
        verbose_name_plural = 'Aliados de Chapa'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return f'{self.nome} ({self.cargo_2026})' if self.cargo_2026 else self.nome
