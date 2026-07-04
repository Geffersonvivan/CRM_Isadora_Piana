"""
Importa resultados eleitorais OFICIAIS direto do TSE (Repositório de Dados Abertos).

Fonte: https://dadosabertos.tse.jus.br/  (votação de candidato por município e zona)
Arquivo: votacao_candidato_munzona_<ano>.zip  (nacional; extrai apenas o CSV de SC)

Diferença para `import_dados_mapa`:
    - Aquele copia um snapshot de 2022 do banco legado `Antigo/db.sqlite3`.
    - Este baixa os dados primários do TSE, conferíveis na fonte oficial.

Uso:
    python manage.py import_tse                         # 2022, todos os cargos estaduais/federais
    python manage.py import_tse --ano 2022
    python manage.py import_tse --cargos deputado_federal senador
    python manage.py import_tse --arquivo /caminho/votacao_candidato_munzona_2022.zip
    python manage.py import_tse --sem-zonas             # não importa ResultadoZona (mais leve)
    python manage.py import_tse --forcar-download       # ignora cache e rebaixa o zip
"""
import csv
import io
import re
import sys
import tempfile
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from liderancas.models import Cidade
from mapa.models import Eleicao, ResultadoCandidato, ResultadoZona

# URL base do CDN do TSE para o conjunto "votação de candidato por município e zona".
TSE_CDN_BASE = (
    'https://cdn.tse.jus.br/estatistica/sead/odsele/'
    'votacao_candidato_munzona/votacao_candidato_munzona_{ano}.zip'
)

# CD_CARGO (TSE) -> tipo no modelo Eleicao. Apenas cargos estaduais/federais.
CARGO_MAP = {
    '1': 'presidente',
    '3': 'governador',
    '5': 'senador',
    '6': 'deputado_federal',
    '7': 'deputado_estadual',
}

# Anos com choices válidos no modelo Eleicao.
ANOS_VALIDOS = {2018, 2022, 2026}


def _norm(texto):
    """Normaliza nome de município para casamento: maiúsculas, sem acento, sem pontuação."""
    if not texto:
        return ''
    texto = unicodedata.normalize('NFKD', texto)
    texto = texto.encode('ascii', 'ignore').decode('ascii')
    texto = texto.upper().strip()
    texto = re.sub(r'[^A-Z0-9 ]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto


class Command(BaseCommand):
    help = 'Importa resultados eleitorais oficiais do TSE (votação por município e zona).'

    def add_arguments(self, parser):
        parser.add_argument('--ano', type=int, default=2022, help='Ano da eleição (default 2022).')
        parser.add_argument(
            '--cargos', nargs='+', default=None,
            choices=list(CARGO_MAP.values()),
            help='Cargos a importar (default: todos os estaduais/federais).',
        )
        parser.add_argument('--arquivo', default=None, help='Caminho de um .zip já baixado do TSE.')
        parser.add_argument('--sem-zonas', action='store_true', help='Não importar resultados por zona.')
        parser.add_argument('--forcar-download', action='store_true', help='Rebaixa o zip ignorando cache.')

    def handle(self, *args, **options):
        ano = options['ano']
        if ano not in ANOS_VALIDOS:
            self.stderr.write(self.style.ERROR(
                f'Ano {ano} não está em Eleicao.ANO_CHOICES {sorted(ANOS_VALIDOS)}. '
                'Ajuste o modelo antes de importar outro ano.'
            ))
            return

        cargos = set(options['cargos']) if options['cargos'] else set(CARGO_MAP.values())

        # 1. Obter o arquivo (local ou download).
        zip_path = self._obter_zip(ano, options['arquivo'], options['forcar_download'])
        if not zip_path:
            return

        # 2. Mapa nome-normalizado -> Cidade (uma vez).
        cidade_por_nome = {_norm(c.nome): c for c in Cidade.objects.all()}
        self.stdout.write(f'{len(cidade_por_nome)} cidades carregadas para casamento por nome.')

        # 3. Ler e agregar o CSV de SC.
        dados = self._ler_csv_sc(zip_path, ano, cargos, sem_zonas=options['sem_zonas'])
        if dados is None:
            return

        # 4. Gravar no banco.
        self._gravar(ano, dados, cidade_por_nome, sem_zonas=options['sem_zonas'])

        self.stdout.write(self.style.SUCCESS('Importação do TSE concluída!'))

    # ------------------------------------------------------------------ pós-import
    def _atualizar_votos_cidade(self, ano, eleicao_por_chave):
        """Atualiza Cidade.votos_referencia_2022 somando os votos do candidato da
        campanha (settings.CAMPANHA) por cidade, no cargo-base configurado."""
        cargo_base = settings.CAMPANHA['TSE_CARGO_BASE']
        base = eleicao_por_chave.get((cargo_base, 1))
        if not base:
            return

        from django.db.models import Sum
        votos_por_cidade = (
            ResultadoCandidato.objects
            .filter(eleicao=base, is_candidato=True)
            .values('cidade_id')
            .annotate(total=Sum('votos'))
        )
        updated = 0
        for item in votos_por_cidade:
            n = Cidade.objects.filter(id=item['cidade_id']).update(
                votos_referencia_2022=item['total']
            )
            updated += n

        # Zerar cidades sem votos do candidato
        ids_com_votos = {item['cidade_id'] for item in votos_por_cidade}
        Cidade.objects.exclude(id__in=ids_com_votos).update(votos_referencia_2022=0)

        self.stdout.write(f'{updated} cidades atualizadas com votos de referência {ano}.')

    # ------------------------------------------------------------------ download
    def _obter_zip(self, ano, arquivo, forcar):
        if arquivo:
            p = Path(arquivo)
            if not p.exists():
                self.stderr.write(self.style.ERROR(f'Arquivo não encontrado: {p}'))
                return None
            self.stdout.write(f'Usando arquivo local: {p}')
            return p

        cache_dir = Path(tempfile.gettempdir()) / 'tse_cache'
        cache_dir.mkdir(exist_ok=True)
        destino = cache_dir / f'votacao_candidato_munzona_{ano}.zip'

        if destino.exists() and not forcar:
            self.stdout.write(f'Usando zip em cache: {destino} ({destino.stat().st_size // 1_000_000} MB)')
            return destino

        url = TSE_CDN_BASE.format(ano=ano)
        self.stdout.write(f'Baixando do TSE: {url}')
        tmp = destino.with_suffix('.zip.part')
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'CRM-Isadora/import_tse'})
            with urllib.request.urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get('Content-Length', 0))
                baixado = 0
                with open(tmp, 'wb') as f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        baixado += len(chunk)
                        if total:
                            pct = baixado * 100 // total
                            sys.stdout.write(f'\r  {baixado // 1_000_000}/{total // 1_000_000} MB ({pct}%)')
                            sys.stdout.flush()
            sys.stdout.write('\n')
            tmp.replace(destino)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Falha no download: {e}'))
            if tmp.exists():
                tmp.unlink()
            return None
        return destino

    # ------------------------------------------------------------------ leitura
    def _ler_csv_sc(self, zip_path, ano, cargos, sem_zonas):
        try:
            zf = zipfile.ZipFile(zip_path)
        except zipfile.BadZipFile:
            self.stderr.write(self.style.ERROR(
                f'Zip inválido/corrompido: {zip_path}. Use --forcar-download para rebaixar.'
            ))
            return None

        nome_sc = next((n for n in zf.namelist() if re.search(r'_SC\.csv$', n, re.I)), None)
        if not nome_sc:
            self.stderr.write(self.style.ERROR(
                f'CSV de SC não encontrado no zip. Conteúdo: {zf.namelist()[:10]}'
            ))
            return None
        self.stdout.write(f'Lendo {nome_sc} ...')

        # Agregados (somam votos em trânsito + nominais e através das zonas).
        # candidato: chave (tipo, turno, cd_mun, sq_cand)
        cand = {}
        # total de votos por (tipo, turno, cd_mun) para calcular percentual
        total_mun = {}
        # nome do município por código
        mun_nome = {}
        # zona: chave (tipo, turno, cd_mun, zona, sq_cand)
        zona = {} if not sem_zonas else None

        obrigatorias = {
            'CD_CARGO', 'NR_TURNO', 'CD_MUNICIPIO', 'NM_MUNICIPIO', 'NR_ZONA',
            'SQ_CANDIDATO', 'NR_CANDIDATO', 'NM_URNA_CANDIDATO', 'NM_CANDIDATO',
            'SG_PARTIDO', 'DS_SIT_TOT_TURNO', 'QT_VOTOS_NOMINAIS',
        }

        with zf.open(nome_sc) as raw:
            texto = io.TextIOWrapper(raw, encoding='latin-1', newline='')
            reader = csv.DictReader(texto, delimiter=';')
            faltando = obrigatorias - set(reader.fieldnames or [])
            if faltando:
                self.stderr.write(self.style.ERROR(
                    f'Colunas esperadas ausentes no CSV: {sorted(faltando)}. '
                    f'Cabeçalho recebido: {reader.fieldnames}'
                ))
                return None

            lidas = 0
            for row in reader:
                lidas += 1
                tipo = CARGO_MAP.get((row['CD_CARGO'] or '').strip())
                if not tipo or tipo not in cargos:
                    continue

                turno = int(row['NR_TURNO'] or 1)
                cd_mun = (row['CD_MUNICIPIO'] or '').strip()
                sq = (row['SQ_CANDIDATO'] or '').strip()
                try:
                    votos = int(row['QT_VOTOS_NOMINAIS'] or 0)
                except ValueError:
                    votos = 0

                mun_nome.setdefault(cd_mun, row['NM_MUNICIPIO'])
                total_mun[(tipo, turno, cd_mun)] = total_mun.get((tipo, turno, cd_mun), 0) + votos

                nome = row['NM_URNA_CANDIDATO'] or row['NM_CANDIDATO'] or ''
                sit = (row['DS_SIT_TOT_TURNO'] or '').strip()
                eleito = sit.upper().startswith('ELEITO')

                ck = (tipo, turno, cd_mun, sq)
                c = cand.get(ck)
                if c is None:
                    cand[ck] = {
                        'nome': nome, 'numero': row['NR_CANDIDATO'] or '',
                        'partido': row['SG_PARTIDO'] or '', 'eleito': eleito, 'votos': votos,
                    }
                else:
                    c['votos'] += votos
                    c['eleito'] = c['eleito'] or eleito

                if zona is not None and votos:
                    nr_zona = (row['NR_ZONA'] or '').strip()
                    zk = (tipo, turno, cd_mun, nr_zona, sq)
                    z = zona.get(zk)
                    if z is None:
                        zona[zk] = {
                            'nome': nome, 'numero': row['NR_CANDIDATO'] or '',
                            'partido': row['SG_PARTIDO'] or '', 'votos': votos,
                        }
                    else:
                        z['votos'] += votos

        self.stdout.write(
            f'{lidas} linhas lidas; {len(cand)} agregados candidato×município'
            + ('' if zona is None else f'; {len(zona)} candidato×zona')
        )
        return {'cand': cand, 'total_mun': total_mun, 'mun_nome': mun_nome, 'zona': zona}

    # ------------------------------------------------------------------ gravação
    def _gravar(self, ano, dados, cidade_por_nome, sem_zonas):
        cand = dados['cand']
        total_mun = dados['total_mun']
        mun_nome = dados['mun_nome']
        zona = dados['zona']

        # Resolver cd_municipio -> Cidade.
        cidade_por_cod = {}
        nao_encontrados = set()
        for cd_mun, nm in mun_nome.items():
            cidade = cidade_por_nome.get(_norm(nm))
            if cidade:
                cidade_por_cod[cd_mun] = cidade
            else:
                nao_encontrados.add(nm)
        if nao_encontrados:
            self.stdout.write(self.style.WARNING(
                f'{len(nao_encontrados)} municípios do TSE sem correspondência em Cidade: '
                + ', '.join(sorted(nao_encontrados)[:15])
                + ('...' if len(nao_encontrados) > 15 else '')
            ))

        # Eleições presentes nos dados.
        chaves_eleicao = {(tipo, turno) for (tipo, turno, _, _) in cand}

        with transaction.atomic():
            eleicao_por_chave = {}
            for tipo, turno in chaves_eleicao:
                eleicao, _ = Eleicao.objects.get_or_create(ano=ano, tipo=tipo, turno=turno)
                eleicao_por_chave[(tipo, turno)] = eleicao
                ResultadoCandidato.objects.filter(eleicao=eleicao).delete()
                ResultadoZona.objects.filter(eleicao=eleicao).delete()

            # Resultados por candidato×município.
            batch = []
            for (tipo, turno, cd_mun, _sq), c in cand.items():
                cidade = cidade_por_cod.get(cd_mun)
                if not cidade:
                    continue
                total = total_mun.get((tipo, turno, cd_mun), 0)
                pct = round(c['votos'] * 100 / total, 2) if total else 0
                nome_upper = (c['nome'] or '').upper()
                eh_candidato = settings.CAMPANHA['TSE_TERMO_BUSCA'] in nome_upper
                batch.append(ResultadoCandidato(
                    eleicao=eleicao_por_chave[(tipo, turno)],
                    candidato_nome=c['nome'][:255],
                    candidato_numero=str(c['numero'])[:10],
                    partido=c['partido'][:150],
                    cidade=cidade,
                    votos=c['votos'],
                    percentual=pct,
                    eleito=c['eleito'],
                    is_candidato=eh_candidato,
                ))
            ResultadoCandidato.objects.bulk_create(batch, batch_size=1000)
            self.stdout.write(f'{len(batch)} resultados por candidato gravados.')

            # Resultados por zona.
            if zona is not None:
                batch_z = []
                for (tipo, turno, cd_mun, nr_zona, _sq), z in zona.items():
                    cidade = cidade_por_cod.get(cd_mun)
                    if not cidade:
                        continue
                    nome_upper_z = (z['nome'] or '').upper()
                    eh_candidato_z = settings.CAMPANHA['TSE_TERMO_BUSCA'] in nome_upper_z
                    batch_z.append(ResultadoZona(
                        eleicao=eleicao_por_chave[(tipo, turno)],
                        candidato_nome=z['nome'][:255],
                        candidato_numero=str(z['numero'])[:10],
                        partido=z['partido'][:150],
                        cidade=cidade,
                        zona=str(nr_zona)[:10],
                        votos=z['votos'],
                        percentual=0,
                        is_candidato=eh_candidato_z,
                    ))
                ResultadoZona.objects.bulk_create(batch_z, batch_size=1000)
                self.stdout.write(f'{len(batch_z)} resultados por zona gravados.')

        for (tipo, turno), eleicao in sorted(eleicao_por_chave.items()):
            self.stdout.write(f'  • {eleicao}')

        # Atualizar Cidade.votos_referencia_2022 a partir dos resultados TSE.
        self._atualizar_votos_cidade(ano, eleicao_por_chave)
