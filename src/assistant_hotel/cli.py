"""REPL do assistente.

O historico e o hotel atual vivem AQUI, nao no grafo: a API e stateless pelo
mesmo motivo (o SDK Anthropic exige reenviar o historico a cada chamada). O grafo
recebe `history` e devolve a resposta; quem costura os turnos e a interface.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Sequence

from .data.repository import HotelRepository
from .graph import Deps, build_deps, build_graph
from .state import AssistantState

HELP = """\
Comandos:
  /hotel <nome|id>   troca o hotel da conversa
  /hoteis            lista os hoteis da base
  /contexto          mostra o prompt que foi montado na ultima resposta
  /ajuda             esta ajuda
  /sair              encerra

Qualquer outra linha e tratada como pergunta sobre o hotel atual.
"""


def _resolve_start_hotel(repository: HotelRepository, term: str) -> str | None:
    row = repository.get(term)
    if row is not None:
        return str(row.get("hotel_id"))
    matches = repository.find_by_name(term)
    return str(matches[0].get("hotel_id")) if matches else None


def _print_result(result: dict[str, Any], show_context: bool = False) -> None:
    diagnosis = result.get("diagnosis")
    if diagnosis:
        levers = diagnosis["levers"]
        resumo = (
            ", ".join(f"{lv['id']}({lv['severity']})" for lv in levers)
            or "nenhuma alavanca acionada"
        )
        # O hotel vai em toda resposta: sem isso, uma pergunta que nao resolve
        # para nenhum hotel seria respondida sobre o hotel do turno anterior
        # sem o usuario perceber.
        hotel = result.get("hotel_name") or result.get("hotel_id")
        print(f"[{hotel} | {resumo} | confiança: {diagnosis['confidence']}]")

    print()
    print(result.get("answer") or "(sem resposta)")

    for flag in result.get("guardrail_flags") or []:
        print(f"\n[guardrail] {flag}", file=sys.stderr)

    if show_context and result.get("fact_sheet"):
        print("\n" + "-" * 72)
        print(result["fact_sheet"])


def _ask(
    graph: Any,
    question: str,
    hotel_id: str | None,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    state: AssistantState = {"question": question, "history": history}
    if hotel_id:
        # Turno anterior ja resolvido: reaproveita para "e o preco?" funcionar.
        state["hotel_id"] = hotel_id
    return graph.invoke(state)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="assistant-hotel",
        description="Chat de performance hoteleira sobre o pipeline de recomendações.",
    )
    parser.add_argument("--hotel", help="hotel_id ou nome para começar a conversa")
    parser.add_argument("--ask", help="faz uma pergunta, imprime a resposta e sai")
    parser.add_argument("--list", action="store_true", help="lista os hotéis da base")
    parser.add_argument(
        "--context", action="store_true", help="imprime o fact sheet de cada resposta"
    )
    args = parser.parse_args(argv)

    deps: Deps = build_deps()

    if args.list:
        for hotel_id in deps.repository.all_ids():
            row = deps.repository.get(hotel_id) or {}
            print(f"{hotel_id}  {row.get('hotel_name')}  ({row.get('country_code')})")
        return 0

    graph = build_graph(deps)
    history: list[dict[str, Any]] = []
    hotel_id: str | None = None

    if args.hotel:
        hotel_id = _resolve_start_hotel(deps.repository, args.hotel)
        if hotel_id is None:
            print(f"Não encontrei nenhum hotel para {args.hotel!r}.", file=sys.stderr)
            return 1

    if args.ask:
        result = _ask(graph, args.ask, hotel_id, history)
        _print_result(result, args.context)
        return 0

    print("assistant-hotel — pergunte sobre o desempenho do seu hotel.")
    print(HELP)

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not line:
            continue
        if line in {"/sair", "/exit", "/quit"}:
            return 0
        if line in {"/ajuda", "/help"}:
            print(HELP)
            continue
        if line == "/hoteis":
            for hid in deps.repository.all_ids():
                row = deps.repository.get(hid) or {}
                marker = "*" if hid == hotel_id else " "
                print(f"{marker} {hid}  {row.get('hotel_name')}  ({row.get('country_code')})")
            continue
        if line.startswith("/hotel"):
            term = line[len("/hotel") :].strip()
            if not term:
                print("uso: /hotel <nome|id>")
                continue
            resolved = _resolve_start_hotel(deps.repository, term)
            if resolved is None:
                print(f"Não encontrei nenhum hotel para {term!r}.")
                continue
            hotel_id = resolved
            history = []
            row = deps.repository.get(hotel_id) or {}
            print(f"Hotel: {row.get('hotel_name')} ({hotel_id}) — histórico reiniciado.")
            continue

        result = _ask(graph, line, hotel_id, history)
        _print_result(result, args.context)

        # Só memoriza o hotel quando a resolução deu certo: um turno de
        # esclarecimento não pode apagar o hotel da conversa.
        if result.get("hotel_id"):
            hotel_id = result["hotel_id"]

        answer = result.get("answer")
        if answer:
            history.append({"role": "user", "content": line})
            history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    raise SystemExit(main())
