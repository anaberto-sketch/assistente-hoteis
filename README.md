# assistant-hotel

Chat onde o hoteleiro pergunta sobre a performance do seu hotel e recebe um diagnóstico com o que fazer para vender mais.

O time já gera recomendações com IA (os limiares estão materializados nas flags da tabela), mas não existia um jeito de o hoteleiro conversar sobre isso. Hoje a informação está presa numa linha de ~60 colunas que só quem escreveu o pipeline sabe ler.

Este projeto **não reimplementa o pipeline**. Ele reaproveita os limiares existentes, roda o diagnóstico em Python puro e usa o LLM só para narrar o que já foi calculado.

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

114 testes, nenhum toca a rede: o grafo é testado com um `FakeLLM` injetado. O marcador `integration` está registrado no `pyproject.toml` e excluído por padrão, mas **nenhum teste o usa hoje** — os testes contra o GenPlat real são manuais (`python -m assistant_hotel.llm --ping` e as execuções do CLI).
**Configuração** (tudo por env var, nada hardcoded):

| Variável | Default |
|---|---|
| `ANTHROPIC_BASE_URL` | `https://generative-ai-platform-development.ifoodcorp.com.br/api/v2` |
| `ASSISTANT_HOTEL_MODEL` | `claude-sonnet-5-bedrock` |
| `ASSISTANT_HOTEL_TOKEN_PATH` | `~/.config/tompero/requester_token` |
| `ASSISTANT_HOTEL_DATA_DIR` | `data/` |
| `ASSISTANT_HOTEL_MAX_TOKENS` | `4000` |

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

## Guardrails

1. **Entrada recortada.** O prompt recebe `hotel_row[retrieved_fields ∪ lever.field_refs]`, não a linha inteira. Menos número disponível = menos número para inventar.
2. **Instrução explícita.** Usar só os números do FACT SHEET; `NULL` ≠ zero; não afirmar causalidade (`cancel_rate_pct` é de Q3/2025 e não tem comparativo com o destino); não converter janelas em dias para datas de calendário.
3. **Guardrail numérico pós-hoc.** A lista de números permitidos é extraída **do próprio prompt enviado** — não é uma lista paralela que pode divergir. Número sem lastro → uma regeneração com instrução mais restrita → se insistir, a resposta volta marcada em `guardrail_flags` e a interface avisa. Não reescrevemos a resposta por conta própria: trocar número alucinado por número nosso seria pior.
4. **Guardrail de idioma.** `country_code == "BR"` → `pt`; qualquer outro → `es`. Derivado do dado, não do texto da pergunta.
5. **Truncamento não é silencioso.** `stop_reason == "max_tokens"` vira flag visível. Um texto cortado no meio de uma frase parece uma resposta completa.

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
├── llm.py             # ÚNICO módulo que fala com a rede
├── state.py           # TypedDicts do grafo
├── graph.py           # topologia + injeção de dependências
├── domain/            # Python puro: sem I/O, sem LLM
│   ├── thresholds.py  # fonte única dos limiares, com procedência [MATERIAL]/[ENG]
│   ├── rules.py       # rule_* : row -> Lever | None
│   ├── diagnosis.py   # motor: regras + modificadores -> Diagnosis
│   ├── blocks.py      # vocabulário de negócio -> bloco
│   └── fields.py      # carrega o dicionário
├── data/              # HotelRepository (Protocol) + implementação CSV
├── retrieval/         # tokenize + BM25 + search com garantias
├── nodes/             # adaptadores finos domain/ → grafo
├── prompts/           # system_pt.md, system_es.md, render.py
├── guardrails/        # numeric.py
├── cli.py
└── api.py
```

**Fronteiras:** `domain/` é puro e é o coração testável. `nodes/` são adaptadores finos. `retrieval/` conhece só o dicionário, **nunca** a linha do hotel. `llm.py` é o único ponto de rede.
