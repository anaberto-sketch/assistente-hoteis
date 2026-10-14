# Plano de Implementação de Dados — Assistente de Revenue para Hotéis

> Documento técnico do time de dados. Descreve como os dados do material (Excel `Hackaton AI - Asistente de Revenue para Hoteles`) alimentam o assistente conversacional, e como a camada de dados evolui do CSV atual para um backend trocável.
>
> **Fontes de verdade referenciadas neste documento:**
> - `data/Hackaton AI - Asistente de Revenue para Hoteles (1).xlsx` — abas `1. Objetivo y material`, `2. Datos y query`, `3. Diccionario`, `4. Preguntas`, `5. Palancas (plus)`.
> - `data/field_dictionary.yaml` — dicionário de 59 campos (transcrição verbatim da aba `3. Diccionario` + sinônimos curados).
> - `data/perguntas_eval.csv` — as 33 perguntas do set de avaliação (aba `4. Preguntas`).
> - `data/hotels.csv` — a tabela de hotéis (regenerada a partir da aba `2. Datos y query`).
> - Google Doc do time (abas "Guia 1", "guia cris", "notas rafael") — decisões de arquitetura.
> - Código existente em `src/assistant_hotel/` — implementação de referência.

---

## 1. Resumo executivo

O assistente é um **agente conversacional em LangGraph** que, dado um `hotel_id`, lê uma linha determinística da tabela de hotéis e responde perguntas de negócio de um hoteleiro (Despegar), em PT-BR (Brasil) ou ES (demais países). A decisão central de arquitetura é **`lookup ≠ retrieval`**:

- **Lookup (determinístico):** o `hotel_id` resolve exatamente uma linha (`HotelRow`) — 59 campos organizados em 5 blocos. Não há busca aproximada aqui; é chave primária.
- **Retrieval (RAG léxico):** o *dicionário de campos* (definições ES/PT + sinônimos + "como ler") é o corpus sobre o qual roda um índice BM25, para o LLM saber *o que cada campo significa* e *como lê-lo* antes de redigir a resposta.
- **Diagnóstico (determinístico):** 13 funções de regra em Python puro calculam, a partir da linha, qual(is) palanca(s) recomendar. O LLM apenas **narra** fatos pré-computados — nunca calcula nem inventa número.

O papel da camada de dados neste plano é garantir que (a) os números sejam lidos sem ambiguidade (vírgula decimal, aspas de milhar, AP-range como string), (b) `NULL` seja preservado como `NULL` e nunca virado `0`, (c) as métricas e os limiares de decisão tenham **uma única fonte de verdade** com proveniência, e (d) a abstração permita trocar o CSV por um backend SQL (PostgreSQL) sem tocar na lógica de domínio.

O repositório **não é greenfield**: já existe uma implementação completa e testada (114 testes). Este plano, portanto, documenta o estado atual e o caminho de conclusão/extensão — não uma reescrita.

---

## 2. Estado atual

O que **já existe e funciona** no repositório (confirmado lendo o código e os testes):

| Camada | Arquivo(s) | Status |
|---|---|---|
| Modelo / Protocolo | `src/assistant_hotel/data/repository.py` | `HotelRepository` Protocol com `get` / `find_by_name` / `all_ids` |
| Schema + normalização | `src/assistant_hotel/data/schemas.py` | `normalize_value`, `STRING_COLUMNS`, `BOOL_COLUMNS`, `_parse_number` (vírgula/aspas, `""`→`None`) |
| Repositório CSV | `src/assistant_hotel/data/csv_repository.py` | `CsvHotelRepository` + `find_by_name` com difflib (`NAME_MATCH_THRESHOLD=0.6`) |
| Limiares | `src/assistant_hotel/domain/thresholds.py` | 14 `Threshold` com proveniência `[MATERIAL]`/`[ENG]` |
| Regras | `src/assistant_hotel/domain/rules.py` | 13 funções `row -> Lever | None`, `ALL_RULES` em ordem estável |
| Diagnóstico | `src/assistant_hotel/domain/diagnosis.py` | `RULE_SPECS`, modificadores, `diagnose()` |
| Blocos / campos | `src/assistant_hotel/domain/blocks.py`, `fields.py` | `BLOCKS` (5), `FieldEntry`, carrega `field_dictionary.yaml` (59 campos) |
| Idioma | `src/assistant_hotel/domain/language.py` | `language_for`: `BR`→pt, demais→es (NULL→es) |
| Retrieval | `src/assistant_hotel/retrieval/` | BM25 sobre o dicionário, `DEFAULT_LIMIT=14`, 4 garantias de inclusão |
| Grafo | `src/assistant_hotel/graph.py`, `nodes/` | `START → resolve_hotel → fetch_row → diagnose → retrieve_docs → assemble → generate → validate → END` (`→ clarify`) |
| Guardrails numéricos | `src/assistant_hotel/guardrails/numeric.py` | `check_numbers`, `check_years` |
| Prompts | `src/assistant_hotel/prompts/` | `build_context`, fact sheet, thresholds, fields expostos |
| LLM | `src/assistant_hotel/llm.py` | `GenPlatLLM` via GenPlat (iFood), `auth_token=` |
| API / CLI | `src/assistant_hotel/api.py`, `cli.py` | FastAPI `/health` + `/chat`, REPL |
| Dados | `data/field_dictionary.yaml`, `data/perguntas_eval.csv` | presentes e trackeados |

O que **falta / precisa de atenção** (pendências de dados):

1. **`data/hotels.csv` está DELETADO no working tree** (`git status` mostra `D data/hotels.csv`). O código depende dele (`CsvHotelRepository`). Precisa ser **regenerado** a partir da aba `2. Datos y query` do xlsx. Não há `data/hotels.csv` no repositório remoto neste estado local.
2. O xlsx (`data/Hackaton AI - Asistente de Revenue para Hoteles (1).xlsx`) e `refs/` estão **untracked** — decisão necessária sobre versionar ou não o material bruto.
3. Coluna **`perfil_ejemplo`** (60ª coluna do CSV) está **vazia em todas as linhas** e **não** consta no dicionário de 59 campos. Precisa ser tratada (drop ou documentada como não usada).

### Discrepâncias reportadas (PASSO 4)

Conforme a instrução "Se algo não bater com o que você leu, pare e reporte", as seguintes divergências entre o material real e o resumo fornecido no prompt foram encontradas e **não bloqueiam** a execução, mas ficam registradas:

1. **Nomes dos arquivos em `refs/` não batem com o esperado.** O prompt esperava "4 arquivos: Excel principal, PDF, JPEG, CSV das 33 perguntas" dentro de `refs/`. Na prática `refs/` contém **apenas 2 arquivos**: `Cópia de GenAI @Despegar _ 13, 14 y 15 de Octubre 2026.pdf` e `d79fa471-...jpeg`. O Excel está em `data/` (untracked) e o CSV das perguntas é `data/perguntas_eval.csv` (tracked). Não há pasta `/ref` — é `refs/`.
2. **`data/hotels.csv` está apagado** no working tree, apesar de o código (e o resumo) tratá-lo como a tabela canônica.
3. **60ª coluna `perfil_ejemplo`** existe no CSV mas não no dicionário (59 campos) e está vazia em todas as 20 linhas.
4. **"Não usam Databricks"** (anotação da aba "notas rafael" do Google Doc: "Eles nao usam Databricks grrrrrrrrrrr"). O prompt pede para projetar a troca para "Databricks/PostgreSQL". A abstração permanece válida, mas o alvo real de troca deve ser **PostgreSQL/SQL**; Databricks fica anotado como **não utilizado pelo time**, não como alvo.

---

## 3. Arquitetura

### 3.1 Visão de fluxo (existente)

```
                          ┌────────────────────────────────────────────┐
  pergunta + hotel_id ──▶ │ resolve_hotel                              │
                          │   (nome → id → ordem anterior; senão clarify)│
                          └───────────────┬────────────────────────────┘
                                          ▼
                          ┌────────────────────────────────────────────┐
                          │ fetch_row   (language_for(country_code))    │
                          │   HotelRepository.get(hotel_id) → HotelRow  │
                          └───────────────┬────────────────────────────┘
                                          ▼
                          ┌────────────────────────────────────────────┐
                          │ diagnose    (13 regras Python determinísticas)│
                          │   → levers ordenados + data_quality         │
                          └───────────────┬────────────────────────────┘
                                          ▼
                          ┌────────────────────────────────────────────┐
                          │ retrieve_docs (BM25 sobre field_dictionary) │
                          │   must_include = field_refs das levers       │
                          └───────────────┬────────────────────────────┘
                                          ▼
                          ┌────────────────────────────────────────────┐
                          │ assemble    (build_context: fact sheet +    │
                          │              thresholds + fields expostos)  │
                          └───────────────┬────────────────────────────┘
                                          ▼
                          ┌────────────────────────────────────────────┐
                          │ generate    (LLM narra; fallback sem token) │
                          └───────────────┬────────────────────────────┘
                                          ▼
                          ┌────────────────────────────────────────────┐
                          │ validate    (check_numbers + check_years)   │
                          │   → END  |  → generate (1 retry)            │
                          └────────────────────────────────────────────┘
```

### 3.2 Separação de responsabilidades na camada de dados

| Responsabilidade | Onde vive | Por quê |
|---|---|---|
| Ler linha bruta | `DataLoader` (Protocol) → `CsvHotelRepository` | troca de backend não toca domínio |
| Normalizar tipos | `schemas.normalize_value` | vírgula/aspas/NULL em um só lugar |
| Definir blocos/campos | `domain/fields.py` + `field_dictionary.yaml` | dicionário é dado, não código |
| Calcular métricas | `domain/` (funções puras) | determinístico e testável |
| Decidir limiares | `domain/thresholds.py` | uma fonte de verdade com proveniência |
| Mapear pergunta→dados | `domain/blocks.py` + `retrieval` | roteamento léxico |
| Expor ao LLM | `prompts/render.py` | recorte (guardrail 1) |

### 3.3 Pilha

- **Linguagem:** Python ≥ 3.11 (uv como gerenciador).
- **Orquestração:** LangGraph v1.2.15 (grafo linear, 1 aresta condicional).
- **LLM:** Anthropic SDK via GenPlat (gateway iFood); `Authorization: Bearer` (token do Tompero em `~/.config/tompero/requester_token`); modelo `claude-sonnet-5-bedrock`.
- **Dados hoje:** CSV + YAML. **Dados depois:** PostgreSQL (ver §8), mantendo o mesmo Protocol.

---

## 4. Estrutura de dados (§5.1)

### 4.1 Os 5 blocos / 59 campos (aba `3. Diccionario`)

| Bloco | Qtd | Campos |
|---|---|---|
| Identificación | 5 | `hotel_id`, `hotel_name`, `country_code`, `destiny_code`, `destiny` |
| EXPO | 5 | `searchers`, `detailers`, `cvr_search_success`, `cvr_detail_success`, `cvr_total` |
| RESERVAS | 20 | `gb_cy`, `gb_ly`, `bk_cy`, `bk_ly`, `rn_cy`, `rn_ly`, `gb_yoy_pct`, `bk_yoy_pct`, `rn_yoy_pct`, `gb_35d`, `bk_35d`, `rn_35d`, `hotel_growth_pct`, `dest_growth_pct`, `rn_90d_cy`, `rn_90d_ly`, `rn_90d_vs_ly`, `perf_rn_90d_cy`, `perf_compset_rn_90d_cy`, `flag_rn_below_compset` |
| TARIFAS | 24 | `total_lose_logueado_pct_35d`, `profundidad_total_bkg_35d`, `worst_ap_bkg_35d`, `profundidad_worst_ap_bkg_35d`, `worst_ap_compset`, `profundidad_worst_ap_compset`, `profundidad_total_compset`, `delta_precio_compset_pct`, `target_asp`, `compset_asp_avg`, `avg_genius_discount_pct`, `descuento_opaco_pct`, `descuento_package_pct`, `descuento_advanced_purchase_pct`, `appearances_pct`, `lose_rate_on_compete_pct`, `adjustment_pct_avg`, `flag_precio_bkg`, `flag_precio_compset`, `flag_opaco`, `flag_package`, `flag_genius_mayor_opaco`, `root_cause`, `quality_adjustment_level` |
| CALIDAD | 5 | `content_score`, `rate_score`, `star_rating`, `reviews_count`, `cancel_rate_pct` |

**Total = 59.** A 60ª coluna `perfil_ejemplo` (presente no CSV, ausente no dicionário, vazia) **não faz parte do modelo** — deve ser descartada na ingestão (ver §4.3).

### 4.2 Tipos semânticos

| Tipo | Campos | Representação canônica |
|---|---|---|
| Chave/texto (`varchar`) | `hotel_id`, `hotel_name`, `country_code`, `destiny_code`, `destiny`, `worst_ap_bkg_35d`, `worst_ap_compset`, `root_cause`, `perfil_ejemplo` | `str` (AP-range **permanece string**, ex. `"000-007"`, `"046-090"`) |
| Booleano | 6 `flag_*` | `bool | None` (normalizado de `"true"/"false"/""`) |
| Inteiro (`bigint`) | `searchers`, `bk_cy`, `bk_ly`, `rn_cy`, `rn_ly`, `reviews_count` | `int | None` |
| Decimal/percentual (`double`/`decimal`) | demais numéricos | `float | None` |

### 4.3 Transformações de ingestão (§5.3)

Regras **obrigatórias**, já implementadas em `schemas.normalize_value` e que devem ser preservadas em qualquer novo loader:

1. **NULL ≠ zero.** Célula vazia (`""`) → `None`. Nunca `0`. `0` é um valor real (ex.: "não vendeu nada no tramo"), `None` é ausência de dado (ex.: "sem compset comparável").
2. **Vírgula decimal e aspas de milhar.** `"1.234,56"` → `1234.56`. `"12,5"` → `12.5`. O parser trata o separador ambíguo (`.` como milhar vs decimal) de forma conservadora.
3. **AP-range como string.** `worst_ap_bkg_35d` / `worst_ap_compset` são intervalos de antecipação (`"000-007"`, `"046-090"`) — **nunca** converter para número.
4. **Booleano normalizado.** `"true"`/`"false"`/`""` → `True`/`False`/`None`.
5. **`snake_case` como contrato.** Todos os nomes de coluna em `snake_case`; é o que o código e o YAML esperam.
6. **Idioma derivado de `country_code`.** `BR` → `pt`, demais → `es`, `NULL` → `es` (regra de negócio, não inferência).
7. **Drop de coluna fora do dicionário.** `perfil_ejemplo` é descartada (ou explicitamente ignorada) porque não tem definição nem dado.

### 4.4 Formato de armazenamento

- **Hoje:** `data/hotels.csv` (uma linha por hotel; cabeçalho = 59 campos canônicos, após drop de `perfil_ejemplo`) + `data/field_dictionary.yaml` (dicionário).
- **Depois:** trocar o repositório por SQL (§8) mantendo o mesmo contrato `HotelRow = Mapping[str, Any]` e os mesmos nomes `snake_case`.

---

## 5. Métricas (§5.2)

### 5.1.1 Princípio: pré-computado vs runtime

- **Pré-computado (na tabela):** tudo que já vem como coluna da aba `2. Datos y query`. O assistente **lê**, não recalcula. Ex.: `gb_yoy_pct`, `delta_precio_compset_pct`, `adjustment_pct_avg`.
- **Runtime (derivado em Python):** apenas o que é **decisão de regra** (comparação com limiar) ou **formatação** (vírgula decimal, idioma). Ex.: `content_score < 0.70` → palanca "Completa tu ficha".

Nenhuma métrica nova é calculada pelo LLM. O LLM só narra o que `diagnose()` e a `HotelRow` já entregam.

### 5.1.2 Tabela de métricas por pergunta

A fonte de verdade do "quais dados cada pergunta precisa" é a coluna **`Columnas que necesita`** da aba `4. Preguntas` (transcrita abaixo na §7). As métricas envolvidas:

| Métrica | Campo(s) | Tipo | Pré/Runtime |
|---|---|---|---|
| Crescimento YoY (RN/GB/BK) | `rn_yoy_pct`, `gb_yoy_pct`, `bk_yoy_pct` | percentual | pré |
| Reservas futuras 90d vs LY | `rn_90d_cy`, `rn_90d_ly`, `rn_90d_vs_ly` | count + % | pré |
| Performance vs compset (90d) | `perf_rn_90d_cy`, `perf_compset_rn_90d_cy`, `flag_rn_below_compset` | índice + flag | pré |
| Crescimento hotel vs destino | `hotel_growth_pct`, `dest_growth_pct` | % | pré |
| Vendas últimos 35d | `gb_35d`, `bk_35d`, `rn_35d` | valor/count | pré |
| Conversão (busca→ficha→reserva) | `cvr_search_success`, `cvr_detail_success`, `cvr_total` | % | pré |
| Competitividade de preço | `delta_precio_compset_pct`, `target_asp`, `compset_asp_avg`, `flag_precio_compset` | % / valor | pré |
| Disparidade vs Booking | `total_lose_logueado_pct_35d`, `profundidad_total_bkg_35d`, `worst_ap_bkg_35d` | % / AP | pré |
| Descontos carregados | `descuento_opaco_pct`, `descuento_package_pct`, `descuento_advanced_purchase_pct`, `avg_genius_discount_pct` + flags | % | pré |
| Ajuste recomendado | `adjustment_pct_avg` | % | pré |
| Exposição / aparição | `searchers`, `detailers`, `appearances_pct`, `lose_rate_on_compete_pct` | count / % | pré |
| Qualidade | `content_score`, `rate_score`, `star_rating`, `reviews_count`, `cancel_rate_pct` | score/count/% | pré |
| **Diagnóstico (palancas)** | 13 regras sobre os campos acima | `Lever` | **runtime** |

### 5.1.3 Limiares (fonte única: `domain/thresholds.py`)

Proveniência `[MATERIAL]` (aba `3. Diccionario` / `5. Palancas`) e `[ENG]` (engenharia):

| Limiar | Valor | Proveniência |
|---|---|---|
| `content_score` baixo | `< 0.70` | MATERIAL |
| `rate_score` baixo | `< 7.5` | MATERIAL |
| `reviews_count` baixo | `< 50` | MATERIAL |
| `cancel_rate_pct` alto | `> 40` | MATERIAL |
| perda de comparação logada | `> 30` | MATERIAL |
| `delta_precio_compset_pct` alto | `> 5` | MATERIAL |
| `descuento_opaco_pct` insuficiente | `< 5` | MATERIAL |
| `descuento_package_pct` insuficiente | `< 10` | MATERIAL |
| Genius > opaco | `genius > opaco + 1` | MATERIAL |
| profundidade p/ campanha | `≥ 10` | MATERIAL |
| `lose_rate_on_compete_pct` alto | `> 30` | MATERIAL |
| queda YoY RN | `< -10` | MATERIAL |
| compset abaixo | ratio `< 0.95` | MATERIAL |
| `appearances_pct` baixo | `< 50` | ENG |
| `bk_35d` baixo (leitura não confiável) | `< 30` | ENG |

**Regra de fronteira:** comparações estritas (`<`/`>`). `0.70` **não** dispara a palanca; `0.699` dispara. Documentado e testado.

---

## 6. Camada semântica (§5.4)

A camada semântica é o **contrato entre dados e LLM**: o que a ferramenta `get_hotel_data(hotel_id)` expõe e os metadados de decisão.

### 6.1 Contrato de saída (o que o grafo monta)

```jsonc
{
  "hotel_id": "123456",
  "hotel_name": "Hotel Exemplo",
  "language": "es",                       // derivado de country_code
  "row": { /* 59 campos snake_case, tipos canônicos, NULL preservado */ },
  "diagnosis": {
    "levers": [
      { "name": "Completa tu ficha", "severity": "high", "evidence": {"content_score": 0.58} }
    ],
    "data_quality": { /* qualidade do adjustment_level + reviews_count */ },
    "confidence": "medium"
  },
  "thresholds": [ /* 14 Threshold com [MATERIAL]/[ENG] */ ],
  "exposed_fields": [ /* recorte do guardrail 1 (ver 6.3) */ ]
}
```

### 6.2 Metadados de palanca (aba `5. Palancas (plus)`)

As **9 palancas** são as ações recomendáveis. Cada uma tem `quando recomendar`, `colunas que justificam`, mensagem ES/PT e `lógica para o LLM`:

| # | Palanca | Gatilho principal (colunas) | Estado |
|---|---|---|---|
| 1 | Completa tu ficha | `content_score < 0.70` + `cvr_detail_success` baixo | En producción (solver) |
| 2 | Campaña Last Minute | `worst_ap = 000-007` | En producción (solver) |
| 3 | Campaña Anticipa y Ahorra | `worst_ap = 046-090` (+`descuento_advanced_purchase_pct` baixo) | En producción (solver) |
| 4 | Campaña genérica | flag de preço + profundidade `≥ 10` | En producción (solver) |
| 5 | Disponibilidad | `appearances_pct < 50` (inferência) | En producción (solver); detalhe fora da tabela |
| 6 | Optimiza tus tarifas (ajuste leve) | flags de preço + profundidade `< 10` + causa ≠ promoção | En producción (solver) |
| 7 | Optimiza tus tarifas (descuentos) | `flag_opaco` / `flag_genius_mayor_opaco` / `flag_package` | En producción (solver) |
| 8 | Sponsored Listings | `searchers` NULL/baixo + conversão razoável | En producción (solver) |
| 9 | Política de cancelación más flexible | `cvr_detail_success` baixo sem preço/conteúdo | Complementaria (não na tabela) |
| + | Pasaporte | brecha opaco vs compset por tramo | Catálogo; elegibilidade fora da tabela |

**Regras de associação (aba 5):**
- **Prioridade** (maior→menor): 1) Completa tu ficha, 2) Campaña, 3) Disponibilidad, 4) Optimiza tus tarifas, 5) Sponsored Listings.
- **Regra de ouro:** "Nunca levar mais tráfego a uma ficha que não converte." Resolver preço/conteúdo **antes** de Sponsored Listings.
- **Quando NÃO recomendar:** dado `NULL` ou causa mais provável ≠ palanca → dizer o que falta, não forçar.
- **Tono:** não prometer resultado; campanhas "podem" aumentar reservas, não "vão".

### 6.3 Guardrails (não-negociáveis, já implementados)

1. **Recorte de exposição:** o LLM só recebe os campos relevantes (`exposed_fields`), não os 59.
2. **Números pré-computados:** o LLM nunca calcula métrica.
3. **`NULL` nunca vira zero:** narração deve dizer "não temos esse dado".
4. **Limite de dados explícito:** perguntas "fora de alcance" (Q30–Q33) recebem resposta de limite, não número inventado.
5. **Validação numérica:** `check_numbers` + `check_years` antes de devolver; 1 retry.

---

## 7. Mapeamento pergunta → dados → resposta (§5.6)

Fonte: aba `4. Preguntas` (33 perguntas, coluna `Columnas que necesita` + `Cómo debería responder el chat` + `Tipo`). Tipos: **Diagnóstico**, **Descriptiva**, **Acción**, **Límite de datos**.

> Convenção: `Todas` = todos os 59 campos; `(no existe)` = dado não disponível na tabela (resposta de limite); `(restricción)` = restrição de privacidade/escopo.

| # | Pilar | Pergunta (resumo PT) | Colunas que precisa | Tipo |
|---|---|---|---|---|
| 1 | Visión general | Como está meu hotel no geral? | `gb_yoy_pct`, `rn_yoy_pct`, `rn_90d_vs_ly`, `flag_rn_below_compset`, `cvr_total`, `delta_precio_compset_pct`, `content_score`, `rate_score` | Diagnóstico |
| 2 | Visión general | Qual é o principal problema hoje? | Todas | Diagnóstico |
| 3 | Visión general | O que fazer primeiro para vender mais? | Todas + aba 5 | Acción |
| 4 | Reservas | Vendo mais ou menos que ano passado? | `rn_cy`, `rn_ly`, `rn_yoy_pct`, `gb_yoy_pct` | Descriptiva |
| 5 | Reservas | Como vêm as reservas p/ próximos 3 meses? | `rn_90d_cy`, `rn_90d_ly`, `rn_90d_vs_ly` | Descriptiva |
| 6 | Reservas | Vendo mais/menos que competidores? | `perf_rn_90d_cy`, `perf_compset_rn_90d_cy`, `flag_rn_below_compset` | Descriptiva |
| 7 | Reservas | Por que minhas vendas caíram? | `rn_yoy_pct`, `hotel_growth_pct`, `dest_growth_pct`, `searchers`, `cvr_total`, `delta_precio_compset_pct`, `rn_90d_vs_ly` | Diagnóstico |
| 8 | Reservas | Meu destino cresce mais que meu hotel? | `hotel_growth_pct`, `dest_growth_pct` | Descriptiva |
| 9 | Reservas | Quanto vendi nos últimos 35 dias? | `gb_35d`, `bk_35d`, `rn_35d` | Descriptiva |
| 10 | Reservas | Como me comparo ao destino em reservas? | `hotel_growth_pct`, `dest_growth_pct` | Límite de datos |
| 11 | Exposición | Quanta gente vê meu hotel? | `searchers`, `detailers` | Descriptiva |
| 12 | Exposición | Por que quase não apareço nas buscas? | `searchers`, `appearances_pct`, `flag_rn_below_compset` | Diagnóstico |
| 13 | Exposición | % das buscas que termina vendo a ficha? | `cvr_search_success`, `searchers`, `detailers` | Descriptiva |
| 14 | Conversión | Da gente que entra, quanta reserva? | `cvr_detail_success`, `detailers` | Descriptiva |
| 15 | Conversión | Entra muita gente mas não reserva, por quê? | `cvr_detail_success`, `delta_precio_compset_pct`, `flag_precio_bkg`, `content_score`, `rate_score` | Diagnóstico |
| 16 | Conversión | Minha conversão é boa? | `cvr_search_success`, `cvr_detail_success`, `cvr_total` | Límite de datos |
| 17 | Tarifas | Meu preço é competitivo? | `delta_precio_compset_pct`, `flag_precio_compset`, `target_asp`, `compset_asp_avg`, `total_lose_logueado_pct_35d`, `flag_precio_bkg` | Diagnóstico |
| 18 | Tarifas | Estou mais caro que a Booking? | `total_lose_logueado_pct_35d`, `profundidad_total_bkg_35d`, `worst_ap_bkg_35d` | Descriptiva |
| 19 | Tarifas | Em qual antecedência perco mais? | `worst_ap_bkg_35d`, `worst_ap_compset`, `profundidad_worst_ap_bkg_35d` | Diagnóstico |
| 20 | Tarifas | Quais descontos tenho e estão bons? | `descuento_opaco_pct`, `descuento_package_pct`, `descuento_advanced_purchase_pct`, `avg_genius_discount_pct`, `flag_opaco`, `flag_package`, `flag_genius_mayor_opaco` | Diagnóstico |
| 21 | Tarifas | Quanto baixar o preço p/ ganhar? | `adjustment_pct_avg`, `profundidad_total_compset`, `profundidad_total_bkg_35d` | Acción |
| 22 | Tarifas | Apareço muito mas perco, o que acontece? | `appearances_pct`, `lose_rate_on_compete_pct`, `root_cause` | Diagnóstico |
| 23 | Calidad | Minha ficha está completa? | `content_score` | Diagnóstico |
| 24 | Calidad | Minhas avaliações são boas? | `rate_score`, `reviews_count`, `star_rating` | Descriptiva |
| 25 | Calidad | Tenho muitos cancelamentos? | `cancel_rate_pct` | Descriptiva |
| 26 | Calidad | Por que cancelam tantas reservas? | `cancel_rate_pct` | Límite de datos |
| 27 | Palancas | Vale a pena fazer campanha? | `worst_ap_bkg_35d`, `profundidad_total_bkg_35d`, `root_cause`, `rn_90d_vs_ly` | Acción |
| 28 | Palancas | Vale a pena Sponsored Listings? | `searchers`, `appearances_pct`, `cvr_total` | Acción |
| 29 | Palancas | Qual desconto devo carregar? | `descuento_opaco_pct`, `avg_genius_discount_pct`, `flag_opaco` | Acción |
| 30 | Fuera de alcance | Qual minha ocupação / RevPAR? | (no existe) | Límite de datos |
| 31 | Fuera de alcance | De quais países vêm os hóspedes? | (no existe) | Límite de datos |
| 32 | Fuera de alcance | Qual preço exato para amanhã? | (no existe) | Límite de datos |
| 33 | Fuera de alcance | Como vai outro hotel do destino? | (restricción) | Límite de datos |

### 7.1 Notas de resposta por tipo

- **Descriptiva:** dar o dado nominal e a referência, sem julgar além do que a tabela permite. Ex.: Q11 "não há referência de destino, então não dá para dizer se é muito ou pouco".
- **Diagnóstico:** seguir o funil (exposição → conversão → reservas → causas em tarifas/qualidade) e **nomear uma única** causa principal com seus dados.
- **Acción:** uma única ação prioritária associada a uma palanca, com a métrica que a justifica.
- **Límite de datos:** declarar explicitamente o que a tabela não traz e oferecer o dado mais próximo disponível (ex.: Q30 → oferecer room nights + gross booking em vez de ocupação/RevPAR).

### 7.2 Regra de idioma (refletida na camada de dados)

A resposta é **PT-BR** se `country_code == "BR"`, **ES** nos demais casos (`NULL` → ES). Isso é decidido em `fetch_row` via `language_for()` e **não** depende do idioma da pergunta — é uma propriedade do hotel (o hoteleiro). O dicionário carrega definições em `es.*` e `pt.*` para o retrieval funcionar nos dois idiomas.

---

## 8. Abstração de dados (§5.5)

### 8.1 Protocolo atual

```python
@runtime_checkable
class HotelRepository(Protocol):
    def get(self, hotel_id: str) -> HotelRow | None: ...
    def find_by_name(self, name: str) -> list[HotelRow]: ...
    def all_ids(self) -> list[str]: ...
```

`CsvHotelRepository` é a implementação de hoje. A troca de backend exige **apenas** uma nova implementação do mesmo Protocol.

### 8.2 Evolução para backend SQL (PostgreSQL)

Motivado por: a anotação do time de que **não usam Databricks** (§2, discrepância 4), e a necessidade de servir muitos hotéis sem carregar CSV em memória.

```python
# Proposta de interface ampliada (não quebra o Protocol existente)
class DataLoader(Protocol):
    def get_hotel(self, hotel_id: str) -> HotelRow | None: ...
    def get_hotel_metrics(self, hotel_id: str) -> HotelRow | None: ...   # alias p/ retrocompat
    def get_destiny_reference(self, destiny_code: str) -> DestinyRef | None: ...
    def list_hotels(self) -> list[str]: ...
```

**Princípios:**
- `get_hotel` = lookup por chave (índice em `hotel_id`). Determinístico, O(1)/índice.
- `get_destiny_reference` = agregados do destino (comparação de tendência), quando o time expuser essa tabela; hoje não existe no material → devolve `None` e a resposta declara o limite.
- `list_hotels` = catálogo p/ resolver nome→id.
- A normalização (`normalize_value`) e os limiares (`thresholds.py`) **não mudam** na troca — são independentes do storage.

---

## 9. Plano de arquivos (§5.7)

### 9.1 Arquivos a criar

| Arquivo | Conteúdo | Prioridade |
|---|---|---|
| `docs/DATA_IMPLEMENTATION_PLAN.md` | este documento | ✅ feito |
| `scripts/regenerate_hotels_csv.py` | lê a aba `2. Datos y query` do xlsx e regenera `data/hotels.csv` (59 campos, drop `perfil_ejemplo`, normalização) | alta (desbloqueia o código) |
| `data/hotels.csv` | **regenerado** (hoje está deletado) | alta |
| `scripts/validate_data.py` | valida contagem de colunas (59), tipos, NULL vs zero, flags, AP-range | alta |
| `src/assistant_hotel/data/sql_repository.py` | implementação PostgreSQL do `HotelRepository` (opcional, pós-MVP) | baixa/média |
| `tests/test_csv_repository.py` (ampliar) | casos de vírgula decimal, aspas, NULL≠0, AP-range string | alta |
| `tests/test_ingestion.py` | garante que o CSV regenerado casa com o dicionário (59 campos) | alta |

### 9.2 Arquivos existentes que já cobrem o plano

`schemas.py`, `csv_repository.py`, `thresholds.py`, `rules.py`, `diagnosis.py`, `blocks.py`, `fields.py`, `language.py`, `retrieval/*`, `prompts/*`, `guardrails/*`, `graph.py`, `nodes/*` — mantidos; o plano **não** reescreve a lógica de domínio.

---

## 10. Plano de integração (§5.8)

### 10.1 Backend (LangChain/LangGraph)

- `build_deps()` já injeta `CsvHotelRepository` + `build_index` + `GenPlatLLM`. A troca para `SqlHotelRepository` é **uma linha** no wiring de dependências.
- `fetch_row` chama `HotelRepository.get(hotel_id)` e aplica `language_for(country_code)`.
- `assemble` chama `build_context(...)` que já monta fact sheet + thresholds + campos expostos.

### 10.2 Frontend

- O frontend envia `question` + `hotel_id` (ou `hotel_name`, resolvido por `resolve_hotel`). O `hotel_id` é a única chave; o backend responde `hotel_id`, `hotel_name`, `language`, `confidence`, `levers`, `data_quality`, `guardrail_flags`.

### 10.3 Pipeline de avaliação

- As 33 perguntas (`data/perguntas_eval.csv`) são o **set de avaliação**. Cada pergunta tem `Columnas que necesita` + resposta esperada — base para asserts de *cobertura de dados* e *tipo de resposta*.
- O validador numérico (`check_numbers`/`check_years`) roda **antes** de devolver; 1 retry.
- Regra de idioma é avaliada separadamente (PT-BR p/ BR, ES p/ demais).

### 10.4 System prompt

- `prompts/system_pt.md` / `system_es.md` já codificam as 8 regras invioláveis + estrutura de resposta + limite de ~500 palavras. A camada de dados alimenta o `fact_sheet` e o `thresholds` que entram no prompt montado.

---

## 11. Próximos passos

1. **Regenerar `data/hotels.csv`** a partir do xlsx (script `scripts/regenerate_hotels_csv.py`) — é o bloqueador imediato: o código não roda sem a tabela.
2. **Validar** contagem (59 campos), tipos e NULL≠0 com `scripts/validate_data.py` + testes.
3. **Rodar a suíte** (`uv run pytest`) para confirmar que a tabela regenerada é compatível com o código.
4. **Decidir versionamento** dos artefatos brutos: manter `data/*.xlsx` e `refs/` no repo ou movê-los para um storage privado (atenção à regra de não versionar material sensível).
5. **Avaliar** as 33 perguntas contra o pipeline (cobertura de dados + tipo de resposta + idioma).
6. **(Pós-MVP)** implementar `SqlHotelRepository` (PostgreSQL) atrás do mesmo `HotelRepository`, habilitando escala além do CSV — **não** Databricks (o time não usa).

---

### Anexo A — Proveniência dos limiares e das palancas

Todos os limiares vêm da aba `3. Diccionario` (colunas "Que es / Como leerlo") e da aba `5. Palancas (plus)` (colunas "Cuándo recomendarla" e "Lógica para el LLM"). Os marcados `[ENG]` são decisões de engenharia não presentes no material (limiar de confiabilidade de leitura), e estão documentados como tal em `domain/thresholds.py`. Nenhum limiar é inventado neste plano.

### Anexo B — Discrepâncias (repetição para rastreabilidade)

Ver §2 "Discrepâncias reportadas (PASSO 4)". Resumo: (1) nomes de `refs/` divergem do esperado e não há `/ref`; (2) `data/hotels.csv` deletado; (3) 60ª coluna `perfil_ejemplo` vazia e fora do dicionário; (4) "não usam Databricks" — alvo de troca é PostgreSQL, não Databricks.
