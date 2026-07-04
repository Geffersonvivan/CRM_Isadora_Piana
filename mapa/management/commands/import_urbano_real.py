"""
Importa população urbana/rural REAL do Censo 2022 (IBGE tabela 9923) e SETA
populacao_urbana / populacao_rural por município. Substitui a estimativa
sintética (que era derivada do PIB).

    python manage.py import_urbano_real [--dry-run]
"""
import gzip
import json
import urllib.request

from django.core.management.base import BaseCommand, CommandError

from liderancas.models import Cidade
from mapa.models import IndicadorMunicipal

URL = 'https://apisidra.ibge.gov.br/values/t/9923/n6/all/v/93/p/2022/c1/1,2'
ANO = 2022


def _get(u):
    req = urllib.request.Request(u, headers={'Accept': 'application/json', 'User-Agent': 'CRM-Isadora/1.0'})
    raw = urllib.request.urlopen(req, timeout=60).read()
    try:
        return json.loads(raw.decode('utf-8'))
    except UnicodeDecodeError:
        return json.loads(gzip.decompress(raw).decode('utf-8'))


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class Command(BaseCommand):
    help = 'Importa população urbana/rural real do Censo 2022 (IBGE 9923)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        self.stdout.write('Buscando urbano/rural real (IBGE 9923)...')
        try:
            data = _get(URL)
        except Exception as e:
            raise CommandError(f'IBGE falhou (tente de novo mais tarde): {e}')

        urb, rur = {}, {}
        for r in data[1:]:
            cod = r.get('D1C', '')
            if not cod.startswith('42'):
                continue
            cat = r.get('D4C')
            if cat == '1':
                urb[cod] = _int(r.get('V'))
            elif cat == '2':
                rur[cod] = _int(r.get('V'))
        self.stdout.write(f'  Recebido: {len(urb)} urbana, {len(rur)} rural')

        id_to_cod = {c.id: c.codigo_ibge for c in Cidade.objects.all() if c.codigo_ibge}
        inds = list(IndicadorMunicipal.objects.filter(ano_referencia=ANO).select_related('cidade'))
        mud, amostra = 0, []
        for i in inds:
            cod = id_to_cod.get(i.cidade_id)
            if not cod or cod not in urb:
                continue
            nu, nr = urb.get(cod, 0), rur.get(cod, 0)
            if i.populacao_urbana != nu or i.populacao_rural != nr:
                if len(amostra) < 5:
                    pct = round(100 * nu / (nu + nr), 1) if (nu + nr) else 0
                    amostra.append(f'{i.cidade.nome}: urb {i.populacao_urbana}->{nu}, rur {i.populacao_rural}->{nr} ({pct}% urb)')
                mud += 1
                if not dry:
                    i.populacao_urbana, i.populacao_rural = nu, nr
        if not dry and mud:
            IndicadorMunicipal.objects.bulk_update(inds, ['populacao_urbana', 'populacao_rural'])

        for a in amostra:
            self.stdout.write('   ' + a)
        verbo = 'mudariam' if dry else 'atualizados'
        self.stdout.write(self.style.SUCCESS(f'{mud} indicadores {verbo} com urbano/rural REAL do Censo 2022.'))
