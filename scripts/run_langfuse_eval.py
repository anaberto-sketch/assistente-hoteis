"""Roda o grafo real sobre o `golden_dataset` do Langfuse e julga cada resposta.

O tracing ja responde "o que o modelo recebeu e quanto custou". Isto responde a
outra metade: "a resposta esta boa?". Cada item do dataset tem uma PERGUNTA e uma
RUBRICA (o criterio de como o assistente deveria responder). O script passa a
pergunta pelo grafo de verdade, manda pergunta + resposta + rubrica para um juiz,
e devolve tudo -- resposta, nota e justificativa -- na aba de experiments do
Langfuse, ligado ao dataset.

    uv run --env-file .env python scripts/run_langfuse_eval.py --limit 2 --no-judge
    uv run --env-file .env python scripts/run_langfuse_eval.py

POR QUE O HOTEL PRECISA SER ESCOLHIDO AQUI. O dataset traz so a pergunta; sem
hotel o grafo NAO chama o LLM. `resolve_hotel` procura um hotel citado na
pergunta (por nome ou por ID) e, nao achando, cai em `clarify`, que devolve uma
mensagem fixa. O item seria "avaliado" sem o agente ter respondido nada, sem
geracao e sem custo -- um zero que nao mede o assistente. Por isso cada item
recebe um hotel, por rotacao determinista sobre a base.

A rotacao e o FALLBACK, nao uma imposicao: pergunta que cite um hotel pelo nome
ou pelo ID continua usando o hotel citado, porque essa resolucao vem antes no
grafo. So as perguntas genericas ("estou caro?") e que rodam contra o hotel
rotacionado.

O JUIZ E O PROPRIO LLM DO PROJETO, e nao vai envolvido em `TracedLLM`. Isso e
deliberado: a chamada do juiz nao vira span, entao o trace de cada item continua
mostrando so a geracao do agente -- e o custo na coluna `cost` e o custo do
assistente, nao o do avaliador. O gasto do juiz aparece so no GenPlat.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

DATASET = "golden_dataset"

# O default do SDK e 50. Isso dispara 50 chamadas simultaneas no GenPlat e leva
# 429 -- o limite do gateway e bem menor que o do Langfuse.
CONCORRENCIA_PADRAO = 4

JUIZ_SISTEMA = """\
Voce avalia respostas de um assistente de revenue para hoteis.

Recebe a PERGUNTA de um hoteleiro, a RESPOSTA que o assistente deu, e a RUBRICA
-- os criterios do que a resposta deveria conter.

De uma nota de 0 a 1 sobre o quanto a RESPOSTA satisfaz a RUBRICA:
  1.0  satisfaz todos os criterios
  0.5  satisfaz parte deles
  0.0  nao satisfaz nenhum, ou responde outra coisa

Regras:
  * Julgue so contra a RUBRICA. Nao invente criterio que ela nao tem.
  * Idioma diferente NAO e erro. A rubrica pode estar em espanhol e a resposta
    em portugues, ou o contrario -- julgue o conteudo, nao o idioma.
  * Resposta cortada no meio da frase e defeito, mesmo que o que veio antes
    esteja certo.

Responda SO com um objeto JSON, sem texto em volta:
{"nota": <numero entre 0 e 1>, "justificativa": "<uma frase curta>"}
"""

# Cerca de markdown em volta do JSON, que o modelo costuma acrescentar mesmo
# quando o prompt pede so o objeto.
_CERCA = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_OBJETO = re.compile(r"\{.*\}", re.DOTALL)


# --- o que o dataset traz ----------------------------------------------------

def _pergunta(item: Any) -> str:
    """A pergunta do item. O dataset a guarda como string."""
    valor = item.input
    if isinstance(valor, str):
        return valor
    # Defensivo: se algum item vier como objeto, procuramos as chaves usuais
    # antes de desistir -- `str(dict)` viraria uma pergunta sem sentido.
    if isinstance(valor, dict):
        for chave in ("question", "pergunta", "pregunta", "input"):
            if isinstance(valor.get(chave), str):
                return valor[chave]
    return str(valor)


def _rotacao(itens: list[Any], ids: list[str]) -> dict[str, str]:
    """item.id -> hotel_id, distribuindo os hoteis da base em rodizio.

    A ordenacao por id acontece AQUI, e nao em quem chama: sem ela a rotacao
    dependeria da ordem em que a API devolveu as paginas, e o mesmo item cairia
    num hotel diferente a cada execucao -- o que impediria comparar dois runs.
    """
    if not ids:
        raise RuntimeError("a base de hoteis esta vazia: nenhum item teria hotel")
    ordenados = sorted(itens, key=lambda item: item.id)
    return {item.id: ids[i % len(ids)] for i, item in enumerate(ordenados)}


def _saida(resultado: dict[str, Any]) -> dict[str, Any]:
    """Recorta o estado final para o que interessa guardar como output.

    Nao reaproveita `tracing._resumo_da_resposta`: aquela funcao corta texto em
    2000 chars, e o juiz precisa da resposta inteira. Tambem deixa de fora o
    `system_prompt` e o `fact_sheet`, que estao no estado final e inflariam o
    resultado do experimento sem informar nada.
    """
    diagnostico = resultado.get("diagnosis") or {}
    return {
        "answer": resultado.get("answer"),
        "hotel_id": resultado.get("hotel_id"),
        "hotel_name": resultado.get("hotel_name"),
        "language": resultado.get("language"),
        "confidence": diagnostico.get("confidence"),
        "levers": [alavanca.get("id") for alavanca in diagnostico.get("levers") or []],
        "guardrail_flags": resultado.get("guardrail_flags") or [],
    }


# --- o juiz ------------------------------------------------------------------

def _nota(valor: Any) -> float | None:
    """A nota, se estiver na escala pedida (0 a 1). Senao, None.

    Fora da escala nao e arredondado: um juiz que devolve 85 entendeu outra
    coisa, e transformar isso em 1.0 esconderia o problema atras de uma nota
    bonita.
    """
    # `float(True)` e 1.0: um `true` booleano viraria nota maxima calado.
    if isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= numero <= 1.0:
        return None
    return numero


def _ler_veredito(texto: str) -> tuple[float, str | None] | None:
    """Extrai (nota, justificativa) do texto do juiz, ou None se nao der.

    Tres tentativas, da mais provavel para a mais tolerante: o texto cru, o
    conteudo de uma cerca ```json, e o primeiro {...} do texto.
    """
    candidatos = [texto]
    cerca = _CERCA.search(texto)
    if cerca:
        candidatos.insert(0, cerca.group(1))
    objeto = _OBJETO.search(texto)
    if objeto:
        candidatos.append(objeto.group(0))

    for candidato in candidatos:
        try:
            dados = json.loads(candidato)
        except (ValueError, TypeError):
            continue
        if not isinstance(dados, dict):
            continue
        nota = _nota(dados.get("nota"))
        if nota is None:
            continue
        justificativa = dados.get("justificativa") or dados.get("justification")
        return nota, (str(justificativa).strip() if justificativa else None)
    return None


def _juiz(llm: Any, nome: str = "rubrica") -> Any:
    """Um evaluator do Langfuse que julga a resposta contra a rubrica do item."""

    def rubrica(
        *,
        input: Any,
        output: Any,
        expected_output: Any,
        metadata: Any = None,
        **_: Any,
    ) -> Any:
        from langfuse import Evaluation

        resposta = output.get("answer") if isinstance(output, dict) else output
        prompt = (
            f"PERGUNTA:\n{input}\n\n"
            f"RESPOSTA:\n{resposta}\n\n"
            f"RUBRICA:\n{expected_output}"
        )
        completion = llm.generate(
            JUIZ_SISTEMA, [{"role": "user", "content": prompt}]
        )

        veredito = _ler_veredito(completion.text)
        if veredito is None:
            # Devolver None vira ZERO avaliacoes naquele item (o SDK filtra o
            # que nao e `Evaluation`), e nao nota zero. Inventar 0.0 diria "o
            # agente errou" quando quem falhou foi o juiz.
            print(
                f"[aviso] o juiz nao devolveu JSON com nota em 0..1. "
                f"Bruto: {completion.text[:200]!r}",
                file=sys.stderr,
            )
            return None

        nota, justificativa = veredito
        return Evaluation(
            name=nome,
            value=nota,
            comment=justificativa,
            data_type="NUMERIC",
            metadata={"stop_reason": completion.stop_reason},
        )

    return rubrica


# --- a execucao --------------------------------------------------------------

def _task(graph: Any, rotacao: dict[str, str], session_id: str) -> Any:
    """O task do experimento: pergunta -> grafo -> resposta recortada."""

    def tarefa(*, item: Any, **_: Any) -> Any:
        estado = {
            "question": _pergunta(item),
            "history": [],
            "hotel_id": rotacao.get(item.id),
        }
        # As chaves lidas por `TracedGraph.invoke`: uma sessao por execucao
        # (agrupa os itens), a tag que separa o eval dos traces de producao, e o
        # id do item para casar trace e caso.
        config = {
            "metadata": {
                "session_id": session_id,
                "tags": ["eval"],
                "case_id": item.id,
            }
        }
        return _saida(graph.invoke(estado, config))

    return tarefa


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_langfuse_eval",
        description=f"Roda o grafo sobre o dataset {DATASET!r} e julga as respostas.",
    )
    parser.add_argument(
        "--limit", type=int, help="roda so os N primeiros itens (smoke test)"
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="roda o grafo sem julgar: testa so o encanamento do Langfuse",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=CONCORRENCIA_PADRAO,
        help=f"itens em paralelo (default: {CONCORRENCIA_PADRAO})",
    )
    args = parser.parse_args(argv)

    from assistant_hotel import tracing

    # Sem credencial o `Langfuse()` NAO levanta: ele imprime um aviso e devolve
    # um cliente desligado. O experimento rodaria inteiro e nao gravaria nada,
    # que e o pior desfecho possivel -- parece que funcionou.
    if not tracing.enabled():
        print(
            "Sem LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY o cliente fica desligado\n"
            "e o experimento nao grava nada. Rode com --env-file .env.",
            file=sys.stderr,
        )
        return 1

    from langfuse import Langfuse

    from assistant_hotel.data.csv_repository import CsvHotelRepository
    from assistant_hotel.graph import default_graph

    cliente = Langfuse()
    dataset = cliente.get_dataset(DATASET)

    # Ordenar por id antes de cortar faz o `--limit` ser sempre os MESMOS itens,
    # e nao os que a API devolveu primeiro.
    itens = sorted(dataset.items, key=lambda item: item.id)
    if args.limit:
        itens = itens[: args.limit]
    if not itens:
        print(f"O dataset {DATASET!r} esta vazio.", file=sys.stderr)
        return 1

    ids = sorted(CsvHotelRepository().all_ids())
    rotacao = _rotacao(itens, ids)
    dataset.items = itens

    session_id = uuid.uuid4().hex
    run_name = f"eval-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"

    print(f"dataset    : {DATASET} ({len(itens)} itens)")
    print(f"hoteis     : {len(ids)} na base, em rodizio")
    print(f"run        : {run_name}")
    print(f"sessao     : {session_id}")
    print(f"juiz       : {'nao' if args.no_judge else 'sim'}")
    print(f"paralelismo: {args.concurrency}")
    print()

    evaluators = []
    if not args.no_judge:
        from assistant_hotel.llm import GenPlatLLM

        # `GenPlatLLM` cru, sem `TracedLLM`: a chamada do juiz nao vira span e o
        # custo do item continua sendo o do assistente.
        evaluators.append(_juiz(GenPlatLLM()))

    # `run_experiment` e sincrono e ja chama `flush()` antes de retornar -- nao
    # precisa de flush manual aqui.
    resultado = dataset.run_experiment(
        name="rubrica",
        run_name=run_name,
        description="Grafo real sobre o golden_dataset, julgado contra a rubrica do item.",
        task=_task(default_graph(), rotacao, session_id),
        evaluators=evaluators,
        max_concurrency=args.concurrency,
        metadata={"dataset": DATASET, "rotacao": "por indice", "juiz": not args.no_judge},
    )

    print(resultado.format(include_item_results=True))
    if resultado.experiment_url:
        print()
        print(f"experiment: {resultado.experiment_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
