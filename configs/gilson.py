"""Config de marca — Gilson Marques (NOVO), Deputado Federal · SC 2026.

Base 2022 e disputa 2026 no MESMO cargo (federal): o ranking de ameaça
pondera rivais a federal excluindo o próprio candidato (is_candidato).

A CONFIRMAR com a campanha: nome de urna exato no TSE 2022.
"""

CAMPANHA = {
    'CANDIDATO_NOME': 'Gilson Marques',
    'CANDIDATO_PRIMEIRO_NOME': 'Gilson',
    'CANDIDATO_ARTIGO': 'o',
    'PARTIDO_SIGLA': 'NOVO',
    'PARTIDO_NUMERO': '30',
    'UF': 'Santa Catarina',

    # Cargo em disputa em 2026
    'CARGO_2026': 'Deputado Federal',
    'TSE_CARGO_2026': 'deputado_federal',

    # Base eleitoral de referência (2022 — candidato a federal)
    'TSE_TERMO_BUSCA': 'GILSON MARQUES',
    'TSE_CARGO_BASE': 'deputado_federal',
    'TSE_CARGO_BASE_LABEL': 'Dep. Federal',
    'TSE_ANO_BASE': 2022,

    # Paleta NOVO — a mesma da Isadora.
    # Lista de Lideranças editável inline: exclusiva da Isadora por ora.
    'LIDERANCA_INLINE_EDIT': False,
    'DASHBOARD_VOTOS_PLANILHA': False,
    'PWA_CADASTRO_CONTATO': False,
    'MAPA_NIVEIS_IBGE': False,

    'CORES': {
        '--navy': '#FF6B00',        # laranja NOVO (marca)
        '--navy-700': '#E25E00',
        '--navy-900': '#2B2B2B',    # grafite — superfície escura
        '--ouro': '#C44B00',        # assinatura (fio/chip/realce, com moderação)
        '--ouro-strong': '#A33D00',
        '--coral': '#7c3aed',       # vertical Mobilização
        '--teal': '#0d9488',        # vertical Tarefas
    },

    # Colunas da lista de Lideranças — conjunto clássico (sem as colunas da
    # planilha central da Isadora). Ajustar quando a campanha definir as dela.
    'COLUNAS_LIDERANCA': [
        'nome', 'papel', 'telefone', 'email', 'instagram', 'cidade', 'regiao',
        'coordenador_responsavel', 'tipo', 'prioridade', 'intencao_voto',
        'frequencia_relacionamento', 'votos_referencia', 'ultima_interacao',
        'cadastrado_por', 'observacoes',
    ],
}
