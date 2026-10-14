"""fetch_row: lookup deterministico da linha do hotel.

Isto NAO e retrieval. A linha e um registro chaveado por `hotel_id`; buscar por
similaridade poderia devolver a linha de OUTRO hotel. Aqui e `get(id)` e pronto.
"""

from __future__ import annotations

from typing import Any

from ..data.repository import HotelRepository
from ..domain.language import language_for
from ..state import AssistantState


def make_fetch_node(repository: HotelRepository) -> Any:
    def fetch_row(state: AssistantState) -> dict[str, Any]:
        hotel_id = state.get("hotel_id")
        row = repository.get(hotel_id) if hotel_id else None
        if row is None:
            # resolve_hotel ja validou o id contra o mesmo repositorio: chegar
            # aqui e bug de programacao, nao erro do usuario.
            raise RuntimeError(
                f"hotel_id={hotel_id!r} passou pela resolucao mas nao existe no "
                "repositorio. O portao de resolucao esta furado."
            )

        return {
            "hotel_row": dict(row),
            "hotel_name": row.get("hotel_name"),
            "language": language_for(row.get("country_code")),
        }

    return fetch_row
