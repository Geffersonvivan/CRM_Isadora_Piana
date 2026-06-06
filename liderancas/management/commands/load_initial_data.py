from django.core.management.base import BaseCommand
from django.core.management import call_command
from liderancas.models import Regiao


class Command(BaseCommand):
    help = 'Load initial regions/cities if database is empty'

    def handle(self, *args, **options):
        if Regiao.objects.exists():
            self.stdout.write('Regions already loaded, skipping.')
            return
        call_command('loaddata', 'regioes_cidades_sc')
        self.stdout.write(self.style.SUCCESS('Initial data loaded successfully.'))
