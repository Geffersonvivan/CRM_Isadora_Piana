"""
Carrega todas as 21 regiões e ~295 cidades de Santa Catarina.
Regiões: fixture inline (FECAM).
Cidades: API IBGE + mapeamento oficial SAS/SC.
"""
import gzip
import json
import urllib.request
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from liderancas.models import Regiao, Cidade

REGIOES = [
    (1, "AMEOSC", "Associação dos Municípios do Extremo Oeste Catarinense"),
    (2, "AMERIOS", "Associação dos Municípios do Entre Rios"),
    (3, "AMNOROESTE", "Associação dos Municípios do Noroeste Catarinense"),
    (4, "AMOSC", "Associação dos Municípios do Oeste de Santa Catarina"),
    (5, "AMAI", "Associação dos Municípios do Alto Irani"),
    (6, "AMAUC", "Associação dos Municípios do Alto Uruguai Catarinense"),
    (7, "AMMOC", "Associação dos Municípios do Meio Oeste Catarinense"),
    (8, "AMARP", "Associação dos Municípios do Alto Vale do Rio do Peixe"),
    (9, "AMPLASC", "Associação dos Municípios do Planalto Sul de Santa Catarina"),
    (10, "AMURC", "Associação dos Municípios da Região do Contestado"),
    (11, "AMURES", "Associação dos Municípios da Região Serrana"),
    (12, "AMPLANORTE", "Associação dos Municípios do Planalto Norte Catarinense"),
    (13, "AMUNESC", "Associação dos Municípios do Nordeste de Santa Catarina"),
    (14, "AMVALI", "Associação dos Municípios do Vale do Itapocu"),
    (15, "AMAVI", "Associação dos Municípios do Alto Vale do Itajaí"),
    (16, "AMVE", "Associação dos Municípios do Vale Europeu"),
    (17, "AMFRI", "Associação dos Municípios da Foz do Rio Itajaí"),
    (18, "GRANFPOLIS", "Associação dos Municípios da Grande Florianópolis"),
    (19, "AMUREL", "Associação dos Municípios da Região de Laguna"),
    (20, "AMREC", "Associação dos Municípios da Região Carbonífera"),
    (21, "AMESC", "Associação dos Municípios do Extremo Sul Catarinense"),
]

# Mapeamento IBGE code -> sigla da região (fonte: SAS/SC)
CITY_REGION_MAP = {
    # AMAI (14)
    "4200101": "AMAI", "4202537": "AMAI", "4205175": "AMAI", "4205308": "AMAI",
    "4207684": "AMAI", "4209458": "AMAI", "4210555": "AMAI", "4211850": "AMAI",
    "4212270": "AMAI", "4213401": "AMAI", "4216107": "AMAI", "4219101": "AMAI",
    "4219507": "AMAI", "4219705": "AMAI",
    # AMARP (15)
    "4201604": "AMARP", "4203006": "AMARP", "4203154": "AMARP", "4205506": "AMARP",
    "4206751": "AMARP", "4207577": "AMARP", "4209706": "AMARP", "4210050": "AMARP",
    "4210704": "AMARP", "4213005": "AMARP", "4214409": "AMARP", "4215406": "AMARP",
    "4217907": "AMARP", "4218251": "AMARP", "4219309": "AMARP",
    # AMAUC (14)
    "4200754": "AMAUC", "4201273": "AMAUC", "4204301": "AMAUC", "4207601": "AMAUC",
    "4207700": "AMAUC", "4207809": "AMAUC", "4208005": "AMAUC", "4208609": "AMAUC",
    "4209854": "AMAUC", "4212601": "AMAUC", "4213104": "AMAUC", "4213906": "AMAUC",
    "4217501": "AMAUC", "4219606": "AMAUC",
    # AMAVI (28)
    "4200200": "AMAVI", "4200309": "AMAVI", "4201802": "AMAVI", "4201901": "AMAVI",
    "4202859": "AMAVI", "4204194": "AMAVI", "4205100": "AMAVI", "4206900": "AMAVI",
    "4207403": "AMAVI", "4208500": "AMAVI", "4209151": "AMAVI", "4209508": "AMAVI",
    "4209904": "AMAVI", "4210852": "AMAVI", "4212700": "AMAVI", "4213708": "AMAVI",
    "4214003": "AMAVI", "4214102": "AMAVI", "4214508": "AMAVI", "4214607": "AMAVI",
    "4214805": "AMAVI", "4215307": "AMAVI", "4215679": "AMAVI", "4217808": "AMAVI",
    "4218608": "AMAVI", "4219200": "AMAVI", "4219358": "AMAVI", "4219408": "AMAVI",
    # AMEOSC (19)
    "4200804": "AMEOSC", "4202081": "AMEOSC", "4202099": "AMEOSC", "4202156": "AMEOSC",
    "4204905": "AMEOSC", "4205001": "AMEOSC", "4206405": "AMEOSC", "4206603": "AMEOSC",
    "4207650": "AMEOSC", "4208401": "AMEOSC", "4211009": "AMEOSC", "4212007": "AMEOSC",
    "4212239": "AMEOSC", "4214151": "AMEOSC", "4215554": "AMEOSC", "4216255": "AMEOSC",
    "4216701": "AMEOSC", "4217204": "AMEOSC", "4218756": "AMEOSC",
    # AMERIOS (17)
    "4202578": "AMERIOS", "4203105": "AMERIOS", "4203501": "AMERIOS", "4204707": "AMERIOS",
    "4204756": "AMERIOS", "4205357": "AMERIOS", "4207759": "AMERIOS", "4210506": "AMERIOS",
    "4210902": "AMERIOS", "4212106": "AMERIOS", "4215075": "AMERIOS", "4215208": "AMERIOS",
    "4215356": "AMERIOS", "4215687": "AMERIOS", "4217154": "AMERIOS", "4217303": "AMERIOS",
    "4217956": "AMERIOS",
    # AMESC (15)
    "4201406": "AMESC", "4201950": "AMESC", "4202073": "AMESC", "4205191": "AMESC",
    "4208708": "AMESC", "4210407": "AMESC", "4210803": "AMESC", "4211256": "AMESC",
    "4212254": "AMESC", "4213807": "AMESC", "4215653": "AMESC", "4216404": "AMESC",
    "4217709": "AMESC", "4218103": "AMESC", "4218806": "AMESC",
    # AMFRI (11)
    "4202008": "AMFRI", "4202453": "AMFRI", "4203204": "AMFRI", "4207106": "AMFRI",
    "4208203": "AMFRI", "4208302": "AMFRI", "4210001": "AMFRI", "4211306": "AMFRI",
    "4212502": "AMFRI", "4212809": "AMFRI", "4213500": "AMFRI",
    # AMMOC (12)
    "4200408": "AMMOC", "4203907": "AMMOC", "4204004": "AMMOC", "4205209": "AMMOC",
    "4206702": "AMMOC", "4206801": "AMMOC", "4209003": "AMMOC", "4209201": "AMMOC",
    "4210035": "AMMOC", "4211801": "AMMOC", "4218509": "AMMOC", "4219176": "AMMOC",
    # AMNOROESTE (8)
    "4204459": "AMNOROESTE", "4205605": "AMNOROESTE", "4207858": "AMNOROESTE",
    "4209177": "AMNOROESTE", "4211652": "AMNOROESTE", "4214201": "AMNOROESTE",
    "4215752": "AMNOROESTE", "4216909": "AMNOROESTE",
    # AMOSC (20)
    "4200507": "AMOSC", "4200556": "AMOSC", "4201653": "AMOSC", "4204103": "AMOSC",
    "4204202": "AMOSC", "4204350": "AMOSC", "4204400": "AMOSC", "4205431": "AMOSC",
    "4206652": "AMOSC", "4208955": "AMOSC", "4211405": "AMOSC", "4211454": "AMOSC",
    "4211876": "AMOSC", "4212908": "AMOSC", "4213153": "AMOSC", "4215695": "AMOSC",
    "4216008": "AMOSC", "4217550": "AMOSC", "4217758": "AMOSC", "4218855": "AMOSC",
    # AMPLANORTE (10)
    "4202131": "AMPLANORTE", "4203808": "AMPLANORTE", "4207908": "AMPLANORTE",
    "4208104": "AMPLANORTE", "4210100": "AMPLANORTE", "4210308": "AMPLANORTE",
    "4211108": "AMPLANORTE", "4212205": "AMPLANORTE", "4213609": "AMPLANORTE",
    "4218301": "AMPLANORTE",
    # AMPLASC (7)
    "4200051": "AMPLASC", "4202875": "AMPLASC", "4203600": "AMPLASC", "4204152": "AMPLASC",
    "4211058": "AMPLASC", "4219150": "AMPLASC", "4219853": "AMPLASC",
    # AMREC (12)
    "4204251": "AMREC", "4204608": "AMREC", "4205456": "AMREC", "4207007": "AMREC",
    "4209607": "AMREC", "4211207": "AMREC", "4211603": "AMREC", "4211702": "AMREC",
    "4217600": "AMREC", "4218350": "AMREC", "4219002": "AMREC", "4220000": "AMREC",
    # AMUNESC (9)
    "4201307": "AMUNESC", "4202057": "AMUNESC", "4203303": "AMUNESC", "4205803": "AMUNESC",
    "4208450": "AMUNESC", "4209102": "AMUNESC", "4215000": "AMUNESC", "4215802": "AMUNESC",
    "4216206": "AMUNESC",
    # AMURC (5)
    "4204806": "AMURC", "4205555": "AMURC", "4213351": "AMURC", "4215505": "AMURC",
    "4216057": "AMURC",
    # AMUREL (18)
    "4201505": "AMUREL", "4202800": "AMUREL", "4203956": "AMUREL", "4206108": "AMUREL",
    "4206207": "AMUREL", "4207205": "AMUREL", "4207304": "AMUREL", "4208807": "AMUREL",
    "4209409": "AMUREL", "4212403": "AMUREL", "4212650": "AMUREL", "4214904": "AMUREL",
    "4215455": "AMUREL", "4215604": "AMUREL", "4217006": "AMUREL", "4217105": "AMUREL",
    "4218400": "AMUREL", "4218707": "AMUREL",
    # AMURES (18)
    "4201000": "AMURES", "4202438": "AMURES", "4202503": "AMURES", "4202602": "AMURES",
    "4203253": "AMURES", "4203402": "AMURES", "4204178": "AMURES", "4204558": "AMURES",
    "4209300": "AMURES", "4211751": "AMURES", "4211892": "AMURES", "4212056": "AMURES",
    "4213302": "AMURES", "4215059": "AMURES", "4216503": "AMURES", "4216800": "AMURES",
    "4218905": "AMURES", "4218954": "AMURES",
    # AMVALI (7)
    "4202107": "AMVALI", "4204509": "AMVALI", "4206504": "AMVALI", "4208906": "AMVALI",
    "4210605": "AMVALI", "4216354": "AMVALI", "4217402": "AMVALI",
    # AMVE (14)
    "4201257": "AMVE", "4201703": "AMVE", "4202206": "AMVE", "4202404": "AMVE",
    "4202701": "AMVE", "4202909": "AMVE", "4205159": "AMVE", "4205902": "AMVE",
    "4206306": "AMVE", "4207502": "AMVE", "4213203": "AMVE", "4214706": "AMVE",
    "4215109": "AMVE", "4218202": "AMVE",
    # GRANFPOLIS (22)
    "4200606": "GRANFPOLIS", "4200705": "GRANFPOLIS", "4200903": "GRANFPOLIS",
    "4201109": "GRANFPOLIS", "4201208": "GRANFPOLIS", "4202305": "GRANFPOLIS",
    "4203709": "GRANFPOLIS", "4205407": "GRANFPOLIS", "4205704": "GRANFPOLIS",
    "4206009": "GRANFPOLIS", "4209805": "GRANFPOLIS", "4210209": "GRANFPOLIS",
    "4211504": "GRANFPOLIS", "4211900": "GRANFPOLIS", "4212304": "GRANFPOLIS",
    "4214300": "GRANFPOLIS", "4215703": "GRANFPOLIS", "4215901": "GRANFPOLIS",
    "4216305": "GRANFPOLIS", "4216602": "GRANFPOLIS", "4217253": "GRANFPOLIS",
    "4218004": "GRANFPOLIS",
}


class Command(BaseCommand):
    help = 'Carrega as 21 regiões e todas as cidades de SC (IBGE + SAS/SC)'

    def handle(self, *args, **options):
        # 1. Criar/atualizar regiões
        regioes_map = {}
        for pk, sigla, nome in REGIOES:
            regiao, created = Regiao.objects.update_or_create(
                sigla=sigla,
                defaults={
                    'nome': nome,
                    'nome_completo': nome,
                    'slug': slugify(sigla),
                },
            )
            regioes_map[sigla] = regiao
            status = 'criada' if created else 'atualizada'
            self.stdout.write(f'  Região {sigla} {status}')

        self.stdout.write(self.style.SUCCESS(f'{len(regioes_map)} regiões processadas'))

        # 2. Buscar cidades do IBGE
        url = 'https://servicodados.ibge.gov.br/api/v1/localidades/estados/42/municipios'
        self.stdout.write('Buscando municípios de SC do IBGE...')

        try:
            req = urllib.request.Request(url, headers={
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip',
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                try:
                    data = raw.decode('utf-8')
                except UnicodeDecodeError:
                    data = gzip.decompress(raw).decode('utf-8')
                cities_data = json.loads(data)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Erro ao acessar IBGE API: {e}'))
            return

        created_count = 0
        updated_count = 0
        skipped = []

        for city_data in cities_data:
            ibge_code = str(city_data['id'])
            nome = city_data['nome']

            sigla_regiao = CITY_REGION_MAP.get(ibge_code)
            if not sigla_regiao or sigla_regiao not in regioes_map:
                skipped.append(f'{nome} ({ibge_code})')
                continue

            slug = slugify(nome)
            regiao = regioes_map[sigla_regiao]

            # Tenta buscar por codigo_ibge primeiro, depois por nome+regiao
            cidade = Cidade.objects.filter(codigo_ibge=ibge_code).first()
            if not cidade:
                cidade = Cidade.objects.filter(nome=nome, regiao=regiao).first()
            if not cidade:
                # Busca por nome em qualquer região (pode ter sido importada com região errada)
                cidade = Cidade.objects.filter(nome=nome).first()

            if cidade:
                cidade.codigo_ibge = ibge_code
                cidade.regiao = regiao
                if not cidade.slug:
                    cidade.slug = slug
                cidade.save(update_fields=['codigo_ibge', 'regiao', 'slug'])
                updated_count += 1
            else:
                Cidade.objects.create(
                    nome=nome,
                    regiao=regiao,
                    codigo_ibge=ibge_code,
                    slug=slug,
                )
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Concluído: {created_count} cidades criadas, {updated_count} atualizadas'
        ))
        if skipped:
            self.stdout.write(self.style.WARNING(
                f'{len(skipped)} sem região mapeada: {", ".join(skipped)}'
            ))
