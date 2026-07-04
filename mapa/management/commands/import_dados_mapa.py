"""
Importa dados para o módulo de mapas:
1. População das cidades via IBGE API (web)
2. Dados internos do Antigo (votos 2022, metas, estrutura política, zonas eleitorais)
3. Resultados eleitorais 2022 do Antigo (CandidateResult, ZoneResult)

Uso:
    python manage.py import_dados_mapa          # importa tudo
    python manage.py import_dados_mapa --ibge   # só população IBGE
    python manage.py import_dados_mapa --antigo  # só dados do Antigo
"""
import json
import sqlite3
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Sum

from liderancas.models import Regiao, Cidade
from mapa.models import Eleicao, ResultadoCandidato, ResultadoZona

ANTIGO_DB = Path(__file__).resolve().parent.parent.parent.parent / 'Antigo' / 'db.sqlite3'

# Mapeamento tipo eleição Antigo -> CRM
ELECTION_TYPE_MAP = {
    'federal_deputy': 'deputado_federal',
    'state_deputy': 'deputado_estadual',
    'senator': 'senador',
    'governor': 'governador',
    'president': 'presidente',
    'mayor': 'prefeito',
    'councilor': 'vereador',
}


class Command(BaseCommand):
    help = 'Importa dados para o módulo de mapas (IBGE + Antigo)'

    def add_arguments(self, parser):
        parser.add_argument('--ibge', action='store_true', help='Importar apenas população do IBGE')
        parser.add_argument('--antigo', action='store_true', help='Importar apenas dados do Antigo')

    def handle(self, *args, **options):
        run_all = not options['ibge'] and not options['antigo']

        if run_all or options['ibge']:
            self._import_ibge_population()

        if run_all or options['antigo']:
            if not ANTIGO_DB.exists():
                self.stderr.write(f'Base do Antigo não encontrada: {ANTIGO_DB}')
            else:
                self._import_antigo_cities()
                self._import_antigo_elections()

        self._update_region_aggregates()
        self.stdout.write(self.style.SUCCESS('Importação concluída!'))

    def _import_ibge_population(self):
        """Importa população estimada 2024 das cidades de SC via IBGE API."""
        self.stdout.write('Baixando população estimada do IBGE...')

        # API IBGE - Estimativas de população 2024
        url = (
            'https://servicodados.ibge.gov.br/api/v3/agregados/6579'
            '/periodos/2024/variaveis/9324'
            '?localidades=N6[N3[42]]'
        )

        import gzip

        def fetch_json(u):
            req = urllib.request.Request(u, headers={
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

        try:
            data = fetch_json(url)
        except Exception as e:
            self.stderr.write(f'Erro ao acessar IBGE 2024: {e}')
            self.stdout.write('Tentando dados de 2022...')
            try:
                data = fetch_json(url.replace('2024', '2022'))
            except Exception as e2:
                self.stderr.write(f'Erro no fallback 2022: {e2}')
                return

        # Estrutura IBGE: [{ variavel, resultados: [{ localidade: {id, nome}, serie: {2024: valor} }] }]
        updated = 0
        try:
            resultados = data[0]['resultados'][0]['series']
            for item in resultados:
                ibge_code = item['localidade']['id']
                nome_ibge = item['localidade']['nome']
                # Pegar o valor mais recente
                pop_str = list(item['serie'].values())[0]
                if pop_str and pop_str != '...':
                    pop = int(pop_str)
                    n = Cidade.objects.filter(codigo_ibge=ibge_code).update(populacao=pop)
                    if n:
                        updated += 1
        except (KeyError, IndexError) as e:
            self.stderr.write(f'Erro ao processar dados IBGE: {e}')
            return

        self.stdout.write(f'{updated} cidades atualizadas com população IBGE')

    def _import_antigo_cities(self):
        """Importa dados de cidades do Antigo: votos, metas, estrutura política."""
        self.stdout.write('Importando dados de cidades do Antigo...')

        conn = sqlite3.connect(str(ANTIGO_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Carregar mapeamento ibge_code -> region slug do Antigo
        cursor.execute('''
            SELECT c.ibge_code, c.name, c.population, c.registered_voters,
                   c.votes_sorgatto_2022, c.mayor_name, c.mayor_party,
                   c.num_vereadores, c.num_vereadores_pl, c.pl_executive_president,
                   c.meta_votes, c.meta_doacoes, c.electoral_zone,
                   r.slug as region_slug
            FROM geography_city c
            JOIN geography_region r ON c.region_id = r.id
        ''')

        rows = cursor.fetchall()
        updated = 0
        not_found = 0

        for row in rows:
            ibge_code = row['ibge_code']
            try:
                city = Cidade.objects.get(codigo_ibge=ibge_code)
            except Cidade.DoesNotExist:
                not_found += 1
                continue

            # Atualizar com dados do Antigo (só se não tiver dados melhores da web).
            # Nomes de coluna do SELECT são do banco legado (Antigo) — mantidos como estão.
            city.votos_referencia_2022 = row['votes_sorgatto_2022'] or 0
            city.eleitores = row['registered_voters'] or 0
            city.prefeito_nome = row['mayor_name'] or ''
            city.prefeito_partido = row['mayor_party'] or ''
            city.num_vereadores = row['num_vereadores'] or 0
            city.num_vereadores_partido = row['num_vereadores_pl'] or 0
            city.presidente_diretorio = row['pl_executive_president'] or ''
            city.meta_votos = row['meta_votes'] or 0
            city.meta_doacoes = row['meta_doacoes'] or 0
            city.zona_eleitoral = row['electoral_zone'] or ''

            # Só atualizar população se não veio do IBGE (valor = 0)
            if city.populacao == 0 and row['population']:
                city.populacao = row['population']

            city.save(update_fields=[
                'votos_referencia_2022', 'eleitores', 'prefeito_nome', 'prefeito_partido',
                'num_vereadores', 'num_vereadores_partido', 'presidente_diretorio',
                'meta_votos', 'meta_doacoes', 'zona_eleitoral', 'populacao',
            ])
            updated += 1

        conn.close()
        self.stdout.write(f'{updated} cidades atualizadas do Antigo ({not_found} não encontradas)')

    def _import_antigo_elections(self):
        """Importa resultados eleitorais 2022 do Antigo."""
        self.stdout.write('Importando resultados eleitorais do Antigo...')

        conn = sqlite3.connect(str(ANTIGO_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Carregar eleições
        cursor.execute('SELECT id, year, election_type, round_number FROM elections_election')
        elections_antigo = cursor.fetchall()

        # Mapeamento ibge_code -> cidade_id no CRM
        city_map = dict(
            Cidade.objects.exclude(codigo_ibge__isnull=True)
            .exclude(codigo_ibge='')
            .values_list('codigo_ibge', 'id')
        )

        # Mapeamento antigo city_id -> ibge_code
        cursor.execute('SELECT id, ibge_code FROM geography_city')
        antigo_city_ibge = {row['id']: row['ibge_code'] for row in cursor.fetchall()}

        total_candidatos = 0
        total_zonas = 0

        for elec in elections_antigo:
            antigo_id = elec['id']
            tipo = ELECTION_TYPE_MAP.get(elec['election_type'])
            if not tipo:
                continue

            # Criar ou obter eleição no CRM
            eleicao, _ = Eleicao.objects.get_or_create(
                ano=elec['year'],
                tipo=tipo,
                turno=elec['round_number'] or 1,
            )

            # Limpar resultados antigos desta eleição
            ResultadoCandidato.objects.filter(eleicao=eleicao).delete()
            ResultadoZona.objects.filter(eleicao=eleicao).delete()

            # Importar resultados por candidato
            cursor.execute('''
                SELECT candidate_name, candidate_number, party, city_id,
                       votes, percentage, is_elected, is_sorgatto
                FROM elections_candidateresult
                WHERE election_id = ?
            ''', (antigo_id,))

            batch = []
            for row in cursor.fetchall():
                ibge = antigo_city_ibge.get(row['city_id'])
                cidade_id = city_map.get(ibge) if ibge else None
                if not cidade_id:
                    continue
                batch.append(ResultadoCandidato(
                    eleicao=eleicao,
                    candidato_nome=row['candidate_name'],
                    candidato_numero=row['candidate_number'] or '',
                    partido=row['party'] or '',
                    cidade_id=cidade_id,
                    votos=row['votes'] or 0,
                    percentual=row['percentage'] or 0,
                    eleito=bool(row['is_elected']),
                    is_candidato=bool(row['is_sorgatto']),
                ))

            if batch:
                ResultadoCandidato.objects.bulk_create(batch, batch_size=500)
                total_candidatos += len(batch)

            # Importar resultados por zona
            cursor.execute('''
                SELECT candidate_name, candidate_number, party, city_id,
                       zone_number, votes, percentage, is_sorgatto
                FROM elections_zoneresult
                WHERE election_id = ?
            ''', (antigo_id,))

            batch_z = []
            for row in cursor.fetchall():
                ibge = antigo_city_ibge.get(row['city_id'])
                cidade_id = city_map.get(ibge) if ibge else None
                if not cidade_id:
                    continue
                batch_z.append(ResultadoZona(
                    eleicao=eleicao,
                    candidato_nome=row['candidate_name'],
                    candidato_numero=row['candidate_number'] or '',
                    partido=row['party'] or '',
                    cidade_id=cidade_id,
                    zona=row['zone_number'] or '',
                    votos=row['votes'] or 0,
                    percentual=row['percentage'] or 0,
                    is_candidato=bool(row['is_sorgatto']),
                ))

            if batch_z:
                ResultadoZona.objects.bulk_create(batch_z, batch_size=500)
                total_zonas += len(batch_z)

        conn.close()
        self.stdout.write(f'{total_candidatos} resultados por candidato importados')
        self.stdout.write(f'{total_zonas} resultados por zona importados')

    def _update_region_aggregates(self):
        """Atualiza dados agregados das regiões."""
        self.stdout.write('Atualizando agregados das regiões...')
        updated = 0
        for region in Regiao.objects.all():
            agg = region.cidades.aggregate(
                pop=Sum('populacao'),
                eleit=Sum('eleitores'),
            )
            region.populacao = agg['pop'] or 0
            region.eleitores = agg['eleit'] or 0
            region.save(update_fields=['populacao', 'eleitores'])
            updated += 1
        self.stdout.write(f'{updated} regiões atualizadas')
