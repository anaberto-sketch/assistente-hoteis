# assistant-hotel

Chat onde o hoteleiro pergunta sobre a performance do seu hotel e recebe um diagnóstico com o que fazer para vender mais.

O time já gera recomendações com IA (os limiares estão materializados nas flags da tabela), mas não existia um jeito de o hoteleiro conversar sobre isso. Hoje a informação está presa numa linha de ~60 colunas que só quem escreveu o pipeline sabe ler.

Este projeto **não reimplementa o pipeline**. Ele reaproveita os limiares existentes, roda o diagnóstico em Python puro e usa o LLM só para narrar o que já foi calculado.

---

## Design em uma frase

**Agentes + Skills + MCP-ready, com diagnóstico determinístico.** As "skills" são os três blocos de regras do pipeline (CALIDAD, TARIFAS, RESERVAS) implementados em Python puro; o LLM é o narrador final, não decide nada; a camada de dados é um `Protocol` com duas implementações plugáveis (CSV hoje, MCP amanhã) — a troca não toca o grafo.

| Camada | O quê | Como |
|---|---|---|
| Agente orquestrador | Grafo linear LangGraph | `graph.py` — 1 aresta condicional (clarify) |
| Skills de diagnóstico | Regras puras em Python com procedência auditável | `domain/rules.py` + `domain/thresholds.py` (`[MATERIAL]`/`[ENG]`) |
| Retrieval de contexto | BM25 léxico sobre dicionário de 59 campos | `retrieval/` — nunca sobre a linha do hotel |
| Camada de dados | `HotelRepository` Protocol — MCP-ready | `data/csv_repository.py` (hoje) · `data/mcp_repository.py` (shape MCP) |
| Narração | Claude Sonnet via GenPlat, system prompt estruturado em XML tags | `llm.py` + `prompts/system_pt.md` + `system_es.md` |
| Guardrails | Numérico pós-hoc + idioma + truncamento + escopo + prompt injection | `guardrails/numeric.py` + regras no system prompt |

A trava de design está na linha "Skills de diagnóstico": no padrão clássico "LLM descobre o que está ruim", o modelo erra e inventa flags. Aqui as flags são aplicadas **antes** do LLM ver qualquer coisa — ele não tem como alucinar alavanca.

---

## A decisão central: lookup ≠ retrieval

O erro fácil aqui é jogar o CSV num vector store e fazer RAG sobre ele. Isso está errado por três motivos:

1. **A linha do hotel é um registro chaveado por `hotel_id`.** Busca por similaridade pode devolver **a linha de outro hotel** — o hoteleiro veria números do concorrente. É falha de isolamento de dados, não de qualidade.
2. **Não há "top-k".** É um registro completo. Rankear não faz sentido.
3. **Similaridade sobre números não tem semântica.**

Então a separação é:

| O quê | Como | Por quê |
|---|---|---|
| Dados do hotel | lookup determinístico (`HotelRepository.get`) | é registro chaveado, não documento |
| Como interpretar | RAG léxico (BM25) sobre o dicionário de campos | é o corpus de texto |
| Limiares do pipeline | dossiê estático, sempre injetado | um limiar não pode "não ser encontrado" |
| Diagnóstico | regras puras em Python | o LLM não deve *descobrir* flags |

O LLM é a **última** etapa e só narra fatos já calculados.

---

## Como rodar

```bash
uv sync --extra dev
```

> `uv sync` sem `--extra dev` **não instala o pytest** — o extra `dev` não entra por padrão. Se `uv run pytest` reclamar de módulo faltando, é isso.

**Credencial.** O GenPlat exige `Authorization: Bearer <token>`; o SDK Anthropic manda `x-api-key` por padrão e o gateway responde 401. O cliente usa `auth_token=`, que emite o header certo. O token vem do Tompero e nunca é logado.

```bash
tompero auth get requester-token   # se ainda não existir
uv run python -m assistant_hotel.llm --ping
```

**Sem credencial o assistente não cai.** O token é lido na primeira chamada ao modelo, não na inicialização — então `--list`, a resolução do hotel e todo o diagnóstico determinístico continuam funcionando. A resposta vira uma mensagem padrão que explica o que falta, e o CLI avisa no stderr logo que abre. Sem token, `--list` nem avisa: não precisa de LLM para listar.

**CLI.**

```bash
uv run python -m assistant_hotel.cli --list
uv run python -m assistant_hotel.cli --hotel "Windsor Tower Hotel" --ask "por que estou perdendo reservas?"
uv run python -m assistant_hotel.cli --hotel 345798 --ask "estou caro?" --context   # imprime o fact sheet
uv run python -m assistant_hotel.cli                                                # REPL
```

No REPL: `/hotel <nome|id>`, `/hoteis`, `/contexto`, `/ajuda`, `/sair`.

**API.**

```bash
uv run uvicorn assistant_hotel.api:app --port 8000
# ou: uv run python -m assistant_hotel.api

curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"como está meu hotel?","hotel_id":"345798"}'
```

`POST /chat` recebe `question`, `hotel_id` (opcional) e `history` (opcional). Devolve `answer`, `levers` (com `evidence` e `caveats`), `data_quality`, `language`, `confidence` e `guardrail_flags`. É stateless: o cliente reenvia `history` a cada turno, como o CLI faz internamente.

**Testes.**

```bash
uv run pytest
```

134 testes, nenhum toca a rede: o grafo é testado com um `FakeLLM` injetado. O marcador `integration` está registrado no `pyproject.toml` e excluído por padrão, mas **nenhum teste o usa hoje** — os testes contra o GenPlat real são manuais (`python -m assistant_hotel.llm --ping` e as execuções do CLI).

**Avaliação.** Os testes provam que o grafo funciona; eles não medem se a resposta presta. Isso é o que `evals/` faz — roda o grafo real contra o GenPlat e julga o texto com LLM-as-a-judge.

```bash
uv sync --extra eval
uv run python evals/build_cases.py           # perguntas_eval -> casos do eval
uv run python evals/run_eval.py --selftest   # o juiz discrimina?
uv run python evals/run_eval.py --limit 3    # o lote (66 casos: comece pequeno)
uv run python evals/dashboard.py             # http://127.0.0.1:8765
```

Os casos saem de `data/perguntas_eval.csv` (33 perguntas em PT e ES, cada uma com a rubrica de como o chat deveria responder), cruzadas com hotéis reais — sem `hotel_id` o grafo cai em `clarify` e o caso reprova sem nem chamar o LLM.

Fica fora do `testpaths` do pytest de propósito: `uv run pytest` nunca chama a rede. Ver [evals/README.md](evals/README.md).

**Configuração** (tudo por env var, nada hardcoded):

| Variável | Default |
|---|---|
| `ANTHROPIC_BASE_URL` | `https://generative-ai-platform-development.ifoodcorp.com.br/api/v2` |
| `ASSISTANT_HOTEL_MODEL` | `claude-sonnet-5-bedrock` |
| `ASSISTANT_HOTEL_TOKEN_PATH` | `~/.config/tompero/requester_token` |
| `ASSISTANT_HOTEL_DATA_DIR` | `data/` |
| `ASSISTANT_HOTEL_MAX_TOKENS` | `4000` |

---

## Observabilidade (Langfuse)

Cada request do agente vira um trace: a pergunta, a resposta, o hotel, as alavancas e as flags de guardrail. Dentro dele, uma span por nó do grafo e a span `generation` com modelo e tokens.

**É opcional e inerte.** Sem `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` no ambiente, nada é construído e nada é impresso — o resultado do grafo é idêntico. As credenciais vêm do ambiente (o SDK lê `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`/`LANGFUSE_HOST`); nenhum `.env` é lido pelo código:

```bash
uv run --env-file .env python -m assistant_hotel.cli --hotel 345798 --ask "estou caro?"
```

### O custo: quem calcula é o Langfuse

Não mandamos custo nenhum. Mandamos `model` + `usage_details`, e o Langfuse **infere** o custo casando o nome do modelo com as definições que ele mesmo mantém — assim um preço que mude lá não exige deploy nosso.

Só que `claude-sonnet-5-bedrock` é um nome do GenPlat, e **todos** os padrões de Claude na tabela do Langfuse são ancorados (`^...$`) — nenhum casa. Sem definição própria, a span sai com tokens e **sem custo**. Para resolver, uma vez só:

```bash
uv run --env-file .env python scripts/ensure_langfuse_model.py --dry-run   # mostra o que faria
uv run --env-file .env python scripts/ensure_langfuse_model.py             # cria
```

O script é idempotente (não faz nada se já houver um modelo que reconheça o nome) e registra o preço publicado do Sonnet 5 — **$2/MTok de entrada e $10/MTok de saída**, verificado em [claude.com/pricing](https://claude.com/pricing) em 14/10/2026. O cálculo do custo acontece na **ingestão**: defini-lo agora não reescreve spans já enviadas, só as novas.

Se o preço mudar, ajuste no Langfuse (Settings → Models) ou rode o script com `--input-price`/`--output-price`. Não colocamos preço no nosso código de propósito: um número nosso envelheceria sem ninguém notar.

---

## Topologia do grafo

Grafo linear com **uma única aresta condicional**. Sem multi-agente, sem supervisor, sem checkpointer.

```
START → resolve_hotel ─┬→ fetch_row → diagnose → retrieve_docs → assemble → generate → validate → END
                       └→ clarify ──────────────────────────────────────────────────────────────→ END
```

Duas escolhas de ordem que não são arbitrárias:

- **`diagnose` roda antes de `retrieve_docs`.** "Como está meu hotel?" não tem sinal léxico nenhum. Se o retrieval dependesse só do texto, não acharia nada. Com o diagnóstico primeiro, as alavancas acionadas **semeiam** a busca: todo campo que sustenta uma evidência entra no prompt por construção.
- **`clarify` é um curto-circuito sem LLM.** Perguntar "qual hotel?" não precisa de modelo.

`resolve_hotel` é o único portão de entrada de hotel, e valida o id contra o repositório antes de emitir. Ordem: nome citado → ID citado → hotel do turno anterior. É o último caso que faz "e o preço?" funcionar.

---

## Dados

`data/hotels.csv` — 20 hotéis, 60 colunas, transcritos verbatim do material do time.
`data/field_dictionary.yaml` — 59 campos (ES/PT) + sinônimos curados à mão.

Três detalhes de ingestão que valem registrar:

- O export usa **vírgula decimal** (`"0,01294181599"`) e aspas de milhar (`"1494870,06"`).
- Colunas de faixa (`worst_ap_bkg_35d` = `"046-090"`) permanecem **string** — parecem número, são rótulo.
- **String vazia vira `NULL`, e `NULL` nunca vira zero.** "Sem compset definido" é diferente de "compset igual a zero".

Os `synonyms` de cada campo **não** vêm do material — são curadoria manual, e são o que faz o retrieval funcionar em ES/PT ("conversão"/"conversión", "preço"/"precio").

---

## MCP-ready: a camada de dados é um Protocol

`HotelRepository` em `data/repository.py` é um `Protocol`. Hoje existem duas implementações:

| Implementação | Como funciona | Quando usar |
|---|---|---|
| `CsvHotelRepository` | lookup direto em `data/hotels.csv` | demo, dev, testes |
| `MCPHotelRepository` | mesma interface, mas chama tools nomeadas (`get_hotel_metrics`, `search_hotel_by_name`, `list_hotels`) com headers (`x-hotel-id`, `x-session-id`, `x-requester-token`) | integração com servidor MCP real |

A segunda hoje resolve localmente via `_call_tool` (não há servidor subido no hackathon). Trocar essa linha por `MultiServerMCPClient.call_tool(...)` é a única mudança para plugar num servidor MCP de verdade. O grafo, as regras, o retrieval e os guardrails não precisam saber da diferença.

**Por que isolar aqui:** quando o servidor MCP existir, ele é quem garante o isolamento por `hotel_id` (header, não payload). O cliente MCP não consegue ler dados de outro hotel ainda que mude o `hotel_id` no payload — o servidor valida pelos headers do token. É a mesma razão pela qual *lookup ≠ retrieval*: isolamento de dados por chave, não por similaridade.

---

## Guardrails

1. **Entrada recortada.** O prompt recebe `hotel_row[retrieved_fields ∪ lever.field_refs]`, não a linha inteira. Menos número disponível = menos número para inventar.
2. **Instrução explícita.** Usar só os números do FACT SHEET; `NULL` ≠ zero; não afirmar causalidade (`cancel_rate_pct` é de Q3/2025 e não tem comparativo com o destino); não converter janelas em dias para datas de calendário.
3. **Guardrail numérico pós-hoc.** A lista de números permitidos é extraída **do próprio prompt enviado** — não é uma lista paralela que pode divergir. Número sem lastro → uma regeneração com instrução mais restrita → se insistir, a resposta volta marcada em `guardrail_flags` e a interface avisa. Não reescrevemos a resposta por conta própria: trocar número alucinado por número nosso seria pior.
4. **Guardrail de idioma.** `country_code == "BR"` → `pt`; qualquer outro → `es`. Derivado do dado, não do texto da pergunta.
5. **Truncamento não é silencioso.** `stop_reason == "max_tokens"` vira flag visível. Um texto cortado no meio de uma frase parece uma resposta completa.
6. **Escopo funcional + imunidade a prompt injection.** O system prompt instrui o modelo a tratar o texto do hoteleiro, o histórico e o retorno de ferramentas como dados não confiáveis. Pedidos fora do contexto do hotel (política, religião, dados de outros hotéis, revelar instruções) recebem recusa breve e redirecionamento. Isso é defesa em texto — não substitui a validação de headers que o servidor MCP terá que fazer, mas evita a classe trivial de ataque numa demo pública.

---

## Limitações conhecidas

- **Afirmações booleanas não passam pelo guardrail.** O modelo pode dizer "`flag_precio_compset` = não" inferindo dos `ok_checks` em vez de ler o campo. Hoje ele acerta porque o fact sheet traz as regras avaliadas, mas não há verificação. Um guardrail de prosa para isso seria frágil; a alternativa é expor as flags sempre.
- **Amostra de 20 hotéis.** O `appearances_pct` e o `bk_35d` têm limiares marcados `[ENG]` em `domain/thresholds.py` — o material não dá número para esses casos. Precisam de calibração com o time antes de virarem regra de negócio.
- **O dicionário inteiro caberia no prompt** (59 campos). O retrieval entra como foco e ordenação, não como dependência de correção — as garantias de inclusão existem para que uma falha de recuperação nunca vire uma resposta errada.
- **Uma alavanca não é uma recomendação completa.** O material tem um pipeline de recomendações que vai além das flags; aqui só as alavancas deriváveis dos limiares documentados são calculadas.

---

## Estrutura

```
src/assistant_hotel/
├── config.py          # Settings + leitura do token
├── llm.py             # cliente do GenPlat (um dos dois pontos de rede)
├── tracing.py         # Langfuse: traces das requests do agente (o outro)
├── state.py           # TypedDicts do grafo
├── graph.py           # topologia + injeção de dependências
├── domain/            # Python puro: sem I/O, sem LLM
│   ├── thresholds.py  # fonte única dos limiares, com procedência [MATERIAL]/[ENG]
│   ├── rules.py       # rule_* : row -> Lever | None
│   ├── diagnosis.py   # motor: regras + modificadores -> Diagnosis
│   ├── blocks.py      # vocabulário de negócio -> bloco
│   └── fields.py      # carrega o dicionário
├── data/              # HotelRepository (Protocol): CsvHotelRepository + MCPHotelRepository (shape MCP)
├── retrieval/         # tokenize + BM25 + search com garantias
├── nodes/             # adaptadores finos domain/ → grafo
├── prompts/           # system_pt.md, system_es.md, render.py
├── guardrails/        # numeric.py
├── eval/              # checagens deterministicas, leitura do resultado e montagem dos casos
├── cli.py
└── api.py

evals/                 # harness de avaliacao: roda o grafo real e julga com DeepEval
├── build_cases.py     # data/perguntas_eval.csv -> cases.csv (rotacao de hoteis por pais)
├── run_eval.py        # CSV -> grafo -> juiz -> relatorio
├── dashboard.py       # servidor local: le results/ e dispara lotes
├── dashboard.html     # a interface
├── cases.csv          # os casos do eval (gerado pelo build_cases; versionado)
├── cases_exemplo.csv  # os 6 casos autorais, que exercitam regras especificas
└── results/           # saida (fora do git)

scripts/               # tarefas de operacao, rodadas a mao
└── ensure_langfuse_model.py  # cria no Langfuse o modelo que faz o custo aparecer
```

**Fronteiras:** `domain/` é puro e é o coração testável. `nodes/` são adaptadores finos. `retrieval/` conhece só o dicionário, **nunca** a linha do hotel. Os dois únicos pontos de rede são `llm.py` (GenPlat) e `tracing.py` (Langfuse) — e o segundo é inerte sem credencial.
