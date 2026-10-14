"""Idioma da resposta, derivado deterministicamente do pais do hotel.

Regra do material: "Define el idioma de la respuesta: BR en portugues, el resto
en espanol." Nao ha LLM nesta decisao.
"""

from __future__ import annotations

from ..state import Lang

PORTUGUESE_COUNTRY = "BR"


def language_for(country_code: str | None) -> Lang:
    """BR -> pt; qualquer outro pais (ou ausente) -> es."""
    if country_code is None:
        return "es"
    return "pt" if country_code.strip().upper() == PORTUGUESE_COUNTRY else "es"
