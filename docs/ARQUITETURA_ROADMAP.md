# Arquitetura & Roadmap — CRM Base Eleitoral

> **Produto:** CRM Base Eleitoral — um CRM de mandato/campanha política (rede de apoio +
> inteligência territorial), hoje rodando 3 marcas (Isadora, Sorgatto, Gilson) e destinado
> a virar SaaS multi-tenant.
>
> Fonte da verdade das **decisões** de arquitetura e do **passo a passo** para sair de
> "3 CRMs em pastas separadas" para "1 código + config por marca" e, no futuro, um
> produto SaaS multi-tenant. Documento interno (você + Claude). Formato: registro de
> decisões (o *porquê*) com roadmap por fases.
>
> Última atualização: 2026-07-03 · Branch de trabalho: `rebranding-isadora`

---

## 1. Contexto & problema

Hoje existem **três CRMs** que são, na prática, o **mesmo software** com marca e dados
diferentes:

| Marca | Candidato | 2022 (base histórica) | 2026 (disputa) |
|-------|-----------|------------------------|-----------------|
| Isadora Piana | Isadora | Deputada Estadual (SC) | Deputada Estadual (SC) |
| Sorgatto | Sorgatto | Deputado **Federal** | Deputado **Estadual** |
| Gilson Marques | Gilson | Deputado Federal | Deputado Federal |

Todos partido **NOVO (30)**, SC, eleição 2026 (1º turno 04/10/2026).

**O problema:** cada um vive numa pasta/repositório separado. Toda melhoria (agenda,
mapa, moderação, PWA) precisa ser **copiada à mão** para as outras duas. Isso gera
*drift*: as bases divergem, um recebe correção que o outro não recebe, e o custo de
manter cresce a cada feature. Já aconteceu nesta sessão (a agenda do Sorgatto tinha
mudanças que a da Isadora não tinha, e vice-versa).

**Por que não resolver "criando um repo/servidor por cliente":** essa é a rota que não
escala. Funciona para 3, é inviável para 30. Cada cliente novo viraria um fork manual —
o mesmo problema de drift, multiplicado, mais custo de infra linear por cliente.

**A visão:** depois dos 3 eleitos, transformar isto num **CRM de mandato político**
vendido para outros políticos. Um produto, não três forks. Este documento traça o
caminho: primeiro **unificar** (deixar de copiar código à mão), depois **produtizar**
(um deploy servindo muitos clientes com isolamento de dados).

## 2. Princípios de arquitetura

A regra de ouro que decide **cada** dúvida de "onde isso mora":

> **Comportamento é código. Marca é config. Config, no futuro, vira dado.**

Detalhando:

1. **Se é *como* o sistema se comporta → código compartilhado.** Regras de moderação,
   cálculo de placar, score do mapa, sync do PWA, permissão por seção. Isso é *igual*
   para todos os candidatos e nunca deve ser duplicado. (Reforça o CLAUDE.md §4: regra
   de negócio em serviço reutilizável, não copiada entre views/marcas.)

2. **Se é *o que* aquela campanha mostra → config de marca.** Nome do candidato, cores,
   logo, cargo em disputa, termo de busca no TSE, quais colunas de Lideranças aparecem.
   Isso muda por marca **sem tocar em código**.

3. **A config evolui de lugar, não de natureza.** Hoje mora em variáveis de ambiente
   (`settings.CAMPANHA`, lido de `os.environ`). No SaaS, mora numa **linha de tabela**
   (model `Mandato`/tenant no banco). O *mesmo conjunto de chaves* — só muda a fonte:
   `env` → `banco`. Desenhar a config hoje já pensando nessa migração evita retrabalho.

4. **Diferença de conteúdo ≠ diferença de comportamento.** O caso das colunas de
   Lideranças é o exemplo canônico: Isadora tem mais colunas que o Sorgatto, mas as
   duas listas **se comportam igual** (ordenam, paginam, filtram do mesmo jeito). A
   diferença é *quais colunas existem* (config), não *como a lista funciona* (código).
   Nunca fork de comportamento para acomodar diferença de conteúdo.

5. **Dado do mapa é sagrado e vem da fonte, por marca.** O mapa já é ~95%
   config-driven (`TSE_CARGO_BASE`, `TSE_TERMO_BUSCA`). Cada marca aponta para o cargo
   e o candidato certos; o *código* que lê TSE/IBGE é o mesmo. Mantém o CLAUDE.md §5:
   dado real, nunca sintético; rótulo = conteúdo.

## 3. Estado atual (snapshot honesto)

**O que já está pronto para unificar (bom):**

- **`settings.CAMPANHA`** já existe (`crm/settings.py`), lido de `os.environ`.
  Chaves atuais: `CANDIDATO_NOME`, `CARGO_2026` (rótulo), `TSE_TERMO_BUSCA` (`ISADORA`),
  `TSE_CARGO_BASE` (`deputado_estadual`), `TSE_ANO_BASE` (2022). É o embrião da config
  de marca — a estrutura certa já está no lugar.
- **Mapa é ~95% config-driven.** `mapa/views.py` e `import_tse.py` usam
  `settings.CAMPANHA['TSE_CARGO_BASE']` e `['TSE_TERMO_BUSCA']`. `import_tse` já importa
  **todos** os cargos, e denormaliza `Cidade.votos_referencia_2022` a partir do cargo
  base configurado. Trocar de marca no mapa é, quase todo, trocar env.
- **Config de marca já exposta ao front** via `core/context_processors.py` (`campanha`).

**O que ainda falta / diverge (as pontas soltas):**

- **1 hardcode de cargo no front:** `templates/mapa/index.html` (~linha 1030) filtra
  `c.cargo === 'deputado_estadual'` fixo. Para o Gilson/Sorgatto (cargos diferentes em
  2026), isso quebra. Falta uma chave **`TSE_CARGO_2026`** (valor de máquina, ex.
  `deputado_federal`) na config, e trocar o hardcode por ela. É o *único* buraco
  conhecido que impede o mapa de ser 100% config-driven.
- **Colunas de Lideranças divergem** entre marcas (Isadora tem os 16 campos da planilha
  central; Sorgatto tem menos). Hoje isso seria fork de template — precisa virar config
  (lista de colunas por marca). Ver Fase 2.
- **Nome do módulo Django** ✅ já neutralizado: `crm_isadora/` → `crm/` (feito). Falta
  ainda renomear a **pasta-raiz** `CRM_Isadora_Piana` → `CRM_Base_Eleitoral` (passo manual,
  `mv` do diretório). Ver Fase 1.
- **Três repositórios/pastas** separados, sem ancestral comum vivo (só o commit base
  `fdd9ee4`). A unificação precisa escolher uma base e reconvergir.

**Estado do trabalho desta sessão (importante):**

- Tudo está **local e não commitado** na branch `rebranding-isadora`. Produção
  (Railway) **intocada**. Mudanças prontas mas não versionadas: EventoAnexo (anexos na
  agenda), visão-semana do calendário, remoção do painel "Estratégia da semana",
  cabeçalho da agenda em uma linha, os 16 campos da planilha em Lideranças, redesenho da
  tela de permissões, correções do mapa (explicador sempre presente, card "1,2%"
  reescrito). **Fase 0 existe justamente para versionar isso antes de mexer em estrutura.**

## 4. Roadmap por fases

Cada fase tem **objetivo · passos · como · pronto quando**. As fases são sequenciais:
não começar a Fase N+1 com a N pela metade (evita instabilidade em base de campanha em
uso). Fases 0 e 1 são "agora"; 2 é "logo em seguida"; 3 é "depois dos 3 eleitos".

### Fase 0 — Higiene (pré-requisito imediato) ✅ concluída em 04/07/2026

> Feita na `rebranding-isadora`: 15 commits temáticos (higiene → rename do módulo →
> remoção de Doações → unificação de Lideranças → PWA → Agenda → Usuários → Tarefas →
> Notificações → Mapa → Home/capa → Oportunidades → identidade CAMPANHA → docs).
> `git status` limpo, `manage.py check` e `makemigrations --check` sem pendências,
> planilha com PII e patch de sessão no `.gitignore`.

**Objetivo:** transformar o trabalho local não commitado em histórico versionado e
seguro, sem tocar em produção. Nada de refatorar antes de ter rede de segurança.

**Passos:**
1. Revisar o `git status` e agrupar as mudanças por tema.
2. Commitar em **commits atômicos** separando dois eixos:
   - **Rebranding** (Sorgatto → Isadora: rename de módulo, strings, assets).
   - **Feature** (agenda/anexos, planilha em Lideranças, permissões, mapa) — um commit
     coeso por feature, mensagem em pt-BR no padrão do repo.
3. Garantir **um único** `runserver` rodando (a origem do falso "login→logoff" foram
   processos zumbi antigos servindo código velho). Matar os demais.
4. **Não** commitar `.env`/backups de `.env` (CLAUDE.md §9.1); conferir `.gitignore`.

**Como:** trabalhar na `rebranding-isadora`; commits pequenos e citáveis. Não fazer
push para produção ainda — só consolidar histórico local/branch.

**Pronto quando:** `git status` limpo, histórico atômico legível, um servidor só,
nenhum segredo versionado.

---


### Fase 1 — Unificar: 1 código + config de marca (env)

**Objetivo:** um único código-fonte que roda como qualquer uma das 3 marcas trocando
**só variáveis de ambiente**. Fim da cópia manual de feature entre pastas.

**Passos:**
1. **Escolher a base:** Isadora (é o superset — tem mais features e mais colunas). As
   outras marcas passam a ser *deltas de config* sobre ela, não forks de código.
2. **Renomear para o produto (D9):** ✅ módulo Django `crm_isadora/` → **`crm/`** feito
   (`DJANGO_SETTINGS_MODULE`, `wsgi/asgi`, `manage.py`, `Procfile`, `.claude/settings.local.json`
   ajustados; `manage.py check` limpo). ⬜ Falta a pasta-raiz `CRM_Isadora_Piana` →
   `CRM_Base_Eleitoral` (passo manual `mv`, feito fora da sessão — muda o cwd).
3. ✅ **Consolidar a config de marca** num arquivo **versionado** `configs/<slug>.py` (D10),
   carregado pelo `settings.py` conforme `MARCA=<slug>` e exposto como `settings.CAMPANHA`.
   Cobre tudo que difere e **não é segredo**: `CANDIDATO_NOME`, `PARTIDO`/`NUMERO`/`UF`
   (hoje NOVO/30/SC para os 3, mas viram config porque num SaaS variam por cliente),
   `CARGO_2026` (rótulo humano), **`TSE_CARGO_2026`** (valor de máquina — chave nova),
   `TSE_CARGO_BASE`, `TSE_TERMO_BUSCA`, `TSE_ANO_BASE`, cores da marca, e
   `COLUNAS_LIDERANCA` (lista ordenada — detalhada na Fase 2).
   - **Por que arquivo versionado e não `.env`:** config de marca **não é segredo** — no
     git ela fica revisável e sem drift. Como é `.py`, listas/mapas (colunas, cores) são
     nativos, sem JSON-em-string. Segredo (chave, banco, API) continua **só em env**.
   - **Assets (logo/imagens):** versionados sob `static/marca/<slug>/`; a config guarda só
     o `slug` e o código monta o caminho. Mesmo código serve qualquer marca.
4. ✅ **Fechar o buraco do mapa:** trocado o hardcode `deputado_estadual` em
   `templates/mapa/index.html` por `TSE_CARGO_2026` vindo do context processor.
   ✅ Varridas as ~117 strings de marca hardcoded em templates/JS (04/07/2026):
   templates usam o context processor (formas com artigo via `CANDIDATO_ARTIGO`),
   `sc-map.js` recebe `window.CAMPANHA`, manifest do PWA injetado pela view.
   ⚠️ O lado **servidor** da concorrência (`CandidatosAPI` em `mapa/views.py`, overlap
   ponderado fixo em estadual) fica para a Fase 2 passo 3 (cargo cruzado).
5. **Env de cada deploy carrega só o essencial não-versionado:** `MARCA=<slug>` (seletor
   da config) + os **segredos** (`SECRET_KEY`, `DATABASE_URL`, chaves de API). Nada de
   config de marca no env — ela vem de `configs/<slug>.py`.
6. **Deploy:** 3 serviços no Railway apontando para o **mesmo repositório** (um `origin`),
   cada um com sua `MARCA`, seus segredos e seu Postgres. Por padrão todos seguem `main`
   (push uma vez → os 3 sobem, drift-free). Mesma imagem, marcas diferentes.

**Como:** manter o comportamento idêntico ao de hoje — esta fase **não** muda regra de
negócio, só remove o acoplamento marca↔código. Validar cada marca subindo local com o
`.env` dela e conferindo nome, cores, cargo do mapa e colunas. Além do smoke-test manual,
cobrir com **teste automatizado** o que o CLAUDE.md §13 já exige (moderação, permissão,
idempotência do sync, integridade do mapa) rodando sob a config de pelo menos duas marcas
— assim a troca de marca não pode regredir comportamento em silêncio.

**Decisões desta fase** (resolvidas — ver Seção 5): módulo neutro **`crm/`** (D9);
**monorepo único** com config de marca versionada em `configs/<slug>.py` selecionada por
`MARCA=<slug>`, segredo em env (D10).

**Pronto quando:** subir as 3 marcas a partir do mesmo checkout trocando só o `.env`;
mapa correto para os 3 cargos; zero string de marca hardcoded no código.

**Sobre git nesta fase:** monorepo único, um `origin`; as 3 marcas são serviços Railway
do mesmo repo. Detalhado na Seção 7.

---


### Fase 2 — Absorver as diferenças reais entre marcas

**Objetivo:** as poucas diferenças legítimas de *conteúdo* entre marcas viram config,
não fork. Depois desta fase, não sobra motivo para tocar em código por causa de marca.

**Passos:**
1. **Colunas de Lideranças por config.** Definir `COLUNAS_LIDERANCA` na config de marca
   (lista ordenada de campos exibidos). O model `Lideranca` guarda o superset dos
   campos (já tem os 16 da planilha); o *template* e a lista renderizam só as colunas da
   config. Isadora mostra todas; Sorgatto mostra o subconjunto dele. Comportamento
   (ordenar/paginar/filtrar) é o mesmo código. → resolve o pedido "cada usuário mantém
   seu número de colunas, mesmo comportamento".
2. **Fechar o delta de features** entre as marcas de uma vez (já auditado nesta sessão:
   Isadora era quase superset; o gap real era o EventoAnexo, já portado). Reconvergir
   qualquer coisa que ainda esteja só numa pasta.
3. **Cargos 2022×2026 por marca** confirmados end-to-end: base histórica
   (`TSE_CARGO_BASE`/`TSE_ANO_BASE`) pode divergir do cargo em disputa
   (`TSE_CARGO_2026`). `import_tse` já importa todos os cargos; validar que ranking de
   ameaça e concorrência lidam com cargo cruzado (federal→estadual) para o Sorgatto.

**Como:** cada diferença encontrada faz a pergunta do §2.4 — "isso é *como funciona* ou
*o que mostra*?". Se for "o que mostra", vira chave de config; se for "como funciona",
é bug de duplicação a reconvergir.

**Pronto quando:** nenhuma marca tem arquivo de código que a outra não tenha; toda
diferença entre elas é uma linha diferente de `.env`.

---


### Fase 3 — Virada de produto: SaaS multi-tenant

**Objetivo (depois dos 3 eleitos):** um deploy servindo muitos políticos, cada um com
seus dados isolados, sem repo/servidor por cliente. A config deixa de ser `.env` e vira
**dado no banco**.

**Passos:**
1. **Config vira model.** Criar `Mandato` (ou `Tenant`): as mesmas chaves da
   `settings.CAMPANHA` viram colunas de uma linha por cliente (nome, cores, cargos,
   termos TSE, colunas). Migração natural do §2.3.
2. **Escolher o modelo de isolamento** (decisão registrada na Seção 5):
   - **Schema-per-tenant (`django-tenants`)** — *recomendado*. Cada cliente num schema
     Postgres próprio. Isolamento forte de dados, bom para LGPD (dado eleitoral é
     sensível), backup/exclusão por cliente é limpo. Custo: mais complexidade de
     migrations e roteamento.
   - **Shared-DB + `tenant_id` + RLS** — uma tabela para todos com coluna de tenant e
     Row-Level Security do Postgres. Mais simples de operar, mas isolamento depende de
     nunca esquecer o filtro; risco maior de vazamento entre clientes.
3. **Resolução de tenant por subdomínio/domínio** via middleware
   (`isadora.crm.app`, `sorgatto.crm.app`, ou domínio próprio). O middleware carrega o
   `Mandato` da request e injeta a config — substitui o `settings.CAMPANHA` de env.
4. **Migrar as 3 marcas** de "deploy+env" para "tenants" do produto único. Elas viram os
   3 primeiros clientes, provando o modelo. **Migração de dados:** cada marca hoje tem seu
   próprio Postgres; migrar = despejar o banco de cada marca no **schema** do seu tenant
   (com backup + OK, CLAUDE.md §9.4), um por vez, validando contagens oficiais antes de
   desligar o deploy antigo. Não há merge de dados entre marcas — cada uma entra isolada.
5. **Billing & onboarding self-service** (por último): cadastro de novo mandato, cobrança,
   provisionamento automático de schema. Só faz sentido depois do produto validado.

**Como:** não pular etapas — só entrar aqui com Fases 1–2 sólidas. A migração de env→banco
é incremental: o middleware pode, numa transição, cair para `settings.CAMPANHA` quando
não há tenant resolvido, mantendo os 3 no ar durante a virada.

**Pronto quando:** um novo político entra como linha nova no banco (não como deploy
novo), com dados isolados e config própria, sem tocar em código.

## 5. Decisões-chave (registro)

Cada linha é uma decisão que **não** deve ser re-litigada sem motivo novo. O valor deste
registro é o *porquê* e a *alternativa descartada*.

| # | Decisão | Porquê | Alternativa descartada |
|---|---------|--------|------------------------|
| D1 | **Unificar em 1 código**, não fork por cliente | Elimina drift e cópia manual; único caminho que escala para dezenas de clientes | Repo/pasta por cliente (não escala; multiplica o problema atual) |
| D2 | **Base = Isadora** | É o superset de features e colunas; as outras são deltas de config | Base neutra do zero (jogaria fora trabalho pronto) |
| D3 | **Comportamento=código, marca=config** | Separa o que é igual do que varia; guia toda decisão de "onde mora" | Flags espalhadas por view (vira o drift de novo) |
| D4 | **Config em env agora → banco depois** | Mesmas chaves, só muda a fonte; migração incremental sem retrabalho | Já começar com banco (complexidade cedo demais, sem clientes) |
| D5 | **`TSE_CARGO_2026` como chave de máquina** | Cargos 2026 divergem por marca (Sorgatto federal→estadual); remove o único hardcode do mapa | Manter `deputado_estadual` fixo (quebra Gilson/Sorgatto) |
| D6 | **Colunas de Lideranças por config**, model guarda superset | Diferença é de conteúdo, não de comportamento (§2.4) | Template por marca (fork de comportamento) |
| D7 | **SaaS = schema-per-tenant (django-tenants)** | Isolamento forte de dado eleitoral (LGPD); backup/exclusão por cliente limpos | Shared-DB+RLS (isolamento depende de nunca esquecer o filtro) |
| D8 | **Fases sequenciais, prod intocável sem ritual** | Base de campanha está em uso; instabilidade custa voto (CLAUDE.md §9.4) | Refatorar tudo de uma vez em cima de prod |
| D9 | **Produto = "CRM Base Eleitoral"; pasta/repo = `CRM_Base_Eleitoral`; módulo Django = `crm/`** | "Base eleitoral" descreve o que o produto gerencia (rede + território); módulo `crm/` fica neutro de marca e não colide com o model `Mandato` da F3 | `mandato/` (colide com o model; pré-candidato ainda não tem mandato) |
| D10 | **Monorepo único; config não-secreta versionada em `configs/<slug>`, segredo em env; marca escolhida por `MARCA=<slug>`** | Versiona a config (mata drift também na config), mantém segredo fora do git (§9.1), e vira migração natural para a tabela `Mandato` na F3 | `.env` por marca com tudo dentro (config não versionada, "qual env tem qual valor?") |

## 6. Riscos & mitigação

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Rename do módulo Django quebra imports/deploy | Sistema não sobe | Rename mecânico numa fase isolada (F1), testar as 3 marcas subindo local antes de push; `Procfile`/`wsgi`/`asgi` na checklist |
| Mexer em prod dos 3 durante a unificação | Perda de dado em campanha ativa | CLAUDE.md §9.4: só com **backup + OK explícito**; unificação valida local/branch antes de tocar prod; fases sequenciais |
| Config incompleta → marca sobe "meio Isadora" | Vazamento de identidade entre marcas | Checklist de chaves obrigatórias por `.env`; validar nome/cores/cargo/colunas a cada subida |
| Hardcode de cargo esquecido além do índice do mapa | Mapa errado para Gilson/Sorgatto | Buscar por `deputado_estadual`/`deputado_federal` no código na F1; centralizar em `TSE_CARGO_2026` |
| Migração env→banco (F3) derruba os 3 no ar | Downtime de clientes reais | Middleware com fallback para `settings.CAMPANHA` durante a transição; migrar um tenant por vez |
| LGPD em dado eleitoral no modelo shared-DB | Vazamento entre clientes / exclusão difícil | Escolha D7 (schema-per-tenant) já mitiga; exclusão/anonimização por schema |
| Divergência voltar depois de unificar | Volta o drift | Regra §2.4 em code review; nenhuma diferença de marca pode ser arquivo de código |

## 7. Git & deploy

**Agora (Fases 1–2) — monorepo único, um `origin` (D10):**

- **Um** repositório, **um** `origin`. As 3 marcas são **3 serviços Railway** conectados
  ao mesmo repo. Por padrão todos seguem `main`: **`git push origin main` → os 3
  redeployam**, cada um com sua `MARCA` e seus segredos. Drift-free por construção.
- O que **difere** entre marcas mora em `configs/<slug>.py` **versionado** (não é segredo);
  só chave/banco/API ficam no env de cada serviço (CLAUDE.md §9.1). Mesmo commit serve as 3.
- **Deploy escalonado (validar numa antes das outras)**, se precisar: dar a cada serviço
  uma branch de deploy própria (`deploy/isadora`…) e promover `main → deploy/<marca>` na
  ordem desejada. Só adotar quando o rollout simultâneo incomodar — começar simples.
- **Regra de propagação:** como é um código só, feature nova já vale para as 3 no mesmo
  commit. Ajuste específico de marca é uma linha em `configs/<slug>.py` — nunca um `if
  marca ==` no código (isso seria o drift voltando pela janela).

**Depois (Fase 3) — 1 repo, 1 deploy, N tenants:**

- Some a noção de "remote por marca". Um único deploy do produto.
- Cliente novo = linha nova na tabela `Mandato` + (no modelo schema-per-tenant) um schema
  provisionado. Deploy de código é um só para todos.
- Config nunca mais em `.env` de marca: vem do banco, resolvida por subdomínio.

## 8. Glossário & apêndice

**Glossário:**

- **Marca** — a identidade de uma campanha (Isadora / Sorgatto / Gilson): nome, cores,
  cargos, termos TSE, colunas. É *config*, não código.
- **Tenant / Mandato** — no SaaS (Fase 3), um cliente (político) isolado no produto.
  É a "marca" quando ela vira linha de banco em vez de `.env`.
- **`cargo_2022` / `TSE_CARGO_BASE`** — cargo cuja votação de 2022 é a base histórica do
  mapa. Pode diferir do cargo em disputa.
- **`cargo_2026` / `TSE_CARGO_2026`** — cargo que o candidato disputa em 2026. Chave de
  *máquina* (ex. `deputado_federal`), distinta do rótulo humano `CARGO_2026`.
  - *Nota de longevidade:* os nomes "2022/2026" são do ciclo atual. Num SaaS com ciclos
    futuros (2028, 2030…), o conceito estável é **base histórica** vs **disputa atual** —
    `TSE_ANO_BASE` já é configurável; ao produtizar, preferir nomes por papel (`cargo_base`
    / `cargo_disputa`) a anos fixos.
- **Config-driven** — comportamento fixo no código, conteúdo vindo de config; trocar de
  marca não toca em código.
- **Drift** — divergência acumulada entre os 3 códigos por cópia manual. O inimigo que a
  unificação mata.
- **Schema-per-tenant** — cada cliente num schema Postgres próprio (`django-tenants`).
- **Superset** — a marca (Isadora) que contém todas as features/colunas; as outras são
  subconjuntos por config.

**Apêndice — arquivos-chave (âncoras para implementação):**

- `crm/settings.py` → `settings.CAMPANHA` (config de marca por env)
- `mapa/views.py`, `mapa/management/commands/import_tse.py` → uso de `TSE_CARGO_BASE`/
  `TSE_TERMO_BUSCA`; importa todos os cargos; denormaliza `votos_referencia_2022`
- `templates/mapa/index.html` (~1030) → **hardcode `deputado_estadual`** a substituir por
  `TSE_CARGO_2026` (Fase 1, passo 4)
- `core/context_processors.py` → expõe `campanha` ao front
- `liderancas/models.py` → superset dos 16 campos da planilha central (base da config de
  colunas da Fase 2)

**Nota de proveniência:** este documento nasceu de uma sessão de trabalho longa
(rebranding + agenda + mapa + permissões + arquitetura). Atualizar conforme as fases
avançam — é documento vivo, não foto de um dia.
