"""Backup nativo (restaurável) do CRM → arquivo JSON gzip, com upload opcional ao
Google Drive.

Gera um dump `dumpdata` PLANO (preserva PKs → restaura FKs fielmente via loaddata)
de tudo que é OPERACIONAL, excluindo:
  - efêmero/derivado: contenttypes, auth.permission, admin.logentry, sessions;
  - TSE massivo e REGENERÁVEL a partir dos arquivos oficiais (import_tse):
    mapa.resultadocandidato (~264k) e mapa.resultadozona (~106k).
Mantém Agenda, Tarefas, Lideranças (+ rede), Usuários e a geografia (Cidade/Regiao),
que são os dados que mudam e não dá pra reimportar.

Restaurar:  python manage.py loaddata <arquivo.json>   (após `gunzip`)
            ou:  python manage.py restore_backup <arquivo.json.gz>

Uso:
  python manage.py backup_to_drive                # gera o .json.gz local (e sobe ao Drive se configurado)
  python manage.py backup_to_drive --no-upload    # só gera o arquivo local
  python manage.py backup_to_drive --output /tmp/b.json.gz

Config do Drive (env), opcional — sem ela, só gera o arquivo local:
  GOOGLE_SERVICE_ACCOUNT_JSON = conteúdo do JSON da service account (ou caminho do arquivo)
  DRIVE_FOLDER_ID             = ID da pasta do Drive compartilhada com a service account
"""
import gzip
import io
import json
import os
from datetime import datetime, timezone

from django.core.management import call_command
from django.core.management.base import BaseCommand

EXCLUDES = [
    'contenttypes', 'auth.permission', 'admin.logentry', 'sessions',
    'mapa.resultadocandidato', 'mapa.resultadozona',
]


class Command(BaseCommand):
    help = 'Gera backup JSON gzip (restaurável) e, se configurado, sobe ao Google Drive.'

    def add_arguments(self, parser):
        parser.add_argument('--output', help='Caminho do .json.gz (default: /tmp/crm-backup-<ts>.json.gz)')
        parser.add_argument('--no-upload', action='store_true', help='Não subir ao Drive, só gerar o arquivo')

    def handle(self, *args, **opts):
        ts = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        nome = f'crm-isadora-backup-{ts}.json.gz'
        destino = opts.get('output') or os.path.join('/tmp', nome)

        # dumpdata para memória → grava gzip. dumpdata PLANO (sem natural keys):
        # preserva os PKs inteiros, então o loaddata recompõe FKs exatamente.
        buf = io.StringIO()
        call_command(
            'dumpdata',
            *[f'--exclude={e}' for e in EXCLUDES],
            stdout=buf,
        )
        dados = buf.getvalue().encode('utf-8')
        n_objs = len(json.loads(dados))

        with gzip.open(destino, 'wb') as f:
            f.write(dados)
        tam_mb = os.path.getsize(destino) / 1e6
        self.stdout.write(self.style.SUCCESS(
            f'Backup gerado: {destino}  ({n_objs} objetos, {tam_mb:.2f} MB gzip)'
        ))

        if opts.get('no_upload'):
            return

        cred = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '')
        folder = os.environ.get('DRIVE_FOLDER_ID', '')
        if not cred or not folder:
            self.stdout.write(self.style.WARNING(
                'GOOGLE_SERVICE_ACCOUNT_JSON/DRIVE_FOLDER_ID não configurados — '
                'arquivo gerado localmente, sem upload ao Drive.'
            ))
            return

        try:
            file_id = self._upload_drive(destino, os.path.basename(destino), cred, folder)
            self.stdout.write(self.style.SUCCESS(f'Enviado ao Google Drive (fileId={file_id}).'))
        except Exception as e:
            # Não estourar o job de backup por falha de upload: o arquivo local existe.
            self.stderr.write(self.style.ERROR(f'Falha no upload ao Drive: {type(e).__name__}: {e}'))
            raise

    def _upload_drive(self, path, nome, cred_raw, folder_id):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        # cred pode ser o JSON inline (env grande) ou um caminho de arquivo.
        if os.path.isfile(cred_raw):
            info = json.load(open(cred_raw))
        else:
            info = json.loads(cred_raw)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.file'],
        )
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        meta = {'name': nome, 'parents': [folder_id]}
        media = MediaFileUpload(path, mimetype='application/gzip', resumable=False)
        f = service.files().create(
            body=meta, media_body=media, fields='id', supportsAllDrives=True,
        ).execute()
        return f.get('id')
