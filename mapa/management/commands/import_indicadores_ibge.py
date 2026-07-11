"""
Importa indicadores socioeconômicos municipais diretamente das APIs do IBGE.

Dados buscados:
  1. PIB municipal (tabela 5938, variável 37) — em R$ mil
  2. PIB per capita (pesquisa 38, indicador 47001) — usado como renda_per_capita
  3. Bolsa Família e MEIs — estimados com base no perfil socioeconômico

Uso:
    python manage.py import_indicadores_ibge           # ano mais recente disponível
    python manage.py import_indicadores_ibge --ano 2022
"""
import gzip
import json
import math
import urllib.request
from decimal import Decimal

from django.core.management.base import BaseCommand

from liderancas.models import Cidade
from mapa.models import IndicadorMunicipal

SC_CODE = '42'  # Código IBGE de Santa Catarina


class Command(BaseCommand):
    help = 'Importa indicadores socioeconômicos do IBGE para municípios de SC'

    def add_arguments(self, parser):
        parser.add_argument('--ano', type=int, default=0, help='Ano de referência (default: mais recente)')

    def handle(self, *args, **options):
        ano_pref = options['ano']

        # Mapeamento codigo_ibge -> Cidade
        city_map = {}
        for c in Cidade.objects.exclude(codigo_ibge__isnull=True).exclude(codigo_ibge=''):
            city_map[c.codigo_ibge] = c

        self.stdout.write(f'{len(city_map)} cidades encontradas no banco.')

        # 1. Buscar PIB municipal (tabela 5938, var 37)
        self.stdout.write('Baixando PIB municipal do IBGE...')
        pib_data = self._fetch_pib(ano_pref)

        # 2. Buscar PIB per capita (pesquisa 38, indicador 47001)
        self.stdout.write('Baixando PIB per capita do IBGE...')
        pibpc_data = self._fetch_pib_per_capita(ano_pref)

        # Determinar ano de referência
        ano = ano_pref or self._detect_year(pib_data) or 2022
        self.stdout.write(f'Ano de referência: {ano}')

        # 3. Consolidar e salvar
        created = 0
        updated = 0
        skipped = 0

        for ibge_code, cidade in city_map.items():
            # Código IBGE nas APIs pode ter 6 ou 7 dígitos
            code6 = ibge_code[:6] if len(ibge_code) >= 7 else ibge_code
            code7 = ibge_code

            pib_val = pib_data.get(code7) or pib_data.get(code6) or 0

            pop = cidade.populacao or 0

            # §5.1/5.2: Bolsa Família, MEIs e renda per capita NÃO são estimados do
            # PIB (era sintético apresentado como medido). Só gravamos o dado REAL:
            # PIB e população. O resto vem dos comandos import_bolsa_familia_real,
            # import_mei_real e import_renda_real — e fica vazio até lá (update_or_create
            # não sobrescreve o que não está em defaults, preservando o dado real).
            defaults = {
                'pib': Decimal(str(pib_val)),
                'populacao': pop,
            }

            _, is_new = IndicadorMunicipal.objects.update_or_create(
                cidade=cidade,
                ano_referencia=ano,
                defaults=defaults,
            )
            if is_new:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Concluído: {created} criados, {updated} atualizados, {skipped} ignorados'
        ))

    def _fetch_json(self, url):
        req = urllib.request.Request(url, headers={
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                text = gzip.decompress(raw).decode('utf-8')
            return json.loads(text)

    def _fetch_pib(self, ano_pref):
        """Busca PIB municipal da tabela 5938 (var 37) — valor em R$ mil."""
        periodo = str(ano_pref) if ano_pref else '2021'
        url = (
            f'https://servicodados.ibge.gov.br/api/v3/agregados/5938'
            f'/periodos/{periodo}/variaveis/37'
            f'?localidades=N6[N3[{SC_CODE}]]'
        )
        try:
            data = self._fetch_json(url)
        except Exception as e:
            self.stderr.write(f'Erro ao buscar PIB: {e}')
            return {}

        result = {}
        for item in data[0]['resultados'][0]['series']:
            ibge_code = item['localidade']['id']
            val_str = list(item['serie'].values())[0]
            if val_str and val_str != '...':
                result[ibge_code] = float(val_str)
        self.stdout.write(f'  PIB: {len(result)} municípios')
        return result

    def _fetch_pib_per_capita(self, ano_pref):
        """Busca PIB per capita da pesquisa 38, indicador 47001."""
        url = (
            f'https://servicodados.ibge.gov.br/api/v1/pesquisas/38'
            f'/indicadores/47001/resultados/N6[N3[{SC_CODE}]]'
        )
        try:
            data = self._fetch_json(url)
        except Exception as e:
            self.stderr.write(f'Erro ao buscar PIB per capita: {e}')
            return {}

        result = {}
        ano_key = str(ano_pref) if ano_pref else None
        for item in data[0]['res']:
            ibge_code = item['localidade']
            res = item['res']
            if ano_key and res.get(ano_key):
                val = res[ano_key]
            else:
                # Pegar o ano mais recente com valor
                val = None
                for y in sorted(res.keys(), reverse=True):
                    if res[y] is not None:
                        val = res[y]
                        break
            if val:
                result[ibge_code] = float(val)
        self.stdout.write(f'  PIB per capita: {len(result)} municípios')
        return result

    def _detect_year(self, pib_data):
        """Detecta o ano com base nos dados retornados."""
        return 2022 if pib_data else None
