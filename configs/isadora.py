"""Config de marca — Isadora Piana (NOVO/30), Deputada Estadual · SC 2026.

Tudo que difere entre marcas e NÃO é segredo vive aqui (D10). O código lê
settings.CAMPANHA (ou o context processor `campanha` nos templates); nenhum
nome, número ou cargo pode ficar hardcodado fora deste arquivo.
"""

CAMPANHA = {
    'CANDIDATO_NOME': 'Isadora Piana',
    'CANDIDATO_PRIMEIRO_NOME': 'Isadora',
    # Artigo definido do candidato ('a'|'o') — o context processor deriva as
    # formas prontas para texto corrido: "a Isadora", "da Isadora", "à Isadora".
    'CANDIDATO_ARTIGO': 'a',
    'PARTIDO_SIGLA': 'NOVO',
    'PARTIDO_NUMERO': '30',
    'UF': 'Santa Catarina',

    # Cargo em disputa em 2026: rótulo humano e valor de máquina (chaves do
    # TSE usadas nos filtros do mapa — concorrência, ranking de ameaça).
    'CARGO_2026': 'Deputada Estadual',
    'TSE_CARGO_2026': 'deputado_estadual',

    # Base eleitoral de referência no mapa (votação do candidato em eleição
    # anterior). Pode divergir do cargo em disputa (ex.: federal→estadual).
    'TSE_TERMO_BUSCA': 'ISADORA',
    'TSE_CARGO_BASE': 'deputado_estadual',
    'TSE_CARGO_BASE_LABEL': 'Dep. Estadual',   # rótulo humano da base (§5.3: rótulo = conteúdo)
    'TSE_ANO_BASE': 2022,

    # Lista de Lideranças editável célula a célula, no estilo da planilha central
    # (Voto/Nível/Canal/Atendente com dropdown colorido + checkboxes inline).
    # Só a Isadora usa este layout; as outras marcas seguem a lista padrão.
    'LIDERANCA_INLINE_EDIT': True,

    # Dashboard "Meta de Votos" no modelo da planilha (intenção de voto, funil de
    # vaquinha/doação, ranking por atendente) em vez do modelo de rede
    # (coordenador→cabo→replicador). Só a Isadora usa a base da planilha central.
    'DASHBOARD_VOTOS_PLANILHA': True,

    # Ao logar, entra direto na Dashboard (Meta de Votos), sem passar pela capa
    # de campanha. As outras marcas mantêm a capa em '/'.
    'LOGIN_REDIRECT_URL': '/dashboard/meta-votos/',
    # Capa de campanha desativada: a raiz '/' também vai direto para a Dashboard.
    'CAPA_ATIVA': False,

    # Cadastro de campo (PWA) no modelo da planilha: "Novo Contato" com Categoria =
    # nível (Contato/Eleitor/Multiplicador/Voluntário) + "Vota {candidato}?".
    # As outras marcas mantêm o "Novo Apoiador" com as categorias de tipo.
    'PWA_CADASTRO_CONTATO': True,

    # Cores da marca — valores das variáveis CSS históricas (--navy/--ouro/
    # --coral guardam a paleta atual; usar sempre a variável, não hex avulso).
    # Injetadas no :root pelo base.html; global.css traz o fallback.
    'CORES': {
        '--navy': '#FF6B00',        # laranja NOVO (marca)
        '--navy-700': '#E25E00',
        '--navy-900': '#2B2B2B',    # grafite — superfície escura
        '--ouro': '#C44B00',        # assinatura (fio/chip/realce, com moderação)
        '--ouro-strong': '#A33D00',
        '--coral': '#7c3aed',       # vertical Mobilização
        '--teal': '#0d9488',        # vertical Tarefas
    },

    # Colunas da lista de Lideranças, na ordem de exibição (Fase 2). O model
    # guarda o superset; cada marca lista aqui o que mostra. A Isadora exibe
    # tudo. Chaves = campos do model (+ 'ultima_interacao', annotation da view);
    # seleção e ações são estruturais e ficam fora da lista.
    # Espelha o cabeçalho da "BASE DA ESTRUTURA" da PLANILHA CENTRAL ISA (linha 3),
    # na mesma ordem. A coluna "Class" (nº de sequência da planilha) não vira coluna;
    # "HISTÓRICO DO ATENDIMENTO" é a annotation `ultima_interacao` (via InteracaoLog).
    'COLUNAS_LIDERANCA': [
        'atendente',          # ATENDENTE
        'intencao_voto',      # VOTO
        'nivel',              # NÍVEL
        'nome',               # NOME
        'cidade',             # CIDADE
        'uf',                 # UF
        'contato_feito',      # Contato Feito?
        'data_contato',       # DATA CONTATO
        'canal_atendimento',  # CANAL DO ÚLTIMO ATENDIMENTO
        'telefone',           # TELEFONE
        'vaquinha_enviada',   # Já mandou link da VAQUINHA?
        'doou',               # DOOU?
        'observacoes',        # OBSERVAÇÕES GERAIS
        'filiado_partido',    # FILIADO A ALGUM PARTIDO?
        'quem_e_eleitor',     # QUEM É O ELEITOR?
        'origem_contato',     # COMO CHEGOU?
        'instagram',          # INSTAGRAM
        'facebook',           # FACEBOOK
        'email',              # E-MAIL
        'endereco',           # ENDEREÇO (PRA ENTREGA DE MATERIAL)
        'material_entregue',  # MATERIAL ENTREGUE?
        'idade',              # IDADE
        'segmentos',          # SEGMENTOS/INTERESSES
        'ultima_interacao',   # HISTÓRICO DO ATENDIMENTO (InteracaoLog)
    ],
}
