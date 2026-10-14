"""generate: a UNICA chamada ao LLM no caminho feliz.

Sem credencial, o no NAO derruba o grafo: devolve uma resposta padrao que diz o
que aconteceu e como resolver. O diagnostico deterministico ja foi calculado
antes daqui e continua valido -- perder a narrativa nao e motivo para perder
tambem as alavancas.
"""

from __future__ import annotations

from typing import Any

from ..config import MissingTokenError
from ..llm import LLMClient
from ..state import AssistantState

# Motivo gravado em `stop_reason` quando a resposta e a padrao. A API usa isso
# para distinguir "o modelo respondeu" de "nao deu para chamar o modelo".
MISSING_TOKEN_STOP_REASON = "missing_token"

FALLBACK_MESSAGE: dict[str, str] = {
    "pt": (
        "Não consegui gerar a análise em texto: a credencial de acesso ao "
        "modelo não está disponível.\n\n"
        "Rode `tompero auth get requester-token` para habilitá-la.\n\n"
        "O diagnóstico determinístico foi calculado normalmente — as alavancas "
        "acionadas e o nível de confiança estão na resposta."
    ),
    "es": (
        "No pude generar el análisis en texto: la credencial de acceso al "
        "modelo no está disponible.\n\n"
        "Ejecutá `tompero auth get requester-token` para habilitarla.\n\n"
        "El diagnóstico determinístico se calculó normalmente — las palancas "
        "accionadas y el nivel de confianza están en la respuesta."
    ),
}


def make_generate_node(llm: LLMClient) -> Any:
    def generate(state: AssistantState) -> dict[str, Any]:
        system = state.get("system_prompt")
        if not system:
            raise RuntimeError("generate rodou sem system_prompt.")

        messages: list[dict[str, Any]] = list(state.get("history") or [])
        messages.append({"role": "user", "content": state.get("question") or ""})

        try:
            completion = llm.generate(system, messages)
        except MissingTokenError:
            lang = state.get("language") or "es"
            return {
                "answer": FALLBACK_MESSAGE[lang],
                "stop_reason": MISSING_TOKEN_STOP_REASON,
            }

        return {"answer": completion.text, "stop_reason": completion.stop_reason}

    return generate
