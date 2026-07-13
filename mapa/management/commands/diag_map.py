import time
import tracemalloc
import resource

from django.core.management.base import BaseCommand
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.contrib.auth import get_user_model

ENDPOINTS = [
    ('state',             '/mapa/api/state/'),
    ('state-cities',      '/mapa/api/state-cities/'),
    ('overview',          '/mapa/api/overview/'),
    ('elections-2022',    '/mapa/api/elections-2022/'),
    ('calor-camadas',     '/mapa/api/calor-camadas/'),
    ('pl-network',        '/mapa/api/pl-network/'),
    ('zone-ranking',      '/mapa/api/zone-ranking/'),
    ('vitoria',           '/mapa/api/vitoria/'),
    ('neighbor-deputies', '/mapa/api/neighbor-deputies/'),
    ('heatmap/gap',       '/mapa/api/heatmap/gap/'),
]


def rss_mb():
    # ru_maxrss: em KB no Linux
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


class Command(BaseCommand):
    help = 'Mede tempo/queries/memória de cada endpoint do mapa (rodar no dyno).'

    def handle(self, *args, **opts):
        from django.conf import settings
        if 'testserver' not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

        U = get_user_model()
        u = U.objects.filter(is_superuser=True).first() or U.objects.first()
        c = Client()
        c.force_login(u)

        self.stdout.write(f'RSS inicial: {rss_mb():.0f} MB')
        self.stdout.write(
            f'{"endpoint":20} {"status":>6} {"tempo":>9} {"queries":>8} '
            f'{"py_pico_MB":>11} {"RSS_MB":>8}'
        )
        self.stdout.write('-' * 74)
        for name, url in ENDPOINTS:
            try:
                tracemalloc.start()
                with CaptureQueriesContext(connection) as q:
                    t = time.time()
                    r = c.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
                    dt = (time.time() - t) * 1000
                _cur, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                self.stdout.write(
                    f'{name:20} {r.status_code:>6} {dt:>7.0f}ms {len(q):>8} '
                    f'{peak/1e6:>10.1f} {rss_mb():>7.0f}'
                )
            except Exception as e:
                tracemalloc.stop()
                self.stdout.write(f'{name:20}  ERRO: {type(e).__name__}: {str(e)[:70]}')
        self.stdout.write(f'RSS final: {rss_mb():.0f} MB')
