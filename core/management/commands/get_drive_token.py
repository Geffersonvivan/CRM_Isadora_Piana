"""Gera, UMA VEZ, o refresh token OAuth para o backup subir ao Drive como o
usuário (necessário em Drive pessoal/Gmail — service account não tem cota lá).

Uso (na sua máquina, com navegador):
  python manage.py get_drive_token --client caminho/client_secret_XXX.json

Abre o navegador para o consentimento e salva client_id/secret/refresh_token em
.drive_oauth.json (gitignored). NÃO commite esse arquivo. Depois eu leio dele
para setar as variáveis no Railway.

O --client é o JSON do "OAuth Client ID" tipo **Desktop app** (Google Cloud
Console → APIs e Serviços → Credenciais).
"""
import json

from django.core.management.base import BaseCommand, CommandError

# Escopo completo: necessário para escrever numa pasta que o app NÃO criou
# (a pasta já existe no Drive do usuário). Sobe só a partir da conta do usuário.
SCOPES = ['https://www.googleapis.com/auth/drive']


class Command(BaseCommand):
    help = 'Gera o refresh token OAuth (fluxo local no navegador) para o backup ao Drive.'

    def add_arguments(self, parser):
        parser.add_argument('--client', required=True,
                            help='client_secret_*.json do OAuth Client (tipo Desktop app)')
        parser.add_argument('--output', default='.drive_oauth.json',
                            help='Onde salvar as credenciais (default: .drive_oauth.json, gitignored)')

    def handle(self, *args, **opts):
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            raise CommandError('Falta a lib: pip install google-auth-oauthlib')

        flow = InstalledAppFlow.from_client_secrets_file(opts['client'], SCOPES)
        # access_type=offline + prompt=consent garantem o refresh_token.
        creds = flow.run_local_server(port=0, access_type='offline', prompt='consent',
                                      open_browser=True)

        if not creds.refresh_token:
            raise CommandError(
                'Não veio refresh_token. Revogue o acesso do app em '
                'myaccount.google.com/permissions e rode de novo.'
            )

        data = {
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
        }
        with open(opts['output'], 'w') as f:
            json.dump(data, f, indent=2)
        self.stdout.write(self.style.SUCCESS(
            f'OK — credenciais salvas em {opts["output"]} (gitignored). NÃO commite. '
            'Avise que já pode configurar o Railway.'
        ))
