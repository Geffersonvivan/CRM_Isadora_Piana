"""
Sincroniza os indicadores municipais com dados REAIS das fontes oficiais e roda
a auditoria ao final. Pensado para execução agendada (Railway Cron mensal).

Etapas:
  1. População — Censo 2022 oficial (IBGE SIDRA tabela 4714, var 93).
     Atualiza Cidade.populacao e IndicadorMunicipal.populacao. É a peça que
     faltava de verdade: corrige a raiz do bug "populacao=1" (import_indicadores_ibge
     usa `cidade.populacao or 1`, então população 0/errada vira PIB per capita absurdo).
  2. PIB e derivados — reaproveita import_indicadores_ibge (IBGE real).
  3. Demografia — reaproveita import_demograficos_ibge (idade real do IBGE).
  4. Auditoria — roda auditar_indicadores; falha (exit!=0) sinaliza problema ao cron.

Uso:
    python manage.py sync_indicadores                 # tudo
    python manage.py sync_indicadores --so-populacao  # só etapa 1 (rápido, seguro)
    python manage.py sync_indicadores --dry-run        # mostra mudanças sem salvar
    railway run python manage.py sync_indicadores      # na produção
"""
import json
import urllib.request

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from liderancas.models import Cidade
from mapa.models import IndicadorMunicipal

SIDRA_POP_2022 = 'https://apisidra.ibge.gov.br/values/t/4714/n6/all/v/93/p/2022'
ANO_CENSO = 2022


class Command(BaseCommand):
    help = 'Sincroniza indicadores com dados reais (IBGE) e audita. Para Railway Cron.'

    def add_arguments(self, parser):
        parser.add_argument('--so-populacao', action='store_true',
                            help='Executa apenas a etapa de população (rápida e segura)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Mostra o que mudaria sem gravar')
        parser.add_argument('--sem-auditoria', action='store_true',
                            help='Não roda a auditoria ao final')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        self.stdout.write(self.style.MIGRATE_HEADING(
            '⟳ sync_indicadores' + (' (DRY-RUN)' if dry else '')))

        # ── Etapa 1: população real do Censo 2022 ──
        self._sync_populacao(dry)

        if not opts['so_populacao']:
            # ── Etapa 2: PIB real (reaproveita importador existente) ──
            self._run_step('import_indicadores_ibge', dry)
            # ── Etapa 3: demografia (urbano + escolaridade) ──
            self._run_step('import_demograficos_ibge', dry)
            # ── Etapa 3b: dados REAIS do Censo 2022 que sobrescrevem os sintéticos ──
            # Rodam DEPOIS dos importadores acima para substituir as estimativas.
            self._run_step('import_idade_real', dry)          # idosos/jovens reais
            self._run_step('import_renda_real', dry)          # renda real (não mais PIB)
            self._run_step('import_urbano_real', dry)         # urbano/rural real
            self._run_step('import_alfabetizacao_real', dry)  # alfabetização real
            # ── Etapa 3c: coordenadas faltantes pelo centroide do geojson ──
            self._run_step('preencher_coordenadas', dry)

        # ── Etapa 4: auditoria ──
        if not opts['sem_auditoria'] and not dry:
            self.stdout.write(self.style.MIGRATE_HEADING('\n[4/4] Auditoria'))
            try:
                call_command('auditar_indicadores')
            except SystemExit as e:
                if e.code:
                    self.stderr.write(self.style.ERROR(
                        'Auditoria encontrou problemas críticos — verifique acima.'))
                    raise

        self.stdout.write(self.style.SUCCESS('\n✅ sync_indicadores concluído.'))

    # ──────────────────────────────────────────────────────────────
    def _sync_populacao(self, dry):
        self.stdout.write(self.style.MIGRATE_HEADING('\n[1/4] População — Censo 2022 (IBGE)'))
        try:
            with urllib.request.urlopen(SIDRA_POP_2022, timeout=60) as resp:
                rows = json.loads(resp.read())[1:]
        except Exception as e:
            raise CommandError(f'Falha ao buscar população no IBGE SIDRA: {e}')

        censo = {}
        for r in rows:
            cod = r.get('D1C', '')
            val = r.get('V')
            if cod.startswith('42') and val not in (None, '', '-', '...'):
                try:
                    censo[cod] = int(float(val))
                except ValueError:
                    continue
        self.stdout.write(f'  IBGE retornou {len(censo)} municípios de SC.')

        cidades = list(Cidade.objects.exclude(codigo_ibge__isnull=True).exclude(codigo_ibge=''))
        alteradas, sem_match = 0, 0
        for c in cidades:
            real = censo.get(c.codigo_ibge)
            if real is None:
                sem_match += 1
                continue
            if c.populacao != real:
                if c.populacao in (0, None, 1):
                    self.stdout.write(self.style.WARNING(
                        f'  ⚠ {c.nome}: populacao {c.populacao} → {real} (raiz do bug pop=1)'))
                alteradas += 1
                if not dry:
                    c.populacao = real
        if not dry and alteradas:
            with transaction.atomic():
                Cidade.objects.bulk_update(cidades, ['populacao'])

        # Propaga para o IndicadorMunicipal do ano do Censo
        ind_alt = 0
        inds = list(IndicadorMunicipal.objects.filter(ano_referencia=ANO_CENSO).select_related('cidade'))
        for i in inds:
            real = censo.get(i.cidade.codigo_ibge)
            if real and i.populacao != real:
                ind_alt += 1
                if not dry:
                    i.populacao = real
        if not dry and ind_alt:
            IndicadorMunicipal.objects.bulk_update(inds, ['populacao'])

        verbo = 'mudariam' if dry else 'atualizadas'
        self.stdout.write(
            f'  Cidades {verbo}: {alteradas} | Indicadores {verbo}: {ind_alt} '
            f'| sem correspondência IBGE: {sem_match}')

    def _run_step(self, comando, dry):
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n[*] {comando}'))
        if dry:
            self.stdout.write('  (dry-run: pulado)')
            return
        try:
            call_command(comando)
        except Exception as e:  # não derruba o sync inteiro se um importador externo falhar
            self.stderr.write(self.style.ERROR(f'  {comando} falhou: {e}'))
