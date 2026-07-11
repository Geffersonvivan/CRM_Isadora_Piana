"""Integridade dos indicadores do mapa (CLAUDE.md §5 e §13.4) e concorrência
por cargo em disputa (Fase 2 passo 3 — cargo cruzado):
- rótulo bate com valor/unidade (pib_per_capita em R$ por habitante);
- sem dado → sem dado, excluído do cálculo (nunca preenchido por proxy);
- sanidade dos dados base (população > 0) é erro crítico;
- a auditoria de correlação acusa indicador sintético (derivado do PIB)."""
import json
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from liderancas.models import Cidade, Regiao
from mapa.models import Eleicao, IndicadorMunicipal, ResultadoCandidato
from usuarios.models import Usuario


def criar_cidade(nome, populacao=1000, eleitores=800):
    regiao, _ = Regiao.objects.get_or_create(sigla='TST', defaults={'nome': 'Região Teste'})
    return Cidade.objects.create(nome=nome, regiao=regiao, slug=nome.lower().replace(' ', '-'),
                                 codigo_ibge=f'42{abs(hash(nome)) % 10**5:05d}',
                                 populacao=populacao, eleitores=eleitores)


class PibPerCapitaTests(TestCase):
    """§5.3: o que está rotulado 'PIB per capita' é PIB ÷ população, na unidade
    exibida (R$ por habitante) — `pib` é armazenado em R$ mil."""

    def test_unidade_reais_por_habitante(self):
        cidade = criar_cidade('Unidade', populacao=10_000)
        ind = IndicadorMunicipal.objects.create(
            cidade=cidade, ano_referencia=2022, populacao=10_000, pib=50_000)  # R$ 50 milhões
        self.assertEqual(ind.pib_per_capita, 5_000.0)  # R$ 5.000/hab, não 5 nem 5.000.000

    def test_sem_populacao_e_sem_dado_nao_zero(self):
        # §5.2: sem dado → None (excluído do cálculo), nunca um número inventado
        cidade = criar_cidade('Sem Pop')
        ind = IndicadorMunicipal.objects.create(
            cidade=cidade, ano_referencia=2022, populacao=0, pib=50_000)
        self.assertIsNone(ind.pib_per_capita)


class AuditoriaIndicadoresTests(TestCase):
    """O comando auditar_indicadores é o guarda-costas da Seção 5."""

    def _rodar(self, *args):
        out = StringIO()
        codigo = 0
        try:
            call_command('auditar_indicadores', '--json', *args, stdout=out)
        except SystemExit as e:
            codigo = e.code or 0
        return json.loads(out.getvalue()[:out.getvalue().rfind('}') + 1]), codigo

    def test_populacao_invalida_e_critica(self):
        # §5.6: população <= 0 distorce todo per capita — é erro de dado, crítico
        cidade = criar_cidade('Pop Zero', populacao=0)
        IndicadorMunicipal.objects.create(cidade=cidade, ano_referencia=2022,
                                          populacao=0, pib=100)
        report, codigo = self._rodar()
        self.assertEqual(codigo, 1)
        self.assertTrue(any('populacao' in c for c in report['criticos']))

    def test_indicador_sintetico_e_acusado(self):
        # §5.5: renda derivada do PIB per capita (r ≈ 1) não é sinal independente
        for i in range(10):
            pop = 1_000 + i * 500
            pib = 2_000 + (i * 37) % 900 * 10          # variação não monotônica
            IndicadorMunicipal.objects.create(
                cidade=criar_cidade(f'Sint {i}', populacao=pop),
                ano_referencia=2022, populacao=pop, pib=pib,
                renda_per_capita=round(float(pib) / pop * 0.5, 2),  # proxy disfarçado
                familias_bolsa_familia=(i * 7) % 13 + 1,
                meis_ativos=(i * 5) % 11 + 1,
                populacao_urbana=pop // 2, populacao_rural=pop - pop // 2,
                idosos_60_mais=(i * 3) % 9 + 1, jovens_18_29=(i * 11) % 17 + 1,
                taxa_alfabetizacao=5 + (i % 7),
            )
        report, _ = self._rodar()
        self.assertGreaterEqual(abs(report['metricas']['correlacao_pib']['renda_per_capita']), 0.90)
        self.assertTrue(any('renda_per_capita' in a and 'SINTÉTICO' in a
                            for a in report['avisos']))

    def test_dados_sadios_passam_sem_critico(self):
        cidade = criar_cidade('Sadia', populacao=20_000, eleitores=15_000)
        IndicadorMunicipal.objects.create(
            cidade=cidade, ano_referencia=2022, populacao=20_000, pib=80_000,
            renda_per_capita=1_500, familias_bolsa_familia=900, meis_ativos=700,
            populacao_urbana=15_000, populacao_rural=5_000,
            idosos_60_mais=3_000, jovens_18_29=4_000, taxa_alfabetizacao=9.1)
        report, codigo = self._rodar()
        self.assertEqual(codigo, 0)
        self.assertEqual(report['criticos'], [])


class ConcorrenciaCargoCruzadoTests(TestCase):
    """Fase 2 passo 3: CandidatosAPI segue TSE_CARGO_2026 da config."""

    def test_cargo_em_disputa_vem_da_config(self):
        """Fase 2 passo 3: o ranking de ameaça (overlap ponderado) segue
        TSE_CARGO_2026 — inclusive quando a marca disputa outro cargo."""
        a = criar_cidade('Alfa')
        b = criar_cidade('Beta')
        el_est = Eleicao.objects.create(ano=2022, tipo='deputado_estadual', turno=1)
        el_fed = Eleicao.objects.create(ano=2022, tipo='deputado_federal', turno=1)

        # Base da candidata (cargo-base estadual): 100 em Alfa, 50 em Beta
        for cidade, votos in ((a, 100), (b, 50)):
            ResultadoCandidato.objects.create(
                eleicao=el_est, cidade=cidade, candidato_nome='NOSSA CANDIDATA',
                partido='NOVO', votos=votos, is_candidato=True)
        # Rival no cargo em disputa (estadual): 80 votos em Alfa
        ResultadoCandidato.objects.create(
            eleicao=el_est, cidade=a, candidato_nome='RIVAL ESTADUAL',
            partido='PL', votos=80)
        # Candidato de outro cargo (federal): 70 em Alfa
        ResultadoCandidato.objects.create(
            eleicao=el_fed, cidade=a, candidato_nome='NOME FEDERAL',
            partido='PP', votos=70)

        user = Usuario.objects.create_user(username='mapa', password='x')
        self.client.force_login(user)
        url = reverse('mapa:api_competicao')

        with override_settings(ALLOWED_HOSTS=['testserver']):
            cache.clear()   # o endpoint tem cache_page de 24h
            por_nome = {c['nome']: c for c in self.client.get(url).json()['candidatos']}

        rival = por_nome['RIVAL ESTADUAL']
        # ponderado: 100·min(100,80) / (100²+50²) = 8000/12500 = 64%
        self.assertEqual(rival['overlap_pct'], 64.0)
        self.assertEqual(rival['threat_rank'], 1)
        self.assertEqual(rival['shared_cities'], 1)
        # o federal recebe overlap simples (contexto), não o ponderado
        fed = por_nome['NOME FEDERAL']
        self.assertEqual(fed['overlap_votes'], 70)   # min(100, 70) em Alfa

    def test_cargo_cruzado_outra_marca(self):
        """Marca com base E disputa federais: o ponderado migra para federal."""
        from core.tests import MARCA_TESTE
        a = criar_cidade('Gama')
        el_fed = Eleicao.objects.create(ano=2022, tipo='deputado_federal', turno=1)
        ResultadoCandidato.objects.create(
            eleicao=el_fed, cidade=a, candidato_nome='JOAO TESTE',
            partido='NOVO', votos=100, is_candidato=True)
        ResultadoCandidato.objects.create(
            eleicao=el_fed, cidade=a, candidato_nome='RIVAL FEDERAL',
            partido='PL', votos=90)

        user = Usuario.objects.create_user(username='mapa2', password='x')
        self.client.force_login(user)
        url = reverse('mapa:api_competicao')

        with override_settings(ALLOWED_HOSTS=['testserver'], CAMPANHA=MARCA_TESTE):
            cache.clear()
            por_nome = {c['nome']: c for c in self.client.get(url).json()['candidatos']}

        rival = por_nome['RIVAL FEDERAL']
        # ponderado: 100·min(100,90) / 100² = 90%
        self.assertEqual(rival['overlap_pct'], 90.0)
        self.assertEqual(rival['threat_rank'], 1)
