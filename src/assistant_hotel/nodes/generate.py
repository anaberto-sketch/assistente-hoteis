"""generate: a UNICA chamada ao LLM no caminho feliz."""

from __future__ import annotations

from typing import Any

from ..llm import LLMClient
from ..state import AssistantState


def make_generate_node(llm: LLMClient) -> Any:
    def generate(state: AssistantState) -> dict[str, Any]:
        system = state.get("system_prompt")
        if not system:
            raise RuntimeError("generate rodou sem system_prompt.")

        messages: list[dict[str, Any]] = list(state.get("history") or [])
        messages.append({"role": "user", "content": state.get("question") or ""})

        completion = llm.generate(system, messages)
        return {"answer": completion.text, "stop_reason": completion.stop_reason}

    return generate
