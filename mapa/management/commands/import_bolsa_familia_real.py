"""
Importa o nº REAL de famílias no Bolsa Família por município, da API do Portal da
Transparência (CGU), e SETA familias_bolsa_familia. Substitui a estimativa
sintética (derivada do PIB).

Exige um token gratuito do Portal da Transparência (header `chave-api-dados`):
  1. Acesse https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email
  2. Cadastre seu e-mail e receba a chave.
  3. Passe a chave via env PORTAL_TRANSPARENCIA_TOKEN ou --token.

    PORTAL_TRANSPARENCIA_TOKEN=xxxx python manage.py import_bolsa_familia_real --mes 202604
    python manage.py import_bolsa_familia_real --token xxxx --mes 202604 --dry-run

Sem --mes, tenta os últimos meses até achar dados publicados.
"""
import json
import os
import time
import urllib.request
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from liderancas.models import Cidade
from mapa.models import IndicadorMunicipal

BASE = 'https://api.portaldatransparencia.gov.br/api-de-dados/bolsa-familia-por-municipio'
ANO_IND = 2022


class Command(BaseCommand):
    help = 'Importa famílias do Bolsa Família por município (API Portal da Transparência)'

    def add_arguments(self, parser):
        parser.add_argument('--token', type=str, default=None, help='chave-api-dados (ou env PORTAL_TRANSPARENCIA_TOKEN)')
        parser.add_argument('--mes', type=str, default=None, help='Mês de referência AAAAMM (ex.: 202604)')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--delay', type=float, default=0.2, help='Pausa entre chamadas (rate limit)')

    def _get(self, url, token):
        req = urllib.request.Request(url, headers={
            'accept': 'application/json',
            'chave-api-dados': token,
            'User-Agent': 'CRM-Sorgatto/1.0',
        })
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode('utf-8'))

    def _meses_candidatos(self, mes):
        if mes:
            return [mes]
        hoje = date.today()
        out = []
        y, m = hoje.year, hoje.month
        for _ in range(6):  # tenta os últimos 6 meses
            m -= 1
            if m == 0:
                m = 12; y -= 1
            out.append(f'{y}{m:02d}')
        return out

    def handle(self, *args, **opts):
        token = opts['token'] or os.getenv('PORTAL_TRANSPARENCIA_TOKEN')
        if not token:
            raise CommandError(
                'Falta o token. Cadastre em '
                'https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email '
                'e passe via PORTAL_TRANSPARENCIA_TOKEN ou --token.')
        dry, delay = opts['dry_run'], opts['delay']

        cidades = [c for c in Cidade.objects.all() if c.codigo_ibge]
        self.stdout.write(f'Cidades com código IBGE: {len(cidades)}')

        # Descobre o mês com dados publicados testando a 1ª cidade
        mes_ok = None
        for mes in self._meses_candidatos(opts['mes']):
            try:
                amostra = self._get(f'{BASE}?mesAno={mes}&codigoIbge={cidades[0].codigo_ibge}&pagina=1', token)
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise CommandError('Token inválido (401). Verifique a chave-api-dados.')
                continue
            if amostra:
                mes_ok = mes
                break
        if not mes_ok:
            raise CommandError('Nenhum mês recente retornou dados. Informe --mes AAAAMM.')
        self.stdout.write(f'Mês de referência com dados: {mes_ok}')

        id_to_ind = {i.cidade_id: i for i in IndicadorMunicipal.objects.filter(ano_referencia=ANO_IND)}
        mud, faltou, amostra = 0, 0, []
        to_update = []
        for n, c in enumerate(cidades, 1):
            try:
                dados = self._get(f'{BASE}?mesAno={mes_ok}&codigoIbge={c.codigo_ibge}&pagina=1', token)
            except Exception:
                faltou += 1
                continue
            qtd = dados[0].get('quantidadeBeneficiados') if dados else None
            if qtd is None:
                faltou += 1
                continue
            ind = id_to_ind.get(c.id)
            if not ind:
                continue
            if ind.familias_bolsa_familia != int(qtd):
                if len(amostra) < 5:
                    amostra.append(f'{c.nome}: {ind.familias_bolsa_familia} -> {qtd}')
                ind.familias_bolsa_familia = int(qtd)
                to_update.append(ind)
                mud += 1
            if delay:
                time.sleep(delay)
            if n % 50 == 0:
                self.stdout.write(f'  ...{n}/{len(cidades)}')

        if not dry and to_update:
            IndicadorMunicipal.objects.bulk_update(to_update, ['familias_bolsa_familia'])

        for a in amostra:
            self.stdout.write('   ' + a)
        verbo = 'mudariam' if dry else 'atualizados'
        self.stdout.write(self.style.SUCCESS(
            f'{mud} indicadores {verbo} com Bolsa Família REAL ({mes_ok}). Sem dados: {faltou}.'))
