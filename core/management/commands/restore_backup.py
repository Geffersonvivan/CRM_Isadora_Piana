"""Restaura um backup gerado por `backup_to_drive` (JSON gzip) via loaddata.

Uso:
  python manage.py restore_backup /caminho/crm-isadora-backup-*.json.gz

ATENÇÃO: loaddata faz UPSERT por PK — sobrescreve registros existentes com os do
backup e cria os que faltam; NÃO apaga o que não está no backup. Para um restore
"limpo" (voltar exatamente ao estado do backup) é preciso zerar as tabelas antes,
o que é destrutivo — faça só com backup do estado atual + OK explícito (§9.4).
"""
import gzip
import os
import tempfile

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Restaura um backup .json.gz (loaddata). Sobrescreve por PK; não apaga o resto.'

    def add_arguments(self, parser):
        parser.add_argument('arquivo', help='Caminho do .json.gz (ou .json) do backup')

    def handle(self, *args, **opts):
        caminho = opts['arquivo']
        if not os.path.isfile(caminho):
            raise CommandError(f'Arquivo não encontrado: {caminho}')

        # loaddata precisa de um .json descompactado (aceita .json/.xml/.yaml por extensão).
        if caminho.endswith('.gz'):
            with gzip.open(caminho, 'rb') as fin:
                dados = fin.read()
            tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
            tmp.write(dados)
            tmp.close()
            alvo = tmp.name
            limpar = True
        else:
            alvo = caminho
            limpar = False

        self.stdout.write(f'Restaurando de {caminho} ...')
        try:
            call_command('loaddata', alvo)
        finally:
            if limpar:
                os.unlink(alvo)
        self.stdout.write(self.style.SUCCESS('Restore concluído (loaddata).'))
