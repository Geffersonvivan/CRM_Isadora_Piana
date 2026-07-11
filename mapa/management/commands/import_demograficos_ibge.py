"""
Importa dados demográficos do IBGE (Censo 2022) para IndicadorMunicipal.

Dados buscados:
- População urbana/rural (Censo 2022, tabela 4709)
- Faixa etária (Censo 2022, tabela 9514)
- Escolaridade (estimativa baseada em IDH-E)

Uso: python manage.py import_demograficos_ibge
"""
import gzip
import json
import urllib.request
from django.core.management.base import BaseCommand
from liderancas.models import Cidade
from mapa.models import IndicadorMunicipal


def _ibge_get(url, timeout=60):
    """Fetch JSON from IBGE API using urllib (no requests dependency)."""
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
        'User-Agent': 'CRM-Isadora/1.0',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            text = gzip.decompress(raw).decode('utf-8')
        return json.loads(text)

IBGE_SC = '42'  # Código SC


class Command(BaseCommand):
    help = 'Importa dados demográficos do IBGE para cidades de SC'

    def handle(self, *args, **options):
        cidades = {c.codigo_ibge: c for c in Cidade.objects.all() if c.codigo_ibge}
        if not cidades:
            # Tentar mapear por nome
            cidades_by_nome = {}
            for c in Cidade.objects.all():
                cidades_by_nome[c.nome.upper()] = c
            self.stdout.write(f'Cidades carregadas por nome: {len(cidades_by_nome)}')
        else:
            cidades_by_nome = {}
            self.stdout.write(f'Cidades com código IBGE: {len(cidades)}')

        updated = 0

        # ── 1) População por situação de domicílio (urbano/rural)
        # Censo 2022 - Tabela 4709 - Pop residente por situação
        self.stdout.write('Buscando população urbana/rural...')
        try:
            url = f'https://servicodados.ibge.gov.br/api/v3/agregados/4709/periodos/2022/variaveis/93?localidades=N6[N3[{IBGE_SC}]]&classificacao=1[1,2]'
            data = _ibge_get(url)

            if data and data[0].get('resultados'):
                for resultado in data[0]['resultados']:
                    classificacao = resultado.get('classificacoes', [{}])[0]
                    cat_id = list(classificacao.get('categoria', {}).keys())[0] if classificacao.get('categoria') else None

                    for loc in resultado.get('series', []):
                        cod_ibge = loc['localidade']['id']
                        valor = int(loc['serie'].get('2022', '0') or '0')

                        ind = self._get_indicador(cod_ibge, cidades, cidades_by_nome)
                        if not ind:
                            continue

                        if cat_id == '1':  # Urbana
                            ind.populacao_urbana = valor
                        elif cat_id == '2':  # Rural
                            ind.populacao_rural = valor
                        ind.save(update_fields=['populacao_urbana', 'populacao_rural'])
                        updated += 1

            self.stdout.write(self.style.SUCCESS(f'  Pop urbana/rural: {updated} registros'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Erro pop urbana/rural: {e}'))
            # §5.2: sem dado real -> fica vazio. NÃO estimar (proibido apresentar
            # sintético como medido, §5.1). Use import_urbano_real para o dado real.
            self.stdout.write(self.style.WARNING('  Urbanização sem dado (não estimada).'))

        # ── 2) Faixa etária
        self.stdout.write('Buscando faixa etária...')
        try:
            # Tabela 9514 - Pop por grupo de idade
            url = f'https://servicodados.ibge.gov.br/api/v3/agregados/9514/periodos/2022/variaveis/93?localidades=N6[N3[{IBGE_SC}]]&classificacao=287[100362,93084,93085,93086,93087,49108,49109,60040,60041,93088,93089,93090,93091,93092,93093,93094,93095,100363]'
            data = _ibge_get(url)

            idosos_count = 0
            jovens_count = 0

            if data and data[0].get('resultados'):
                # Categorias de idade:
                # 60-64=93092, 65-69=93093, 70-74=93094, 75-79=93095, 80+=100363 → idosos
                # 18-19≈93086(15-19 parcial), 20-24=93087, 25-29=49108 → jovens
                IDOSOS_CATS = {'93092', '93093', '93094', '93095', '100363'}
                JOVENS_CATS = {'93087', '49108'}  # 20-24, 25-29

                for resultado in data[0]['resultados']:
                    classificacao = resultado.get('classificacoes', [{}])[0]
                    cat_id = list(classificacao.get('categoria', {}).keys())[0] if classificacao.get('categoria') else None

                    for loc in resultado.get('series', []):
                        cod_ibge = loc['localidade']['id']
                        valor = int(loc['serie'].get('2022', '0') or '0')

                        ind = self._get_indicador(cod_ibge, cidades, cidades_by_nome)
                        if not ind:
                            continue

                        if cat_id in IDOSOS_CATS:
                            ind.idosos_60_mais = (ind.idosos_60_mais or 0) + valor
                            idosos_count += 1
                        elif cat_id in JOVENS_CATS:
                            ind.jovens_18_29 = (ind.jovens_18_29 or 0) + valor
                            jovens_count += 1
                        ind.save(update_fields=['idosos_60_mais', 'jovens_18_29'])

            self.stdout.write(self.style.SUCCESS(f'  Faixa etária: {idosos_count} idosos, {jovens_count} jovens'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Erro faixa etária: {e}'))
            # §5.2: sem dado real -> fica vazio. NÃO estimar por média de SC.
            self.stdout.write(self.style.WARNING('  Faixa etária sem dado (não estimada).'))

        # ── 3) Escolaridade/alfabetização: só dado real. Use import_alfabetizacao_real.
        # (§5.1: era estimada do PIB — removido. §5.2: sem dado fica vazio.)

        self.stdout.write(self.style.SUCCESS(f'\nImportação concluída (só dados reais do IBGE).'))

    def _get_indicador(self, cod_ibge, cidades, cidades_by_nome):
        """Busca ou cria IndicadorMunicipal para o código IBGE."""
        cidade = cidades.get(cod_ibge) or cidades.get(str(cod_ibge))
        if not cidade and cidades_by_nome:
            # Tentar buscar nome no IBGE
            return None
        if not cidade:
            return None

        ind, _ = IndicadorMunicipal.objects.get_or_create(
            cidade=cidade, ano_referencia=2022,
            defaults={'populacao': 0}
        )
        return ind

    # §5.1: estimadores sintéticos (urbanização/faixa etária/escolaridade derivadas
    # do PIB/renda) REMOVIDOS — era dado sintético apresentado como medido. O dado
    # real vem dos comandos import_urbano_real, import_alfabetizacao_real, etc.
