# Sincronização e auditoria de indicadores municipais

Os "Dados Socioeconômicos" do Mapa (aba **Perfil Ideológico**) vêm da tabela
`IndicadorMunicipal`. Estes comandos mantêm esses dados corretos e auditados.

## Comandos

| Comando | O que faz |
|---|---|
| `python manage.py auditar_indicadores` | Audita tudo: cobertura, impossibilidades lógicas, quais indicadores são sintéticos (correlação com PIB), eleitores×população. Sai com código **1** se houver problema **crítico** (útil em cron/CI). `--json` para máquina, `--strict` para tratar avisos como críticos. |
| `python manage.py sync_indicadores` | Sincroniza com dados **reais** do IBGE e roda a auditoria no fim. |
| `python manage.py sync_indicadores --so-populacao` | Só a etapa de população (rápida e segura). |
| `python manage.py sync_indicadores --dry-run` | Mostra o que mudaria sem gravar. |

### O que o `sync_indicadores` faz, em ordem
1. **População** — Censo 2022 oficial (IBGE SIDRA tabela 4714, var 93). Corrige a
   raiz do bug `populacao=1` (o importador de PIB usa `cidade.populacao or 1`; se a
   população estiver 0/errada, o PIB per capita explode).
2. **PIB e derivados** — reaproveita `import_indicadores_ibge` (IBGE).
3. **Demografia** (idade real) — reaproveita `import_demograficos_ibge`.
4. **Auditoria** — `auditar_indicadores`; falha sinaliza problema.

## Rodar na produção (Railway)

```bash
railway run python manage.py sync_indicadores            # sincroniza + audita
railway run python manage.py auditar_indicadores         # só auditar
```

## Agendamento mensal (duas opções)

### A) GitHub Actions
O arquivo do workflow está em `docs/github-workflow-sync-indicadores.yml` (fora de
`.github/workflows/` porque criar workflows exige um token com escopo `workflow`).
Para ativar: copie esse conteúdo para `.github/workflows/sync-indicadores.yml`
pela interface do GitHub (Add file → Create new file) — roda dia 5 às 06:00 UTC.
Pré-requisito: criar o secret **`RAILWAY_TOKEN`** no repositório
(Settings → Secrets → Actions). Gere o token em Railway → Account → Tokens.

### B) Railway Cron nativo
No painel do Railway:
1. **New → Empty Service** (mesmo repositório/imagem).
2. Settings → **Cron Schedule**: `0 6 5 * *` (dia 5, 06:00 UTC).
3. **Custom Start Command**: `python manage.py sync_indicadores`.
O serviço de cron sobe, roda o comando e encerra — não fica de pé como o `web`.

## O que é REAL e o que ainda é estimado

Reais do IBGE Censo 2022 (comandos dedicados, todos rodam no sync):
- **População** (4714), **PIB** (5938), **Renda per capita** (3563),
  **Urbano/rural** (9923), **Idosos/Jovens** (9514), **Alfabetização** (10091).
- **lat/lng** — centroide do geojson (`preencher_coordenadas`, sem API).

> Obs.: o campo `anos_estudo_medio` passou a guardar a **taxa de alfabetização (%)**;
> no painel o rótulo é "Alfabetização".

Ainda **estimados** a partir do PIB (selo `est.` no painel):
- **Bolsa Família** — comando `import_bolsa_familia_real` já existe (API do Portal da
  Transparência). Exige um **token gratuito**:
  1. Cadastre o e-mail em https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email
  2. Configure o token na produção: `railway variables --set PORTAL_TRANSPARENCIA_TOKEN=xxxx`
     (e como secret do GitHub Actions, se usar o cron).
  3. Rode: `PORTAL_TRANSPARENCIA_TOKEN=xxxx python manage.py import_bolsa_familia_real`.
  O `sync_indicadores` roda esse passo automaticamente **quando o token está presente**.
- **MEIs** — fonte é a Receita Federal (dump grande); segue estimado.
