"""
Importa RENDA REAL do Censo 2022 — rendimento nominal médio mensal domiciliar
per capita (IBGE tabela 3563, var 2010, situação Total / classe Total) — e SETA
renda_per_capita. Substitui o valor sintético, que era o PIB per capita renomeado.

    python manage.py import_renda_real [--dry-run]
"""
import gzip
import json
import statistics
import urllib.request
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from liderancas.models import Cidade
from mapa.models import IndicadorMunicipal

URL = 'https://apisidra.ibge.gov.br/values/t/3563/n6/all/v/2010/p/last%201/c1/6795/c386/9680'
ANO = 2022


def _get(u):
    req = urllib.request.Request(u, headers={'Accept': 'application/json', 'User-Agent': 'CRM-Sorgatto/1.0'})
    raw = urllib.request.urlopen(req, timeout=60).read()
    try:
        return json.loads(raw.decode('utf-8'))
    except UnicodeDecodeError:
        return json.loads(gzip.decompress(raw).decode('utf-8'))


class Command(BaseCommand):
    help = 'Importa renda real (rendimento per capita) do Censo 2022 (IBGE 3563)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        self.stdout.write('Buscando renda real (IBGE 3563, rendimento per capita)...')
        try:
            data = _get(URL)
        except Exception as e:
            raise CommandError(f'IBGE falhou (tente de novo mais tarde): {e}')

        renda = {}
        for r in data[1:]:
            cod = r.get('D1C', '')
            if not cod.startswith('42'):
                continue
            v = r.get('V')
            if v not in (None, '-', '..', '...', ''):
                try:
                    renda[cod] = Decimal(str(float(v)))
                except (ValueError, ArithmeticError):
                    continue
        if not renda:
            raise CommandError('Nenhum valor de renda retornado.')
        mediana = Decimal(str(statistics.median([float(x) for x in renda.values()])))
        self.stdout.write(f'  Recebido: {len(renda)} municípios | mediana SC = R$ {mediana}')

        id_to_cod = {c.id: c.codigo_ibge for c in Cidade.objects.all() if c.codigo_ibge}
        inds = list(IndicadorMunicipal.objects.filter(ano_referencia=ANO).select_related('cidade'))
        mud, imputadas, amostra = 0, 0, []
        for i in inds:
            cod = id_to_cod.get(i.cidade_id)
            if not cod:
                continue
            nova = renda.get(cod)
            if nova is None:
                nova = mediana  # imputa mediana nas 2 sem dado (não contamina escala)
                imputadas += 1
            if i.renda_per_capita != nova:
                if len(amostra) < 5:
                    amostra.append(f'{i.cidade.nome}: R$ {i.renda_per_capita} -> R$ {nova}')
                mud += 1
                if not dry:
                    i.renda_per_capita = nova
        if not dry and mud:
            IndicadorMunicipal.objects.bulk_update(inds, ['renda_per_capita'])

        for a in amostra:
            self.stdout.write('   ' + a)
        verbo = 'mudariam' if dry else 'atualizados'
        self.stdout.write(self.style.SUCCESS(
            f'{mud} indicadores {verbo} com renda REAL do Censo 2022 ({imputadas} imputadas com mediana).'))
