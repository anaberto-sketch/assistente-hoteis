"""API fina sobre o MESMO grafo do CLI. Nenhuma regra de negocio aqui.

Stateless por construcao: o cliente manda `history` a cada chamada, exatamente
como o CLI faz internamente. Assim nao ha sessao para sincronizar.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .graph import default_graph
from .state import AssistantState

app = FastAPI(
    title="assistant-hotel",
    version="0.1.0",
    description="Chat sobre a performance de um hotel, sobre o pipeline de recomendações.",
)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Pergunta do hoteleiro.")
    hotel_id: str | None = Field(
        default=None,
        description="ID do hotel. Em turnos seguintes, repita o ID devolvido antes.",
    )
    history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Turnos anteriores no formato {'role', 'content'}.",
    )
    session_id: str | None = Field(
        default=None,
        description=(
            "Agrupa turnos da mesma conversa no Langfuse. Opcional: sem ele, "
            "cada request vira um trace proprio."
        ),
    )


class LeverOut(BaseModel):
    id: str
    block: str
    severity: str
    rule: str
    evidence: dict[str, Any]
    caveats: list[str]


class ChatResponse(BaseModel):
    answer: str
    hotel_id: str | None = None
    hotel_name: str | None = None
    language: str | None = None
    confidence: str | None = None
    levers: list[LeverOut] = Field(default_factory=list)
    data_quality: list[str] = Field(default_factory=list)
    guardrail_flags: list[str] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    state: AssistantState = {
        "question": request.question,
        "history": request.history,
    }
    if request.hotel_id:
        state["hotel_id"] = request.hotel_id

    try:
        result = default_graph().invoke(
            state,
            {"metadata": {"session_id": request.session_id}}
            if request.session_id
            else None,
        )
    except FileNotFoundError as exc:
        # Token do Tompero ausente: e indisponibilidade, nao erro do cliente.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    diagnosis = result.get("diagnosis")
    return ChatResponse(
        answer=result.get("answer") or "",
        hotel_id=result.get("hotel_id"),
        hotel_name=result.get("hotel_name"),
        language=result.get("language"),
        confidence=diagnosis["confidence"] if diagnosis else None,
        levers=[
            LeverOut(
                id=lever["id"],
                block=lever["block"],
                severity=lever["severity"],
                rule=lever["rule"],
                evidence=lever["evidence"],
                caveats=lever["caveats"],
            )
            for lever in (diagnosis["levers"] if diagnosis else [])
        ],
        data_quality=diagnosis["data_quality"] if diagnosis else [],
        guardrail_flags=result.get("guardrail_flags") or [],
    )


def main() -> None:
    import uvicorn

    uvicorn.run("assistant_hotel.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
