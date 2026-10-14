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
    # Uso vem do provedor e pode faltar (o FakeLLM dos testes nao preenche).
    # Por isso os defaults sao None, e nao 0: "nao sei" e diferente de "zero".
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"

    def usage_details(self) -> dict[str, int]:
        """Uso no formato que o Langfuse espera: `input`/`output`/`total`.

        Nao e o nome do SDK anthropic (`input_tokens`/`output_tokens`) de
        proposito -- verificado em langfuse/openai.py, que monta
        `{"input": usage_dict["prompt_tokens"]}`.

        Devolve vazio quando o provedor nao informou uso: melhor sem custo do
        que com custo inventado.
        """
        if self.input_tokens is None and self.output_tokens is None:
            return {}
        entrada = self.input_tokens or 0
        saida = self.output_tokens or 0
        return {"input": entrada, "output": saida, "total": entrada + saida}


class LLMClient(Protocol):
    """Interface minima. Os testes injetam um stub no lugar do GenPlat."""

    def generate(self, system: str, messages: list[dict[str, Any]]) -> Completion: ...


class GenPlatLLM:
    """Cliente do GenPlat com credencial PREGUICOSA.

    O token so e lido na primeira chamada, nunca no construtor. Isso mantem o
    CLI e a API de pe sem credencial: listar hoteis, resolver o hotel e rodar o
    diagnostico deterministico nao precisam de LLM -- so a narrativa precisa.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings.from_env()
        self._client: Any = None

    @property
    def model(self) -> str:
        """Nome do modelo, para a span de geracao do Langfuse."""
        return self._settings.model

    def _connect(self) -> Any:
        if self._client is None:
            # Import tardio: manter o import no topo obrigaria a rede instalada
            # para rodar os testes de dominio.
            from anthropic import Anthropic

            self._client = Anthropic(
                base_url=self._settings.genplat_base_url,
                auth_token=read_requester_token(self._settings.token_path),
            )
        return self._client

    def generate(self, system: str, messages: list[dict[str, Any]]) -> Completion:
        # Sem `temperature`: o SDK anthropic 1.13.0 nao expoe parametros de
        # amostragem na Messages API (so `output_config.effort`/`format`).
        # Tampouco usamos `thinking`/`effort`, que o gateway pode nao aceitar.
        response = self._connect().messages.create(
            model=self._settings.model,
            max_tokens=self._settings.max_tokens,
            system=system,
            messages=messages,
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        usage = getattr(response, "usage", None)
        return Completion(
            text=text,
            stop_reason=getattr(response, "stop_reason", None),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )


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
