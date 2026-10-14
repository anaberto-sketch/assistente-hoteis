"""validate: guardrail numerico pos-hoc, com UMA regeneracao.

Valida contra o system prompt que foi realmente enviado, entao o que se checa e
exatamente o que o modelo teve a disposicao -- nao uma lista paralela que pode
divergir do prompt.

Uma unica tentativa extra: se o modelo insistir no numero sem lastro, a resposta
volta marcada em `guardrail_flags` e quem exibe (CLI/API) avisa o usuario. Nao
reescrevemos a resposta por conta propria: trocar numero alucinado por numero
nosso seria pior.
"""

from __future__ import annotations

from typing import Any

from ..guardrails.numeric import check_numbers, check_years
from ..llm import LLMClient
from ..state import AssistantState

RETRY_INSTRUCTION: dict[str, str] = {
    "pt": (
        "Sua resposta citou números ou datas que NÃO aparecem no FACT SHEET: "
        "{offenders}. Reescreva a resposta usando apenas números e datas que "
        "apareçam no FACT SHEET. Se um dado não estiver lá, diga que não está "
        "disponível. Não converta janelas em dias (\"90 dias\") em datas."
    ),
    "es": (
        "Tu respuesta citó números o fechas que NO aparecen en el FACT SHEET: "
        "{offenders}. Reescribe la respuesta usando solamente números y fechas que "
        "aparezcan en el FACT SHEET. Si un dato no está ahí, decí que no está "
        "disponible. No conviertas ventanas en días (\"90 días\") a fechas."
    ),
}


def make_validate_node(llm: LLMClient) -> Any:
    def validate(state: AssistantState) -> dict[str, Any]:
        answer = state.get("answer") or ""
        source = state.get("system_prompt") or ""
        lang = state.get("language") or "es"

        # Resposta cortada pelo teto de tokens e um defeito visivel: o texto
        # termina no meio de uma frase e parece completo. Nao vale regenerar --
        # a segunda tentativa bateria no mesmo teto.
        truncated = state.get("stop_reason") == "max_tokens"

        offenders = check_numbers(answer, source) + check_years(answer, source)
        if not offenders:
            if truncated:
                return {
                    "guardrail_flags": [
                        "Resposta truncada pelo limite de tokens: o texto termina "
                        "no meio. Aumente ASSISTANT_HOTEL_MAX_TOKENS."
                    ]
                }
            return {"guardrail_flags": []}

        flags = [
            "Números ou datas sem lastro no fact sheet na 1a versão: "
            + ", ".join(offenders)
            + " — resposta regenerada."
        ]
        if truncated:
            flags.append("A 1a versão também veio truncada pelo limite de tokens.")

        messages: list[dict[str, Any]] = list(state.get("history") or [])
        messages.append({"role": "user", "content": state.get("question") or ""})
        messages.append({"role": "assistant", "content": answer})
        messages.append(
            {
                "role": "user",
                "content": RETRY_INSTRUCTION[lang].format(
                    offenders=", ".join(offenders)
                ),
            }
        )

        retry = llm.generate(source, messages)
        if not retry.text:
            return {"guardrail_flags": flags + ["A regeneração voltou vazia."]}

        if retry.truncated:
            flags.append("A 2a versão também veio truncada pelo limite de tokens.")

        still = check_numbers(retry.text, source) + check_years(retry.text, source)
        if still:
            flags.append(
                "A 2a versão ainda cita números ou datas sem lastro: "
                + ", ".join(still)
            )

        return {
            "answer": retry.text,
            "stop_reason": retry.stop_reason,
            "guardrail_flags": flags,
        }

    return validate
