"""Config de marca — DEMO (exemplo/template para as próximas marcas).

Marca fictícia para demonstrar a troca por env (MARCA=demo) e servir de
modelo ao criar configs/sorgatto.py e configs/gilson.py: masculina e com
cargo em disputa diferente (federal), cores próprias. Não usar em produção.
"""

CAMPANHA = {
    'CANDIDATO_NOME': 'João Demo',
    'CANDIDATO_PRIMEIRO_NOME': 'João',
    'CANDIDATO_ARTIGO': 'o',
    'PARTIDO_SIGLA': 'NOVO',
    'PARTIDO_NUMERO': '30',
    'UF': 'Santa Catarina',

    'CARGO_2026': 'Deputado Federal',
    'TSE_CARGO_2026': 'deputado_federal',

    'LIDERANCA_INLINE_EDIT': False,
    'DASHBOARD_VOTOS_PLANILHA': False,
    'TSE_TERMO_BUSCA': 'JOAO DEMO',
    'TSE_CARGO_BASE': 'deputado_federal',
    'TSE_CARGO_BASE_LABEL': 'Dep. Federal',
    'TSE_ANO_BASE': 2022,

    # Azul de propósito — troca de marca fica visível de longe.
    'CORES': {
        '--navy': '#1d4ed8',
        '--navy-700': '#1e40af',
        '--navy-900': '#1e293b',
        '--ouro': '#0e7490',
        '--ouro-strong': '#155e75',
        '--coral': '#7c3aed',
        '--teal': '#0d9488',
    },

    # Subconjunto curto de propósito — demonstra a lista enxuta de outra marca.
    'COLUNAS_LIDERANCA': [
        'nome', 'papel', 'telefone', 'cidade', 'regiao',
        'coordenador_responsavel', 'intencao_voto', 'ultima_interacao',
        'cadastrado_por', 'observacoes',
    ],
}
