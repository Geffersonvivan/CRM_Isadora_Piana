"""
Auto-detecção de redutos adversários a partir dos resultados de 2022.

Lógica prática e simples:
  Para cada cidade (não marcada à mão), mede a FORÇA IDEOLÓGICA da esquerda —
  quanto do voto total de deputado federal 2022 foi para partidos adversários
  (PT, PSOL, PCdoB, REDE, PV...). É o lean do eleitorado, não a ausência do LS:
    - esquerda >= 30% dos votos → 'adversario' (reduto hostil)
    - esquerda >= 20% dos votos → 'disputado'  (eleitorado dividido)
    - caso contrário            → não marca (terreno favorável/neutro)
  Guarda o deputado adversário mais votado como referência (nome/partido).

Não toca em cidades com controle_manual=True.

Uso:
    python manage.py detectar_redutos            # aplica
    python manage.py detectar_redutos --dry-run  # só mostra
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from liderancas.models import Cidade
from mapa.models import Eleicao, ResultadoCandidato

ADVERSARY_PARTIES = {'PT', 'PSOL', 'PCdoB', 'REDE', 'PV', 'SOLIDARIEDADE'}


class Command(BaseCommand):
    help = 'Detecta redutos adversários cruzando os votos de deputado de 2022.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry = options['dry_run']
        eleicao = Eleicao.objects.filter(ano=2022, tipo='deputado_federal').first()
        if not eleicao:
            self.stderr.write('Eleição deputado_federal 2022 não encontrada.')
            return

        # total de votos de deputado por cidade + votos da esquerda + melhor rival
        total_cidade = defaultdict(int)
        esq_cidade = defaultdict(int)
        rival = {}
        for r in (ResultadoCandidato.objects.filter(eleicao=eleicao)
                  .values('cidade_id', 'candidato_nome', 'partido', 'votos')
                  .order_by('cidade_id', '-votos')):
            cid = r['cidade_id']
            total_cidade[cid] += r['votos']
            if r['partido'] in ADVERSARY_PARTIES:
                esq_cidade[cid] += r['votos']
                if cid not in rival:   # mais votado da esquerda (já ordenado por votos desc)
                    rival[cid] = r

        adversario = disputado = limpo = pulado = 0
        for cid in Cidade.objects.all():
            if cid.controle_manual:
                pulado += 1
                continue
            total = total_cidade.get(cid.id, 0)
            esq = esq_cidade.get(cid.id, 0)
            share = (esq / total * 100) if total else 0
            r = rival.get(cid.id)

            if share >= 30:
                novo, nome, part = 'adversario', (r['candidato_nome'] if r else ''), (r['partido'] if r else '')
                adversario += 1
            elif share >= 20:
                novo, nome, part = 'disputado', (r['candidato_nome'] if r else ''), (r['partido'] if r else '')
                disputado += 1
            else:
                # LS competitivo: limpa marcação automática anterior (deixa p/ cadastro)
                novo, nome, part = '', '', ''
                if cid.controle in ('adversario', 'disputado'):
                    limpo += 1
                else:
                    continue

            if not dry:
                cid.controle = novo
                cid.adversario_nome = nome
                cid.adversario_partido = part
                cid.save(update_fields=['controle', 'adversario_nome', 'adversario_partido'])

        self.stdout.write(self.style.SUCCESS(
            f'Adversário: {adversario} | Em disputa: {disputado} | '
            f'limpos: {limpo} | manuais preservados: {pulado}'
            + (' (DRY-RUN)' if dry else '')
        ))
