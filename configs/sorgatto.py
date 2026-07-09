"""Config de marca — Sorgatto (PL), Deputado Estadual · SC 2026.

Caso de cargo cruzado: base histórica de 2022 como deputado FEDERAL,
disputa de 2026 como deputado ESTADUAL — o mapa e o ranking de ameaça
lidam com isso via TSE_CARGO_BASE ≠ TSE_CARGO_2026 (Fase 2 passo 3).

Nome de urna confirmado nos dados do TSE 2022 ('SORGATTO', dep. federal) e
nome completo no branding da produção anterior. A CONFIRMAR: paleta oficial
da campanha (abaixo, azul/amarelo institucionais do PL).
"""

CAMPANHA = {
    'CANDIDATO_NOME': 'Leandro Sorgatto',
    'CANDIDATO_PRIMEIRO_NOME': 'Sorgatto',
    'CANDIDATO_ARTIGO': 'o',
    'PARTIDO_SIGLA': 'PL',
    'PARTIDO_NUMERO': '22',
    'UF': 'Santa Catarina',

    # Cargo em disputa em 2026
    'CARGO_2026': 'Deputado Estadual',
    'TSE_CARGO_2026': 'deputado_estadual',

    # Base eleitoral de referência (2022 — candidato a federal)
    'TSE_TERMO_BUSCA': 'SORGATTO',
    'TSE_CARGO_BASE': 'deputado_federal',
    'TSE_CARGO_BASE_LABEL': 'Dep. Federal',
    'TSE_ANO_BASE': 2022,

    # Paleta PL (azul + amarelo) — ajustar com a identidade oficial da campanha.
    # Lista de Lideranças editável inline: exclusiva da Isadora por ora.
    'LIDERANCA_INLINE_EDIT': False,
    'DASHBOARD_VOTOS_PLANILHA': False,

    'CORES': {
        '--navy': '#1e40af',        # azul PL (marca)
        '--navy-700': '#1e3a8a',
        '--navy-900': '#1f2937',    # grafite — superfície escura
        '--ouro': '#d97706',        # amarelo PL (assinatura, com moderação)
        '--ouro-strong': '#b45309',
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
