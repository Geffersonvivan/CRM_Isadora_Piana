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
    is_sorgatto = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Resultado por Candidato'
        verbose_name_plural = 'Resultados por Candidato'
        indexes = [
            models.Index(fields=['eleicao', 'cidade']),
            models.Index(fields=['is_sorgatto']),
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
    is_sorgatto = models.BooleanField(default=False)

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
    ano_referencia = models.IntegerField(verbose_name='Ano de referência')

    class Meta:
        unique_together = ('cidade', 'ano_referencia')
        verbose_name = 'Indicador Municipal'
        verbose_name_plural = 'Indicadores Municipais'

    def __str__(self):
        return f'{self.cidade.nome} ({self.ano_referencia})'
