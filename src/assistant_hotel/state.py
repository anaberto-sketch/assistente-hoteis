"""Schema do estado do grafo.

`NotRequired` marca o que os nos preenchem; o que nao tem marcacao e entrada
obrigatoria da invocacao.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

Severity = Literal["info", "low", "medium", "high"]
Confidence = Literal["low", "medium", "high"]
Lang = Literal["pt", "es"]

# Severidades ordenadas para poder ordenar as alavancas.
SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2, "info": 3}


class FieldDoc(TypedDict):
    """Um campo do dicionario, como entra no prompt."""

    field: str
    block: str
    definition: str
    how_to_read: str
    score: float  # relevancia BM25; inf = inclusao garantida


class Lever(TypedDict):
    """Uma alavanca acionada pelo diagnostico deterministico."""

    id: str
    block: str
    severity: Severity
    rule: str
    field_refs: list[str]
    evidence: dict[str, Any]  # SOMENTE valores vindos da linha do hotel
    message_pt: str
    message_es: str
    caveats: list[str]


class Diagnosis(TypedDict):
    hotel_id: str
    levers: list[Lever]
    ok_checks: list[str]
    data_quality: list[str]
    confidence: Confidence


class Threshold(TypedDict):
    """Um limiar do pipeline, para o dossie estatico."""

    id: str
    block: str
    rule: str
    meaning_pt: str
    meaning_es: str


class AssistantState(TypedDict):
    # --- entrada ---
    question: str
    history: list[dict[str, Any]]

    # --- resolucao do hotel ---
    hotel_id: NotRequired[str | None]
    hotel_name: NotRequired[str | None]
    resolution_error: NotRequired[str | None]

    # --- dados ---
    hotel_row: NotRequired[dict[str, Any] | None]
    diagnosis: NotRequired[Diagnosis | None]

    # --- retrieval ---
    retrieved_fields: NotRequired[list[FieldDoc]]
    thresholds: NotRequired[list[Threshold]]

    # --- montagem e saida ---
    language: NotRequired[Lang]
    fact_sheet: NotRequired[str]
    # Recorte da linha que foi para o prompt. Guardado para o guardrail numerico
    # validar contra exatamente o que o modelo viu, sem recalcular.
    exposed: NotRequired[dict[str, Any]]
    system_prompt: NotRequired[str]
    answer: NotRequired[str | None]
    # Motivo de o modelo ter parado ("max_tokens" = resposta cortada).
    stop_reason: NotRequired[str | None]
    guardrail_flags: NotRequired[list[str]]
