import time
import tracemalloc

from django.core.management.base import BaseCommand
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Mede tempo/queries/memória de TODOS os endpoints do mapa (rodar no dyno).'

    def handle(self, *args, **opts):
        from django.conf import settings
        if 'testserver' not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

        from liderancas.models import Regiao, Cidade
        rslug = getattr(Regiao.objects.first(), 'slug', None)
        cslug = getattr(Cidade.objects.filter(geojson__isnull=False).first(), 'slug', None)

        endpoints = [
            ('state', '/mapa/api/state/'),
            ('state-cities', '/mapa/api/state-cities/'),
            ('overview', '/mapa/api/overview/'),
            ('elections-2022', '/mapa/api/elections-2022/'),
            ('calor-camadas', '/mapa/api/calor-camadas/'),
            ('pl-network', '/mapa/api/pl-network/'),
            ('zone-ranking', '/mapa/api/zone-ranking/'),
            ('vitoria', '/mapa/api/vitoria/'),
            ('neighbor-deputies', '/mapa/api/neighbor-deputies/'),
            ('strategic', '/mapa/api/strategic/'),
            ('vote-transfer', '/mapa/api/vote-transfer/'),
            ('competicao', '/mapa/api/competicao/'),
            ('perfil-ideologico', '/mapa/api/perfil-ideologico/'),
            ('demandas', '/mapa/api/demandas/'),
            ('roteiros', '/mapa/api/roteiros/'),
            ('roteiro-oportunidades', '/mapa/api/roteiro-oportunidades/'),
            ('roteiro-dia', '/mapa/api/roteiro-dia/'),
            ('urgencia-visita', '/mapa/api/urgencia-visita/'),
            ('candidatos-2022', '/mapa/api/candidatos-2022/'),
        ]
        for m in ('apoiadores', 'votes_2022', 'meta_progress', 'saturation', 'demandas_vencidas', 'gap'):
            endpoints.append((f'heat/{m}', f'/mapa/api/heatmap/{m}/'))
        endpoints.append(('heat/apoiadores?city', '/mapa/api/heatmap/apoiadores/?level=city'))
        endpoints.append(('heat/gap?city', '/mapa/api/heatmap/gap/?level=city'))
        if rslug:
            endpoints.append(('region', f'/mapa/api/region/{rslug}/'))
            endpoints.append(('dashboard/region', f'/mapa/api/dashboard/region/{rslug}/'))
        if cslug:
            endpoints.append(('city', f'/mapa/api/city/{cslug}/'))
            endpoints.append(('dashboard/city', f'/mapa/api/dashboard/city/{cslug}/'))

        U = get_user_model()
        u = U.objects.filter(is_superuser=True).first() or U.objects.first()
        c = Client()
        c.force_login(u)

        self.stdout.write(f'{"endpoint":26} {"status":>6} {"tempo":>9} {"queries":>8} {"py_MB":>7} {"KB":>7}')
        self.stdout.write('-' * 70)
        for name, url in endpoints:
            try:
                tracemalloc.start()
                with CaptureQueriesContext(connection) as q:
                    t = time.time()
                    r = c.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
                    dt = (time.time() - t) * 1000
                _c, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                flag = '  <<< LENTO' if dt > 2000 else ''
                self.stdout.write(
                    f'{name:26} {r.status_code:>6} {dt:>7.0f}ms {len(q):>8} '
                    f'{peak/1e6:>6.1f} {len(r.content)/1024:>6.0f}{flag}'
                )
            except Exception as e:
                tracemalloc.stop()
                self.stdout.write(f'{name:26}  ERRO: {type(e).__name__}: {str(e)[:60]}')
