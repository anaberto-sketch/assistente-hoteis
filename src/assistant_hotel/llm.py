"""Cliente do LLM via GenPlat. UNICO modulo que fala com a rede.

O gateway do GenPlat e compativel com a API Anthropic, mas com uma diferenca que
custa caro se passar batido: ele exige `Authorization: Bearer <token>`. O SDK
Anthropic envia `x-api-key` por padrao, e o gateway responde 401. Por isso
usamos `auth_token=`, que faz o SDK emitir o header certo (verificado em
anthropic/_client.py: `return {"Authorization": f"Bearer {auth_token}"}`).

O token nunca e logado.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Protocol

from .config import Settings, read_requester_token


@dataclass(frozen=True)
class Completion:
    """Resposta do modelo mais o motivo de ela ter terminado.

    `stop_reason` faz parte do contrato de proposito: quando o valor e
    "max_tokens" a resposta veio CORTADA, e devolver so o texto esconderia isso
    do usuario. Um texto truncado no meio de uma frase parece uma resposta
    completa.
    """

    text: str
    stop_reason: str | None = None

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"


class LLMClient(Protocol):
    """Interface minima. Os testes injetam um stub no lugar do GenPlat."""

    def generate(self, system: str, messages: list[dict[str, Any]]) -> Completion: ...


class GenPlatLLM:
    def __init__(self, settings: Settings | None = None) -> None:
        # Import tardio: manter o import no topo obrigaria a rede instalada
        # para rodar os testes de dominio.
        from anthropic import Anthropic

        self._settings = settings or Settings.from_env()
        self._client = Anthropic(
            base_url=self._settings.genplat_base_url,
            auth_token=read_requester_token(self._settings.token_path),
        )

    def generate(self, system: str, messages: list[dict[str, Any]]) -> Completion:
        # Sem `temperature`: o SDK anthropic 1.13.0 nao expoe parametros de
        # amostragem na Messages API (so `output_config.effort`/`format`).
        # Tampouco usamos `thinking`/`effort`, que o gateway pode nao aceitar.
        response = self._client.messages.create(
            model=self._settings.model,
            max_tokens=self._settings.max_tokens,
            system=system,
            messages=messages,
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        return Completion(text=text, stop_reason=getattr(response, "stop_reason", None))


def _ping() -> int:
    """Confere credencial, base_url e modelo contra o gateway real."""
    settings = Settings.from_env()
    print(f"base_url : {settings.genplat_base_url}")
    print(f"model    : {settings.model}")
    print(f"token    : {settings.token_path} (conteudo nao exibido)")

    client = GenPlatLLM(settings)
    completion = client.generate(
        system="Responda em uma palavra.",
        messages=[{"role": "user", "content": "Diga OK."}],
    )
    print(f"resposta : {completion.text!r}")
    print(f"stop     : {completion.stop_reason}")
    return 0


if __name__ == "__main__":
    if "--ping" in sys.argv:
        raise SystemExit(_ping())
    print("uso: python -m assistant_hotel.llm --ping")
    raise SystemExit(2)
