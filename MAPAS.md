# MAPAS.md — Padrão de exposição dos mapas

> Contrato para **toda visualização geográfica** do CRM (o mapa de SC e seus modos).
> Escrito no mesmo espírito do [CLAUDE.md](CLAUDE.md): cada regra deve ser citável em
> code review. O mapa orienta decisão estratégica de campanha — dado errado ou rótulo
> enganoso aqui custa voto e dinheiro (cf. CLAUDE.md §5).

Arquivos-chave: `templates/mapa/index.html` (UI + legendas + dashboards),
`static/js/map/sc-map.js` (render D3, cores, tooltips), `mapa/views.py` (APIs/cálculo),
`mapa/models.py` (`Eleicao`, `ResultadoCandidato`, `ResultadoZona`, `IndicadorMunicipal`).

---

## 1. Todo mapa responde uma pergunta de decisão

Cada modo abre com o que o gestor precisa **decidir**, não só com o título técnico.
Ex.: "Onde a Isadora já é competitiva — e onde cada voto novo vale mais?" antes de
"Posição no ranking por cidade (2022)". A pergunta vive no painel de ajuda (`updateHelp`)
e/ou no `dash-summary-title`.

## 2. Hierarquia de leitura (3 níveis)

- **Nível 1 (sempre visível):** pergunta + 1 número-síntese + mapa colorido + legenda.
- **Nível 2 (um clique):** o explainer `legendaCamada(cfg)` — blocos fixos
  "1 · O que a cor mostra / 2 · De onde vêm os números / 3 · Como interpretar".
- **Nível 3 (hover):** tooltip por município com os dados daquela cidade.

O toggle "▸ Como ler este mapa / ▾ Esconder explicação" **persiste a preferência**
(`localStorage: mapa_explainer_aberto`): abre na 1ª visita (o usuário aprende a ler o
mapa), depois começa recolhido; qualquer toggle manual é lembrado. Ver
`_explainDefault` / `_explainSalvarPref` em `index.html`.

## 3. Taxonomia epistêmica — todo número tem procedência

Todo valor recebe (ou pode receber em 1 interação) um badge `.vtag`:

| Badge | Classe CSS | Significado | Exigência |
|-------|-----------|-------------|-----------|
| **FATO** | `.vtag.fato` (verde) | medido de fonte oficial/CRM (TSE, cadastro, campo) | — |
| **META** | `.vtag.meta` (âmbar) | decisão da campanha (ex.: % alvo) | — |
| **CONTA** | `.vtag.conta` (azul) | derivado por fórmula de FATOs | fórmula acessível (tooltip/explainer) |
| **ESTIMADO** | `.vtag.estimado` (cinza/amarelo) | projeção/indício (ex.: perfil IBGE) | margem/premissa explícita |

Regra: **nenhum CONTA ou ESTIMADO aparece sem sua fórmula/premissa a 1 clique/hover.**
Um indicador derivado de outro (correlação ~1) não entra no score como sinal novo
(CLAUDE.md §5.5).

## 4. Rigor matemático

- **Posição no conjunto de cidades:** nunca só a média aritmética de ranking (distorcida
  por outliers e cega ao porte). Usar **mediana** (`median_position`) e **média ponderada
  pelo eleitorado** (`weighted_position` = Σ(posição × eleitores) ÷ Σ(eleitores)), ambas
  **CONTA**. Ver `Elections2022API` em `mapa/views.py`.
- **Percentil por cidade** (§4c): posição ÷ total de candidatos ("top X%") — comparável
  entre cidades de portes diferentes. Campo `percentil` por cidade.
- **Percentual de votos:** sempre explicitar o denominador. No projeto `percentual` do TSE
  é **% dos votos válidos nominais** (soma de `QT_VOTOS_NOMINAIS`, exclui brancos/nulos —
  ver `import_tse.py`). Rotular "% válidos", nunca só "%".
- **Gap para meta 2026:** exibir absoluto **e** relativo ("faltam 1.240 votos = +18,6%"),
  badge CONTA.
- **Formatação pt-BR:** milhar com ponto, decimal com vírgula, ordinal `º` (não `o`/`.5o`).
  Usar `fmt` (`static/js/map/api.js`) e `toLocaleString('pt-BR')`; para ordinal com
  fração, trocar `.`→`,` antes do `º`.

## 5. Semântica de cor

- Escala **verde→vermelho** só para ranking/desempenho.
- Escala **azul sequencial** para volume (nº de votos, eleitorado) — nunca reusar
  verde/vermelho para volume.
- **Sem dado → cinza claro** (`#e2e8f0`/`#d1d5db`) **com rótulo textual "Sem registro"**
  na legenda — **nunca branco** (confunde com o fundo). O fill neutro base já é
  `#e2e8f0` (`_resetToNeutral`).
- Cada faixa da legenda tem rótulo textual (não depende só da cor); alvo de contraste
  WCAG AA.

## 6. Microcopy

Voz ativa, frases curtas, sem jargão sem tradução. Legenda com significado **acionável**
("1º lugar — consolidar e defender"; "11º+ — avaliar custo-benefício"). Tooltip por
município no padrão: `[Cidade] · [Posição + percentil] · [Votos (FATO)] ·
[% válidos (FATO)] · [Gap p/ meta (CONTA)]`.

## 7. Rodapé de proveniência

Todo modo mostra `#mapProvenance` com a **fonte real da camada** (via `PROVENIENCIA[mode]`
+ `renderProvenance` em `index.html`). Um "Fonte: TSE" sob o mapa de Perfil (IBGE) é
mentira — por isso a proveniência é **por camada**, não fixa. Formato:
`Fonte: <fonte> · Municípios: 295 [· Zonas: <n> quando há dado eleitoral]`.

> **TODO (§7):** os dados não guardam timestamp de importação (só `ano`/`ano_referencia`
> em `Eleicao`/`IndicadorMunicipal`), então **não** exibimos "Atualizado em [data]" para
> não inventar. Para cumprir o item por inteiro, expor a data de importação no backend.

---

## Gap analysis — estado em 2026-07-01

Auditoria dos 8+ modos do mapa contra este padrão, no momento da criação deste documento.
`✅` conforme · `🟡` parcial · `❌` gap · `→` ação feita nesta rodada.

| Item | Antes | Agora | Onde |
|------|-------|-------|------|
| §2 Explainer 3 níveis | ✅ `legendaCamada()` | ✅ | `index.html` |
| §2 Persistir toggle | ❌ var JS, sem `localStorage` | ✅ → `mapa_explainer_aberto` | `index.html` |
| §3 Badges FATO/META/CONTA/ESTIMADO | ✅ `.vtag.*` | ✅ | `index.html` |
| §3 Badge inline em todo tooltip | 🟡 badges no explainer, não em cada tooltip | 🟡 (mediana/percentil ganharam badge; tooltips por município ainda parciais) | — |
| §4a Média simples de ranking | ❌ `avg = Σpos/n` | ✅ → mediana + ponderada (CONTA) | `views.py`, `index.html`, `sc-map.js` |
| §4c Percentil por cidade | ❌ | ✅ → coluna "Percentil (top X%)" | `views.py`, `index.html` |
| §4b Denominador do % | 🟡 rótulo só "%" | ✅ → "% válidos" + tooltip | `index.html` |
| §4d Gap absoluto + relativo | 🟡 (Vitória mostra gap) | 🟡 relativo nem sempre explícito | — |
| §4e Formatação pt-BR | ✅ `toLocaleString('pt-BR')` | ✅ (ordinal `o`→`º` corrigido no placar) | — |
| §5 Fill nunca branco | ✅ base `#e2e8f0` | ✅ | `sc-map.js` |
| §5 Rótulo "Sem registro" | ❌ no mapa de eleições | ✅ → banda na legenda | `index.html` |
| §5 Escala azul p/ volume | 🟡 camada "absoluto" já azul | 🟡 nem todo volume normalizado | `sc-map.js` |
| §7 Rodapé de proveniência | ❌ espalhado no texto | ✅ → `#mapProvenance` por camada | `index.html` |
| §7 "Atualizado em [data]" | ❌ sem timestamp na base | ❌ **TODO** (não inventar data) | `mapa/models.py` |

### TODOs remanescentes (falta insumo ou fora do escopo desta rodada)

1. **§7 "Atualizado em [data]":** adicionar `importado_em`/`atualizado_em` (auto_now) em
   `Eleicao` e `IndicadorMunicipal` e expô-lo nas APIs, para o rodapé mostrar a data real
   de carga sem fabricação.
2. **§3 badge inline em todos os tooltips por município:** levar FATO/CONTA/ESTIMADO para
   dentro de cada `_...TipHtml` dos 8 modos (hoje o rigor vive no explainer/tabela).
3. **§4d gap relativo:** garantir "+X% sobre 2022" ao lado do gap absoluto em Vitória 2026
   e Estratégico.
4. **§5 escala azul de volume:** padronizar toda métrica de volume (eleitorado, votos
   absolutos) na escala azul sequencial, separando visualmente de desempenho.
5. **§1 pergunta estratégica** revisada e uniformizada como primeira linha de cada modo.
