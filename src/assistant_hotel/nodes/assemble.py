"""assemble: monta o prompt final (fact sheet + dicionario + limiares + idioma).

Este no e o unico lugar que decide o que o modelo pode ver. Aplicar o recorte
aqui (e nao no `generate`) mantem `generate` burro e o guardrail numerico
alinhado com o que realmente foi enviado.
"""

from __future__ import annotations

from typing import Any

from ..domain.thresholds import threshold_dossier
from ..prompts.render import build_context
from ..state import AssistantState


def assemble_prompt(state: AssistantState) -> dict[str, Any]:
    row = state.get("hotel_row")
    diagnosis = state.get("diagnosis")
    if row is None or diagnosis is None:
        raise RuntimeError("assemble rodou sem hotel_row/diagnosis.")

    lang = state.get("language") or "es"
    fields = state.get("retrieved_fields") or []
    thresholds = threshold_dossier()

    system, fact_sheet, exposed = build_context(
        lang, row, diagnosis, fields, thresholds
    )

    return {
        "system_prompt": system,
        "fact_sheet": fact_sheet,
        "exposed": exposed,
        "thresholds": thresholds,
    }
