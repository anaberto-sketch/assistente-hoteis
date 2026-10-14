"""resolve_hotel + clarify.

`resolve_hotel` e o UNICO portao de entrada de hotel no grafo. Ele valida o id
contra o repositorio antes de emitir: assim `fetch_row` nunca precisa tratar
"hotel inexistente" e o grafo continua linear, com uma unica aresta condicional.

Ordem de resolucao:
  1. nome citado na pergunta  (o hoteleiro costuma nomear, nao dar ID)
  2. ID numerico citado na pergunta
  3. hotel do turno anterior  (perguntas de acompanhamento: "e o preco?")
"""

from __future__ import annotations

import re
from typing import Any

from ..data.repository import HotelRepository
from ..domain.models import HotelRow
from ..state import AssistantState

# IDs de hotel no material tem 6-7 digitos. O piso de 5 evita casar com
# quantidades soltas ("30000 reservas").
_ID_IN_QUESTION = re.compile(r"\b(\d{5,})\b")

# Sem hotel resolvido nao ha country_code, logo nao ha idioma derivavel. Em vez
# de adivinhar, a mensagem sai nos dois idiomas.
CLARIFY_MESSAGE = (
    "Não encontrei esse hotel na base. Diga o nome ou o ID do hotel.\n"
    "No encontré ese hotel en la base. Decí el nombre o el ID del hotel."
)


def _by_name(repository: HotelRepository, question: str) -> HotelRow | None:
    if not question.strip():
        return None
    candidates = repository.find_by_name(question)
    return candidates[0] if candidates else None


def _by_id(repository: HotelRepository, question: str) -> HotelRow | None:
    for match in _ID_IN_QUESTION.finditer(question):
        row = repository.get(match.group(1))
        if row is not None:
            return row
    return None


def make_resolve_node(repository: HotelRepository) -> Any:
    def resolve_hotel(state: AssistantState) -> dict[str, Any]:
        question = state.get("question") or ""
        previous = state.get("hotel_id")

        row = _by_name(repository, question) or _by_id(repository, question)
        if row is None and previous:
            row = repository.get(previous)

        if row is None:
            return {
                "hotel_id": None,
                "hotel_name": None,
                "resolution_error": CLARIFY_MESSAGE,
            }

        return {
            "hotel_id": str(row.get("hotel_id")),
            "hotel_name": row.get("hotel_name"),
            "resolution_error": None,
        }

    return resolve_hotel


def route_after_resolve(state: AssistantState) -> str:
    """A unica aresta condicional do grafo."""
    return "fetch_row" if state.get("hotel_id") else "clarify"


def make_clarify_node(repository: HotelRepository) -> Any:
    def clarify(state: AssistantState) -> dict[str, Any]:
        total = len(repository.all_ids())
        return {
            "answer": f"{CLARIFY_MESSAGE}\n\n({total} hotéis na base.)",
            "diagnosis": None,
            "guardrail_flags": [],
        }

    return clarify
