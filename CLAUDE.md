# CLAUDE.md — CRM Isadora Piana

> Contrato de auditoria do projeto. Cada regra é escrita para ser **citável** em code
> review: deve ser possível apontar "o trecho X viola a regra Y deste arquivo".
> Regra que não dá para verificar não pertence aqui.
>
> Este documento descreve **como o sistema deve funcionar** — o alvo, não o estado atual.
> Onde a implementação de hoje diverge (ex.: indicadores sintéticos no mapa), o divergente
> é o bug; a regra aqui é o contrato.

---

## 1. Contexto do projeto

CRM da **campanha política de Isadora Piana** (partido **NOVO**, número **30**),
pré-candidata a **Deputada Estadual** em **Santa Catarina** para as eleições de **2026**
(1º turno: 04/10/2026). É uma ferramenta
**interna de uma única organização** — não é multi-tenant, não é SaaS, não é funil de vendas.

Tem **duas faces**:
- **Back-office (web):** gestão da rede, agenda, tarefas, inteligência territorial.
- **PWA de campo (`/app/`):** cadastro rápido de apoiadores e voluntários, **offline-first**,
  usado no celular durante eventos/porta-a-porta.

**Conceitos centrais do domínio:**
1. **Rede de apoio** — hierarquia `coordenador → cabo → apoiador` (model `Lideranca`,
   campo `papel`). Mais `Voluntario` (mobilização), `Egresso` e `Lassberg` (bases externas).
2. **Funil de moderação** — cadastro vindo do PWA nasce `pendente` e só vira base oficial
   quando `aprovado`; pode ser `rejeitado`. Este é o "funil" que mais importa auditar.
   `pendente → aprovado | rejeitado`; `rejeitado → aprovado` só por ação explícita.
3. **Agenda do candidato** — compromissos, roteiros, eventos e tarefas num só calendário.
4. **Inteligência territorial** — mapa de SC com dados eleitorais (TSE) e socioeconômicos
   (IBGE) por município.

Toda lógica de domínio gira em torno desses quatro eixos. Transição de moderação inválida,
registro órfão de rede, ou indicador inventado são bugs.

---

## 2. Stack e convenções

- **Backend:** Django 6.0, Python 3.14. **Sem** DRF, **sem** Celery/Redis, **sem** SPA.
- **Banco:** SQLite em dev, **PostgreSQL no Railway** (prod) via `dj_database_url`.
- **Estáticos:** WhiteNoise. **Config:** `python-dotenv` (`.env`).
- **Front:** templates Django + CSS/JS puro. PWA com **service worker + IndexedDB**.
- **IA:** SDK oficial `anthropic` (limpeza de texto, Haiku 4.5). **Transcrição:** Whisper
  via endpoint compatível com OpenAI (Groq), config por env.

Convenções obrigatórias:
- **Interface em pt-BR.** O domínio (models, campos, choices) já é em pt-BR — mantenha o
  padrão existente de cada app; não traduza campos consolidados só por estilo.
- `snake_case` no Python; `PascalCase` em models; nomes de URL/templates como já usados.
- **Identidade visual** (paleta NOVO — não inventar paleta nova): laranja `#FF6B00` (marca),
  grafite `#2B2B2B` (superfície escura), **laranja escuro `#C44B00`** (assinatura —
  fio/chip/realce, com moderação), roxo `#7c3aed` (vertical Mobilização),
  teal `#0d9488` (Tarefas). Vermelho = pendência/atraso. As variáveis CSS históricas
  (`--navy`, `--ouro`, `--coral`) guardam esses valores; usar sempre a variável, não hex avulso.
- Nada de regra de negócio em template. Ver Seção 4.

---

## 3. Invariantes de domínio (o que mais importa auditar)

1. **Moderação é a fronteira do que é "oficial".** Cadastro com `origem='pwa'` nasce
   `aprovacao='pendente'`. **Contagens, placares, mapa e exports oficiais só consideram
   `aprovado`.** Incluir `pendente`/`rejeitado` em número apresentado como oficial é bug.
   (Exports podem incluir pendentes apenas sob flag explícita, ex.: `--incluir-pendentes`.)
2. **`rejeitado` é estado oculto, com rastro.** Rejeitar exige registrar `motivo_rejeicao`
   e autor; rejeitados não aparecem nas listas padrão. Reverter (`rejeitado → aprovado`)
   é ação explícita do usuário, nunca efeito colateral.
3. **`Lideranca.papel` é o discriminador único** (`coordenador|cabo|apoiador`). Não
   recriar os modelos antigos separados; a lista unificada filtra por `papel`.
4. **Idempotência do sync do PWA.** Todo registro offline carrega um `pwa_client_id` (UUID
   do aparelho). Reenvio **não pode duplicar** — a verificação é por `pwa_client_id`, não
   por nome. Criar registro de campo sem checar `pwa_client_id` é bug.
5. **Deduplicação no cadastro.** Apoiador/voluntário potencialmente duplicado (mesmo
   telefone/nome+cidade) deve ser **detectado e sinalizado**, não recriado silenciosamente.
6. **Soft-delete por padrão** nas entidades de negócio (`Lideranca`, `Voluntario`,
   `Egresso`, `Lassberg`): usar o `SoftDeleteMixin`/`soft_delete()`, nunca `DELETE` físico —
   salvo exigência de LGPD (Seção 11).
7. **Permissão por seção é a regra de acesso.** Visibilidade e ação dependem de
   `Usuario.secoes_permitidas` via `pode_acessar(secao)` (com herança pai→filhos) e do
   decorator `@secao_required`. Não duplicar regra de permissão fora desse mecanismo.

---

## 4. Arquitetura — onde cada coisa vive

- **Views:** orquestram (recebem request, aplicam permissão, chamam a lógica, devolvem
  resposta/render). Não devem conter cálculo de domínio espalhado nem query complexa inline.
- **Regra de negócio e cálculos** (placar da rede, score do mapa, geração de interações,
  moderação): em funções/serviços de domínio reutilizáveis (`core/services.py` e afins),
  não copiados entre views.
- **Acesso a dados:** managers/querysets reutilizáveis (ex.: `SoftDeleteManager`). Filtro de
  `aprovacao` e de soft-delete deve vir do manager/queryset, não reescrito em cada view.
- **Endpoints AJAX/JSON** retornam JSON consistente (`{success|ok, ...}` ou `{error}` com
  status HTTP correto) — ver Seção 8.

Violação típica a flagar: cálculo de domínio ou filtro de "oficial" duplicado/divergente
entre uma view e o manager canônico.

---

## 5. ★ Integridade de dados — mapas e indicadores

Esta é a seção mais sensível. O mapa orienta decisão estratégica de campanha; dado errado
aqui custa voto e dinheiro.

1. **Dado real, nunca sintético apresentado como real.** Indicador socioeconômico ou
   demográfico (renda, % urbana, escolaridade, MEI, Bolsa Família, etc.) só pode ser
   exibido/pontuado se vier de **fonte oficial verificável** (IBGE, TSE, DataSUS…).
   **É proibido derivar um indicador de outro** (ex.: estimar renda/% urbana a partir do PIB
   per capita) e apresentá-lo como medido. Buscar o dado disponível na fonte — não fabricar.
2. **Sem dado → "sem dado".** Quando a fonte não tem o valor, o campo fica vazio/"sem dado"
   e é **excluído do cálculo**. Nunca preencher por fórmula, média ou proxy disfarçado.
3. **Rótulo = conteúdo, e unidade = unidade real.** O que está rotulado "PIB per capita"
   deve ser `PIB ÷ população`, na unidade exibida (R$ por habitante — não PIB total, não
   "R$ mil" mostrado como "R$"). Rótulo divergente do valor é bug (ex.: já corrigido o
   balão que exibia PIB total como per capita).
4. **Proveniência obrigatória.** Cada indicador registra `ano_referencia` e a fonte. Import
   de dado oficial é idempotente e rastreável (comandos `import_*`).
5. **Score/perfil só pondera sinais reais e independentes.** Um indicador derivado de outro
   (correlação ~1 com o PIB) **não entra** no score como sinal novo — seria contar a mesma
   informação duas vezes. Auditoria de correlação (`auditar_indicadores`) deve acusar isso.
6. **Sanidade dos dados base.** `eleitores ≤ população`; `população > 1` (população `=1`
   distorce per capita). Valores que violem isso são erro de dado, não "outlier".
7. **Mapa não mistura "medido" com "estimado" sem marcar.** Se um valor estimado for
   exibido em transição, ele é rotulado como estimativa ("est.") e nunca alimenta números
   oficiais.

---

## 6. PWA / cadastro de campo

1. **Offline-first.** O cadastro de apoiador/voluntário **funciona sem rede**: grava na fila
   local (IndexedDB) e envia ao reconectar. Perda de cadastro por falta de internet é bug.
2. **Sync idempotente** (ver Seção 3.4) — reenvio da fila não duplica.
3. **Funções online-only degradam com aviso.** Transcrição por microfone (Whisper) e
   limpeza com IA exigem rede; offline, o botão informa em vez de falhar silenciosamente.
4. **PWA é leve.** Processamento pesado (IA/transcrição/relatório) roda no **servidor**, não
   no aparelho. Não embutir lógica de negócio cara no cliente.
5. **Entrada validada e formatada na origem.** Campos obrigatórios mínimos (nome, cidade)
   barram o envio; telefone usa máscara `(00) 00000-0000`.
6. **Mudança no shell do PWA exige bump do cache do service worker** (`CACHE` em `sw.js`),
   senão o aparelho serve versão velha.

---

## 7. IA (Claude / Anthropic) e transcrição

1. **Chaves e modelo só por env.** `ANTHROPIC_API_KEY`, `IA_LIMPEZA_MODEL`
   (default `claude-haiku-4-5`), `OPENAI_API_KEY`/`WHISPER_BASE_URL`/`WHISPER_MODEL`
   (transcrição). Nada hardcoded.
2. **A limpeza com IA é fiel.** Corrige forma (ortografia, pontuação, organização) e
   **nunca inventa, supõe ou remove** fato, nome, número ou telefone. É **on-demand** (só
   quando o usuário aciona), nunca automática em massa sem pedido.
3. **Degradação graciosa.** Sem chave configurada, os endpoints respondem com aviso claro
   (HTTP 503 "não configurado"), não com erro genérico nem 500.
4. **Custo é decisão do usuário.** Operação de IA que gasta tokens é disparada por ação
   explícita; não criar laços automáticos que chamem a API sem o usuário pedir.

---

## 8. Endpoints AJAX / JSON

1. Entrada lida de forma segura (`json.loads` com `try/except`; `request.POST`/`FILES`
   validados). Nada de assumir corpo bem-formado.
2. **Status HTTP corretos:** `200/ok` em sucesso, `400` em validação, `403` em permissão,
   `404` em não encontrado, `503` em recurso externo não configurado. Não devolver `200`
   para erro.
3. Resposta JSON consistente por convenção do app (`{success: true}` / `{ok: true}` ou
   `{error: "..."}`); o front trata ambos os caminhos.
4. Listas grandes (lideranças, voluntários, egressos, lassberg) são **paginadas** e
   respeitam `per_page`. Lista sem paginação em recurso que cresce é bug.

---

## 9. Segurança (crítico — o repositório é público)

1. **Segredos jamais no código ou no repositório.** Tudo via `.env`/variável de ambiente.
   Chave, senha ou token hardcoded = bloqueio. `.env*` deve estar no `.gitignore`; backups
   de `.env` nunca são commitados.
2. **`SECRET_KEY`, `ALLOWED_HOSTS` e `DEBUG` vêm do ambiente.** `DEBUG=False` em produção;
   `ALLOWED_HOSTS` explícito.
3. **Permissão por view é obrigatória.** Toda rota sensível usa `@secao_required` (ou
   checagem equivalente). Endpoint autenticado nunca confia em identidade/papel vindos do
   corpo do request — derive do usuário no servidor.
4. **Produção (Railway) é intocável sem ritual.** Migração/alteração em prod só com
   **backup feito + OK explícito** do responsável. Mudança local nunca presume prod.
5. **Sem PII em log** (ver Seção 11).

---

## 10. Dados e migrations

1. **Migration destrutiva exige aviso explícito** no PR (o que se perde + estratégia de
   backup/migração de dados).
2. **`on_delete` consciente** em todo `ForeignKey` — `PROTECT`/`SET_NULL` para dados de
   pessoa/rede; nunca `CASCADE` cego em registro de cidadão.
3. **Imports de dado oficial são idempotentes e rotulados** (`import_tse`, `import_planilha`,
   `import_*_ibge`): rodar duas vezes não duplica; cada carga registra ano/fonte. Atenção a
   particularidades conhecidas da fonte (ex.: arquivo do TSE de SC sem cargo Presidente).
4. **Nada de migration aplicada editada à mão** em ambiente compartilhado.

---

## 11. LGPD e dado eleitoral

1. **Base legal rastreável** para coleta de dado pessoal; uso é o da campanha, não revenda.
2. **Direito de exclusão** atende **DELETE físico ou anonimização**, sobrepondo o soft-delete
   da Seção 6 quando o titular solicita.
3. **Sem PII em texto claro nos logs** (telefone, e-mail, CPF, endereço).

---

## 12. Performance

1. **N+1 proibido** em listas e no mapa: usar `select_related`/`prefetch_related`. Acesso a
   relação dentro de loop sem prefetch deve ser flagado.
2. **Agregação no banco**, não em Python, para contagens/somas de rede e indicadores.
3. Operação longa não bloqueia o request de forma perceptível; se inevitável, é assíncrona
   no cliente (AJAX) com feedback de progresso.

---

## 13. Testes (mínimo a cobrir)

1. **Moderação:** aprovar e rejeitar mudam estado e contagem oficial corretamente; rejeitado
   sai das listas; reversão é explícita.
2. **Permissão por seção:** usuário com/sem a seção vê/não vê o recurso.
3. **Idempotência do sync:** reenviar a mesma fila não duplica registros.
4. **Integridade do mapa:** indicador sem fonte real não entra no score; rótulo bate com o
   valor/unidade; auditoria de correlação acusa indicador sintético.

---

## 14. O que NÃO flagar (reduzir falso positivo)

- Estilo/formatação que um linter/formatter resolveria — não é code review.
- Falta de teste em código fora do diff.
- Preferência subjetiva de nomenclatura que já segue a Seção 2.
- Mudança de comportamento claramente intencional e coerente com o PR.
- Domínio em português nos models/campos — é o padrão do projeto, não erro.

> Regra do revisor: na dúvida se um problema é real, **não** flague. Falso positivo corrói
> confiança. Só aponte o que dá para citar contra uma regra acima.
