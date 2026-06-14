"""
Auditoria completa dos dados de IndicadorMunicipal e Cidade.

Verifica cobertura, impossibilidades lógicas, divergências e identifica quais
indicadores são sintéticos (derivados do PIB per capita). Pensado para rodar
tanto no banco local quanto na produção (Railway):

    python manage.py auditar_indicadores
    railway run python manage.py auditar_indicadores

Sai com código de saída 1 se houver problema CRÍTICO (útil para cron/CI).
Com --json imprime um resumo legível por máquina.
"""
import json
import math
import statistics

from django.core.management.base import BaseCommand

from liderancas.models import Cidade
from mapa.models import IndicadorMunicipal

SC_MUNICIPIOS = 295


def _f(n):
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def _corr(a, b):
    if len(a) < 2:
        return 0.0
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else 0.0


class Command(BaseCommand):
    help = 'Audita IndicadorMunicipal/Cidade: cobertura, erros lógicos e dados sintéticos'

    def add_arguments(self, parser):
        parser.add_argument('--ano', type=int, default=None,
                            help='Filtra indicadores por ano de referência')
        parser.add_argument('--json', action='store_true',
                            help='Imprime resumo em JSON (para cron/alertas)')
        parser.add_argument('--strict', action='store_true',
                            help='Considera "eleitores > população" como crítico')

    def handle(self, *args, **opts):
        ano = opts['ano']
        as_json = opts['json']
        strict = opts['strict']

        cidades = list(Cidade.objects.all())
        qs = IndicadorMunicipal.objects.select_related('cidade')
        if ano:
            qs = qs.filter(ano_referencia=ano)
        inds = list(qs)

        ind_by_cid = {}
        for i in inds:
            ind_by_cid.setdefault(i.cidade_id, []).append(i)

        report = {'criticos': [], 'avisos': [], 'notas': [], 'metricas': {}}

        def crit(msg):
            report['criticos'].append(msg)

        def warn(msg):
            report['avisos'].append(msg)

        # ── Cobertura ──
        sem_ind = [c for c in cidades if c.id not in ind_by_cid]
        dup = {cid: v for cid, v in ind_by_cid.items() if len(v) > 1}
        anos = sorted({i.ano_referencia for i in inds})
        report['metricas']['cidades'] = len(cidades)
        report['metricas']['indicadores'] = len(inds)
        report['metricas']['cidades_sem_indicador'] = len(sem_ind)
        report['metricas']['duplicados'] = len(dup)
        report['metricas']['anos'] = anos
        if len(cidades) != SC_MUNICIPIOS:
            warn(f'{len(cidades)} cidades cadastradas (SC tem {SC_MUNICIPIOS})')
        if sem_ind:
            crit(f'{len(sem_ind)} cidades SEM indicador: ' +
                 ', '.join(c.nome for c in sem_ind[:10]) + ('...' if len(sem_ind) > 10 else ''))
        if dup:
            crit(f'{len(dup)} cidades com indicador duplicado (cidade+ano)')

        # ── Cidade: campos base ──
        c_pop0 = [c for c in cidades if (c.populacao or 0) <= 0]
        c_elt0 = [c for c in cidades if (c.eleitores or 0) <= 0]
        c_elt_gt = [c for c in cidades if c.eleitores and c.populacao and c.eleitores > c.populacao]
        c_ibge = [c for c in cidades if not c.codigo_ibge]
        c_geo = [c for c in cidades if c.latitude is None or c.longitude is None]
        if c_pop0:
            crit(f'{len(c_pop0)} cidades com populacao <= 0: ' + ', '.join(c.nome for c in c_pop0[:10]))
        if c_elt0:
            warn(f'{len(c_elt0)} cidades com eleitores <= 0')
        if c_ibge:
            warn(f'{len(c_ibge)} cidades sem codigo_ibge')
        if c_geo:
            warn(f'{len(c_geo)} cidades sem lat/lng')
        # eleitores > população é ESPERADO em micro-municípios (Censo conta morador
        # de fato; TSE conta título — muita gente vota na cidade natal e mora fora).
        # Só é suspeito quando a desproporção é extrema (> 1,5×).
        c_elt_extremo = [c for c in c_elt_gt if c.eleitores > c.populacao * 1.5]
        if c_elt_gt:
            report['notas'].append(
                f'{len(c_elt_gt)} cidades têm eleitores > população (ESPERADO em micro-municípios — '
                f'morador de fato < títulos): ' +
                ', '.join(f'{c.nome}({c.eleitores}>{c.populacao})' for c in
                          sorted(c_elt_gt, key=lambda c: c.eleitores / c.populacao, reverse=True)[:6]))
        if c_elt_extremo:
            msg = (f'{len(c_elt_extremo)} cidades com eleitores > 1,5× a população (suspeito): ' +
                   ', '.join(f'{c.nome}({c.eleitores}>{c.populacao})' for c in c_elt_extremo[:8]))
            (crit if strict else warn)(msg)
        report['metricas']['eleitores_maior_populacao'] = len(c_elt_gt)
        report['metricas']['eleitores_extremo'] = len(c_elt_extremo)

        # ── Indicador: impossibilidades lógicas ──
        def bad(pred):
            return [i for i in inds if pred(i)]

        checks_crit = {
            'populacao <= 0': bad(lambda i: (i.populacao or 0) <= 0),
            'idosos > populacao': bad(lambda i: i.populacao and i.idosos_60_mais > i.populacao),
            'jovens > populacao': bad(lambda i: i.populacao and i.jovens_18_29 > i.populacao),
            'bolsa_familia > populacao': bad(lambda i: i.populacao and i.familias_bolsa_familia > i.populacao),
            'meis > populacao': bad(lambda i: i.populacao and i.meis_ativos > i.populacao),
        }
        for nome, lst in checks_crit.items():
            if lst:
                crit(f'{len(lst)} indicadores com {nome}: ' +
                     ', '.join(i.cidade.nome for i in lst[:8]))

        pop_baixa = bad(lambda i: 0 < (i.populacao or 0) < 500)
        if pop_baixa:
            warn(f'{len(pop_baixa)} indicadores com populacao < 500 (suspeito): ' +
                 ', '.join(f'{i.cidade.nome}({i.populacao})' for i in pop_baixa[:10]))
        # anos_estudo_medio passou a guardar a TAXA DE ALFABETIZAÇÃO (%), 0-100.
        esc_inv = bad(lambda i: float(i.anos_estudo_medio or 0) <= 0 or float(i.anos_estudo_medio or 0) > 100)
        if esc_inv:
            warn(f'{len(esc_inv)} indicadores com alfabetização inválida (0 ou >100%)')
        urb_inc = bad(lambda i: i.populacao and (i.populacao_urbana + i.populacao_rural) > 0
                      and abs((i.populacao_urbana + i.populacao_rural) - i.populacao) / i.populacao > 0.20)
        if urb_inc:
            warn(f'{len(urb_inc)} indicadores com urbana+rural divergindo >20% da população')

        # ── Campos zerados em massa ──
        zerados = {}
        for campo in ['pib', 'renda_per_capita', 'familias_bolsa_familia', 'meis_ativos',
                      'populacao_urbana', 'populacao_rural', 'idosos_60_mais', 'jovens_18_29',
                      'anos_estudo_medio']:
            z = sum(1 for i in inds if not getattr(i, campo))
            zerados[campo] = z
            if inds and z == len(inds):
                crit(f'campo {campo} zerado em TODAS as cidades')
            elif inds and z > len(inds) * 0.3:
                warn(f'campo {campo} zerado em {z}/{len(inds)} cidades')
        report['metricas']['zerados'] = zerados

        # ── Indicadores sintéticos (correlação com PIB per capita) ──
        com_pop = [i for i in inds if i.populacao and i.pib]
        sinteticos = {}
        if len(com_pop) >= 10:
            pibpc = [float(i.pib) * 1000 / i.populacao for i in com_pop]
            campos_pct = {
                'renda_per_capita': [float(i.renda_per_capita) for i in com_pop],
                'bolsa_familia_pct': [i.familias_bolsa_familia / i.populacao for i in com_pop],
                'meis_pct': [i.meis_ativos / i.populacao for i in com_pop],
                'urbana_pct': [i.populacao_urbana / i.populacao for i in com_pop],
                'idosos_pct': [i.idosos_60_mais / i.populacao for i in com_pop],
                'jovens_pct': [i.jovens_18_29 / i.populacao for i in com_pop],
                'escolaridade': [float(i.anos_estudo_medio) for i in com_pop],
            }
            for k, v in campos_pct.items():
                r = round(_corr(pibpc, v), 3)
                sinteticos[k] = r
                if abs(r) >= 0.90:
                    warn(f'{k} é SINTÉTICO (r={r:+.3f} com PIB p/c) — não é sinal independente')
        report['metricas']['correlacao_pib'] = sinteticos

        # ── Saída ──
        if as_json:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self._print_human(report, len(cidades), len(inds), sem_ind, dup, anos, zerados, sinteticos)

        report['ok'] = not report['criticos']
        if report['criticos']:
            self.stderr.write(self.style.ERROR(
                f"\n❌ AUDITORIA: {len(report['criticos'])} problema(s) CRÍTICO(s), "
                f"{len(report['avisos'])} aviso(s)."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ AUDITORIA: sem problemas críticos ({len(report['avisos'])} aviso(s))."))

    def _print_human(self, report, ncid, nind, sem_ind, dup, anos, zerados, sinteticos):
        w = self.stdout.write
        bar = '=' * 64
        w(bar); w('AUDITORIA DE INDICADORES'); w(bar)
        w(f'Cidades: {ncid} (SC tem {SC_MUNICIPIOS}) | Indicadores: {nind} | '
          f'sem indicador: {len(sem_ind)} | duplicados: {len(dup)} | anos: {anos}')

        if sinteticos:
            w('\n— Correlação de cada indicador com PIB per capita —')
            w('  (|r| >= 0.90 => o campo é só o PIB disfarçado, não um sinal novo)')
            for k, r in sinteticos.items():
                flag = '  ⚠ SINTÉTICO' if abs(r) >= 0.90 else ('  ~ derivado' if abs(r) >= 0.7 else '  ✓ independente')
                w(f'   {k:20} r = {r:+.3f}{flag}')

        if report['criticos']:
            w('\n🔴 CRÍTICOS:')
            for m in report['criticos']:
                w('   • ' + m)
        if report['avisos']:
            w('\n🟠 AVISOS:')
            for m in report['avisos']:
                w('   • ' + m)
        if report.get('notas'):
            w('\n🔵 NOTAS (esperado, não é erro):')
            for m in report['notas']:
                w('   • ' + m)
