"""
Importa faixa etária REAL do Censo 2022 (IBGE tabela 9514) e SETA idosos_60_mais
e jovens_18_29 (20-29) por município. Diferente do import_demograficos_ibge, este:
  - usa parser robusto ('-', '..', '...' viram 0);
  - SOMA em memória e GRAVA por bulk_update (rápido, sem += acumulando);
  - não duplica se reexecutado (idempotente).

    python manage.py import_idade_real
    python manage.py import_idade_real --dry-run
    railway run/DATABASE_URL=... python manage.py import_idade_real
"""
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from liderancas.models import Cidade
from mapa.models import IndicadorMunicipal
from mapa.management.commands.import_demograficos_ibge import _ibge_get

IDOSOS_CATS = ['93092', '93093', '93094', '93095', '100363']  # 60-64..80+
JOVENS_CATS = ['93087', '49108']                              # 20-24, 25-29
ANO = 2022


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0  # '-', '..', '...', 'X' => sem dado


class Command(BaseCommand):
    help = 'Importa idade real (idosos 60+, jovens 20-29) do Censo 2022 (IBGE 9514)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def _fetch(self, cats):
        url = (f'https://servicodados.ibge.gov.br/api/v3/agregados/9514/periodos/{ANO}'
               f'/variaveis/93?localidades=N6[N3[42]]&classificacao=287[{",".join(cats)}]')
        data = _ibge_get(url)
        out = defaultdict(int)
        for resultado in data[0].get('resultados', []):
            for loc in resultado.get('series', []):
                cod = loc['localidade']['id']
                out[cod] += _int(loc['serie'].get(str(ANO)))
        return out

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        self.stdout.write('Buscando faixa etária real (IBGE 9514)...')
        try:
            idosos = self._fetch(IDOSOS_CATS)
            jovens = self._fetch(JOVENS_CATS)
        except Exception as e:
            raise CommandError(f'IBGE falhou (tente de novo mais tarde): {e}')
        self.stdout.write(f'  Recebido: {len(idosos)} municípios (idosos), {len(jovens)} (jovens)')

        cid_by_cod = {c.codigo_ibge: c.id for c in Cidade.objects.all() if c.codigo_ibge}
        inds = list(IndicadorMunicipal.objects.filter(ano_referencia=ANO).select_related('cidade'))
        id_to_cod = {cid: cod for cod, cid in cid_by_cod.items()}  # cidade_id -> codigo_ibge

        mud, amostra = 0, []
        for i in inds:
            cod = id_to_cod.get(i.cidade_id)
            if not cod:
                continue
            ni, nj = idosos.get(cod), jovens.get(cod)
            if ni is None and nj is None:
                continue
            if i.idosos_60_mais != (ni or 0) or i.jovens_18_29 != (nj or 0):
                if len(amostra) < 5:
                    amostra.append(f'{i.cidade.nome}: idosos {i.idosos_60_mais}->{ni}, jovens {i.jovens_18_29}->{nj}')
                mud += 1
                if not dry:
                    i.idosos_60_mais = ni or 0
                    i.jovens_18_29 = nj or 0
        if not dry and mud:
            IndicadorMunicipal.objects.bulk_update(inds, ['idosos_60_mais', 'jovens_18_29'])

        for a in amostra:
            self.stdout.write('   ' + a)
        verbo = 'mudariam' if dry else 'atualizados'
        self.stdout.write(self.style.SUCCESS(f'{mud} indicadores {verbo} com idade REAL do Censo 2022.'))
