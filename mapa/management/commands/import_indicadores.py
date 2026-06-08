"""
Importa indicadores socioeconômicos municipais de arquivo CSV.

CSV esperado (separador ; ou ,):
  codigo_ibge;pib;renda_per_capita;familias_bolsa_familia;populacao;meis_ativos

Uso:
    python manage.py import_indicadores dados.csv --ano 2022
    python manage.py import_indicadores dados.csv --ano 2022 --separador ","
"""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from liderancas.models import Cidade
from mapa.models import IndicadorMunicipal


class Command(BaseCommand):
    help = 'Importa indicadores socioeconômicos municipais de arquivo CSV'

    def add_arguments(self, parser):
        parser.add_argument('arquivo', type=str, help='Caminho do arquivo CSV')
        parser.add_argument('--ano', type=int, required=True, help='Ano de referência dos dados')
        parser.add_argument('--separador', type=str, default=';', help='Separador do CSV (default: ;)')

    def handle(self, *args, **options):
        path = Path(options['arquivo'])
        if not path.exists():
            raise CommandError(f'Arquivo não encontrado: {path}')

        ano = options['ano']
        sep = options['separador']

        # Mapeamento codigo_ibge -> Cidade
        city_map = {}
        for c in Cidade.objects.exclude(codigo_ibge__isnull=True).exclude(codigo_ibge=''):
            city_map[c.codigo_ibge] = c

        created = 0
        updated = 0
        skipped = 0

        with open(path, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=sep)

            # Normalizar nomes das colunas (strip + lower)
            if reader.fieldnames:
                reader.fieldnames = [n.strip().lower() for n in reader.fieldnames]

            for row in reader:
                codigo = row.get('codigo_ibge', '').strip()
                if not codigo:
                    skipped += 1
                    continue

                cidade = city_map.get(codigo)
                if not cidade:
                    self.stderr.write(f'Cidade não encontrada: {codigo}')
                    skipped += 1
                    continue

                defaults = {
                    'pib': self._decimal(row.get('pib', '0')),
                    'renda_per_capita': self._decimal(row.get('renda_per_capita', '0')),
                    'familias_bolsa_familia': self._int(row.get('familias_bolsa_familia', '0')),
                    'populacao': self._int(row.get('populacao', '0')),
                    'meis_ativos': self._int(row.get('meis_ativos', '0')),
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

    def _decimal(self, val):
        try:
            return Decimal(val.strip().replace(',', '.')) if val.strip() else Decimal('0')
        except (InvalidOperation, AttributeError):
            return Decimal('0')

    def _int(self, val):
        try:
            return int(val.strip().replace('.', '').replace(',', '')) if val.strip() else 0
        except (ValueError, AttributeError):
            return 0
