"""
Preenche latitude/longitude das cidades a partir do centroide do geojson já
armazenado — sem download nem API. Útil para as cidades sem coordenada no mapa.

    python manage.py preencher_coordenadas            # só as que faltam
    python manage.py preencher_coordenadas --todas     # recalcula todas
    python manage.py preencher_coordenadas --dry-run   # mostra sem gravar
"""
from django.core.management.base import BaseCommand

from liderancas.models import Cidade


def _ring_centroid(ring):
    """Centroide (x, y) de um anel pela fórmula do shoelace. x=lng, y=lat."""
    n = len(ring)
    if n < 3:
        return None
    a = cx = cy = 0.0
    for i in range(n):
        x0, y0 = ring[i][0], ring[i][1]
        x1, y1 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if a == 0:
        # anel degenerado: média simples dos vértices
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(xs) / n, sum(ys) / n
    a *= 0.5
    return cx / (6 * a), cy / (6 * a)


def _poly_area(ring):
    n = len(ring)
    a = 0.0
    for i in range(n):
        x0, y0 = ring[i][0], ring[i][1]
        x1, y1 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        a += x0 * y1 - x1 * y0
    return abs(a) * 0.5


def centroid_from_geojson(geo):
    """Retorna (lat, lng) do geojson Polygon/MultiPolygon, ou None."""
    if not isinstance(geo, dict):
        return None
    t = geo.get('type')
    coords = geo.get('coordinates')
    if not coords:
        return None
    if t == 'Polygon':
        ring = coords[0]
    elif t == 'MultiPolygon':
        # usa o anel exterior do maior polígono
        ring = max((poly[0] for poly in coords), key=_poly_area, default=None)
    else:
        return None
    if not ring:
        return None
    c = _ring_centroid(ring)
    if not c:
        return None
    lng, lat = c
    return round(lat, 6), round(lng, 6)


class Command(BaseCommand):
    help = 'Preenche lat/lng das cidades pelo centroide do geojson (sem API)'

    def add_arguments(self, parser):
        parser.add_argument('--todas', action='store_true', help='Recalcula todas, não só as vazias')
        parser.add_argument('--dry-run', action='store_true', help='Mostra sem gravar')

    def handle(self, *args, **opts):
        todas, dry = opts['todas'], opts['dry_run']
        cidades = list(Cidade.objects.all())
        alvo = cidades if todas else [c for c in cidades if c.latitude is None or c.longitude is None]
        self.stdout.write(f'Cidades a processar: {len(alvo)} (--todas={todas})')

        atualizadas, sem_geo, erros, desvios = [], 0, 0, []
        for c in alvo:
            if not c.geojson:
                sem_geo += 1
                continue
            cen = centroid_from_geojson(c.geojson)
            if not cen:
                erros += 1
                continue
            lat, lng = cen
            # sanidade: SC fica ~ lat -25.9..-29.4, lng -48.3..-53.8
            if not (-30 <= lat <= -25 and -54 <= lng <= -48):
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ {c.nome}: centroide fora de SC ({lat},{lng}) — pulado'))
                erros += 1
                continue
            if todas and c.latitude is not None:
                desvios.append(abs(c.latitude - lat) + abs(c.longitude - lng))
            if not dry:
                c.latitude, c.longitude = lat, lng
            atualizadas.append(c)

        if not dry and atualizadas:
            Cidade.objects.bulk_update(atualizadas, ['latitude', 'longitude'])

        verbo = 'atualizariam' if dry else 'atualizadas'
        self.stdout.write(self.style.SUCCESS(
            f'{len(atualizadas)} {verbo} | sem geojson: {sem_geo} | erros/fora de SC: {erros}'))
        if desvios:
            import statistics
            self.stdout.write(
                f'Validação (--todas): desvio médio vs lat/lng atual = '
                f'{statistics.mean(desvios):.4f}° (máx {max(desvios):.4f}°)')
