# Integração da Agenda com o Google Agenda (Google Calendar)

> Ideia registrada para implementação futura. Objetivo: sincronizar a agenda do
> CRM (Isadora) com o Google Agenda de uma pessoa/e-mail — idealmente **nos dois
> sentidos** (o e-mail recebe nossa agenda e a nossa agenda recebe a dela).

## Objetivo
- **Saída:** os compromissos/eventos do CRM aparecem no Google Agenda de um e-mail.
- **Entrada:** o que for criado/editado no Google Agenda dela entra no CRM.

## Os dois fluxos (dificuldades diferentes)

### 1. Nossa agenda → Google (sair daqui) — fácil
- **Feed ICS (assinatura)**: gerar uma URL secreta `.ics` com os itens; a pessoa
  faz "Adicionar agenda por URL" no Google. **Somente leitura**, atualização a
  cada **algumas horas** (não instantâneo). Sem OAuth. **Maior custo-benefício**.
- **Via API**: criar os eventos direto no calendário dela pela Google Calendar
  API — instantâneo, mas exige autorização (OAuth) dela.

### 2. Google → nossa agenda (entrar aqui) — mais trabalhoso
- Google Calendar API + **OAuth** (consentimento da pessoa) e então:
  - **polling**: um management command periódico lê as mudanças; ou
  - **push/webhook**: o Google avisa nosso servidor quando algo muda (precisa de
    endpoint **HTTPS público** — o Railway já oferece).

## Bidirecional (as duas vias) — é um projeto, não um ajuste
Requisitos:
- **OAuth** + armazenamento seguro de tokens (com refresh) por usuário;
- **mapeamento** evento Google ↔ `Compromisso`/`Evento` (guardar `google_event_id`);
- **anti-loop/dedup** com `syncToken` (não reimportar o que nós mesmos enviamos);
- **resolução de conflito** (quem vence quando editado dos dois lados);
- **gatilho de sync**: como o projeto **não usa Celery/Redis** (CLAUDE.md §2),
  seria um **management command no cron** (a cada X min) ou os **push channels**
  do Google batendo num webhook nosso.

## Pontos de atenção
- **O que sincroniza:** `Compromisso` e `Evento` mapeiam bem (têm data/hora/cidade).
  `Roteiro` é interno (sequência) — provavelmente sincroniza só as paradas.
- **Segredos:** `client_id`/`client_secret`/tokens só em `.env`/variáveis
  (repositório é público — CLAUDE.md §9).
- **Tipo de conta:**
  - **Google Workspace** → dá para usar **service account com delegação** (sem cada
    pessoa logar);
  - **Gmail pessoal** → **OAuth** com consentimento.
- **Degradação graciosa:** sem credenciais configuradas, a feature fica inativa com
  aviso, não quebra (mesmo padrão da IA/Whisper).

## Recomendação de faseamento
1. **Fase 1 (rápida):** feed **ICS** de saída (URL secreta) → a pessoa assina e
   recebe a nossa agenda. Entrega valor com quase nenhuma infra.
2. **Fase 2 (completa):** Google Calendar API + OAuth + comando de sync (cron) para
   o **bidirecional**. É uma feature de verdade (alguns dias + manutenção de tokens).

## A definir antes de implementar (escopo)
- Conta é **Workspace** ou **Gmail pessoal**?
- Quais itens sincronizam: **Compromisso**, **Evento**, paradas de **Roteiro**?
- Precisa ser **instantâneo** ou pode ter **atraso** (minutos/horas)?
- Sincronização é de **um e-mail** (a candidata) ou **por usuário** do CRM?
- Quem **vence** em caso de conflito (CRM ou Google)?

## Esforço estimado
- Fase 1 (ICS saída): **baixo** (~0,5–1 dia).
- Fase 2 (bidirecional API+OAuth+cron/webhook): **médio–alto** (~3–5 dias + manutenção).
