"""retrieve_docs: escolhe quais campos do dicionario entram no prompt.

Retrieval lexico (BM25) + metadados. As garantias de inclusao estao em
retrieval/index.py; aqui so montamos a query.

A query e a pergunta MAIS os campos que sustentam cada alavanca acionada. E isso
que garante que a evidencia de um diagnostico sempre chegue ao modelo, mesmo que
a pergunta nao cite nenhum desses campos.
"""

from __future__ import annotations

from typing import Any

from ..domain.blocks import blocks_for
from ..retrieval.index import DEFAULT_LIMIT, FieldIndex, search
from ..state import AssistantState


def make_retrieve_node(index: FieldIndex) -> Any:
    def retrieve_docs(state: AssistantState) -> dict[str, Any]:
        question = state.get("question") or ""
        diagnosis = state.get("diagnosis")
        lang = state.get("language") or "es"

        must_include: list[str] = []
        if diagnosis:
            for lever in diagnosis["levers"]:
                must_include.extend(lever["field_refs"])

        return {
            "retrieved_fields": search(
                index,
                query=question,
                lang=lang,
                must_include=must_include,
                blocks=blocks_for(question),
                limit=DEFAULT_LIMIT,
            )
        }

    return retrieve_docs
