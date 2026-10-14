"""diagnose: roda as regras puras. Zero LLM.

Este no roda ANTES do retrieval, de proposito: as alavancas acionadas semeiam a
query de busca, o que faz "como esta meu hotel?" funcionar mesmo sem sinal
lexico nenhum na pergunta.
"""

from __future__ import annotations

from typing import Any

from ..domain.diagnosis import diagnose
from ..state import AssistantState


def diagnose_row(state: AssistantState) -> dict[str, Any]:
    row = state.get("hotel_row")
    hotel_id = state.get("hotel_id")
    if row is None or not hotel_id:
        raise RuntimeError("diagnose rodou sem hotel_row: a topologia do grafo mudou.")

    return {"diagnosis": diagnose(row, hotel_id)}
