"""
Importa a TAXA DE ALFABETIZAÇÃO real do Censo 2022 (IBGE tabela 10091, var 2513,
15 anos ou mais, % ) e grava em anos_estudo_medio — que passa a representar
alfabetização (%), substituindo a "escolaridade" que era estimada do PIB.
O rótulo no painel foi ajustado para "Alfabetização".

    python manage.py import_alfabetizacao_real [--dry-run]
"""
import gzip
import json
import urllib.request
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from liderancas.models import Cidade
from mapa.models import IndicadorMunicipal

URL = ('https://apisidra.ibge.gov.br/values/t/10091/n6/all/v/2513/p/last%201'
       '/c2/6794/c58/95253/c2661/32776/c1/6795')
ANO = 2022


def _get(u):
    req = urllib.request.Request(u, headers={'Accept': 'application/json', 'User-Agent': 'CRM-Isadora/1.0'})
    raw = urllib.request.urlopen(req, timeout=60).read()
    try:
        return json.loads(raw.decode('utf-8'))
    except UnicodeDecodeError:
        return json.loads(gzip.decompress(raw).decode('utf-8'))


class Command(BaseCommand):
    help = 'Importa taxa de alfabetização real do Censo 2022 (IBGE 10091)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        self.stdout.write('Buscando alfabetização real (IBGE 10091)...')
        try:
            data = _get(URL)
        except Exception as e:
            raise CommandError(f'IBGE falhou (tente de novo mais tarde): {e}')

        taxa = {}
        for r in data[1:]:
            cod = r.get('D1C', '')
            if not cod.startswith('42'):
                continue
            v = r.get('V')
            if v not in (None, '-', '..', '...', ''):
                try:
                    taxa[cod] = Decimal(str(round(float(v), 1)))
                except (ValueError, ArithmeticError):
                    continue
        if not taxa:
            raise CommandError('Nenhum valor de alfabetização retornado.')
        self.stdout.write(f'  Recebido: {len(taxa)} municípios')

        id_to_cod = {c.id: c.codigo_ibge for c in Cidade.objects.all() if c.codigo_ibge}
        inds = list(IndicadorMunicipal.objects.filter(ano_referencia=ANO).select_related('cidade'))
        mud, amostra = 0, []
        for i in inds:
            cod = id_to_cod.get(i.cidade_id)
            nova = taxa.get(cod) if cod else None
            if nova is None:
                continue
            if i.anos_estudo_medio != nova:
                if len(amostra) < 5:
                    amostra.append(f'{i.cidade.nome}: {i.anos_estudo_medio} -> {nova}% alfabetizados')
                mud += 1
                if not dry:
                    i.anos_estudo_medio = nova
        if not dry and mud:
            IndicadorMunicipal.objects.bulk_update(inds, ['anos_estudo_medio'])

        for a in amostra:
            self.stdout.write('   ' + a)
        verbo = 'mudariam' if dry else 'atualizados'
        self.stdout.write(self.style.SUCCESS(f'{mud} indicadores {verbo} com alfabetização REAL (Censo 2022).'))
