"""Tracing das requests do agente no Langfuse.

REGRA QUE GOVERNA ESTE MODULO: **sem credencial, isto e um no-op silencioso.**
Nenhuma linha e impressa, nenhum cliente e construido, e o resultado do grafo e
identico ao de nao existir tracing. Quem chama nunca precisa de `if`.

Por que checar a credencial ANTES de construir o cliente: `Langfuse()` sem
`public_key` **nao levanta**. Verificado no SDK 5.0.1 -- ele imprime
"Authentication error: Langfuse client initialized without public_key. Client
will be disabled." e devolve um cliente desligado. Essa linha sujaria o stdout
do CLI e o log do eval, entao nao chegamos a construir.

As credenciais vem do ambiente, com os nomes que o proprio SDK le
(`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` ou
`LANGFUSE_HOST`). Nada de `.env` e lido por este codigo -- quem quiser um arquivo
usa `uv run --env-file .env python ...`.

A forma das spans:

    request  (raiz)   pergunta, resposta, hotel, alavancas, flags de guardrail
      +- no           o que cada no do grafo devolveu
      +- generation   modelo, tokens, resposta  (dentro de `generate`)

Um rastro de observabilidade NUNCA pode custar a resposta do usuario: toda
chamada ao Langfuse esta sob try/except, e falha dele vira no-op.
"""

from __future__ import annotations

import contextlib
import os
import sys
from typing import Any, Callable, Iterator

# O SDK le exatamente estes nomes (langfuse/_client/environment_variables.py).
_CHAVES = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")

# Teto do que vai para a span. O fact sheet e o system prompt sao grandes; mandar
# inteiros em cada no infla o trace sem informar mais.
_LIMITE_TEXTO = 2000

_UNSET = object()
_cliente: Any = _UNSET


def enabled() -> bool:
    """Ha credencial no ambiente?

    E a checagem que decide tudo: `False` significa que o resto do modulo e
    inerte.
    """
    return all(os.environ.get(chave) for chave in _CHAVES)


def _construir() -> Any | None:
    if not enabled():
        return None
    try:
        from langfuse import Langfuse

        return Langfuse()
    except Exception:  # noqa: BLE001 - tracing nunca derruba a aplicacao
        return None


def client() -> Any | None:
    """Cliente singleton, ou `None` quando nao ha credencial.

    Resolvido na primeira USO, nao na montagem do grafo: o `default_graph()` e
    `lru_cache`d, e resolver na montagem congelaria o cliente para o processo.
    """
    global _cliente
    if _cliente is _UNSET:
        _cliente = _construir()
    return _cliente


def reset() -> None:
    """Esquece o cliente resolvido. Existe para os testes."""
    global _cliente
    _cliente = _UNSET


def flush() -> None:
    """Forca o envio do que esta no buffer.

    Processo curto (CLI) morre antes do flush periodico, e o trace se perde.
    """
    cli = client()
    if cli is None:
        return
    with contextlib.suppress(Exception):
        cli.flush()


def _resumir(valor: Any) -> Any:
    """Corta texto longo para a span nao virar um dump do prompt inteiro."""
    if isinstance(valor, str):
        if len(valor) <= _LIMITE_TEXTO:
            return valor
        return valor[:_LIMITE_TEXTO] + f"... [cortado, {len(valor)} chars]"
    if isinstance(valor, dict):
        return {chave: _resumir(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_resumir(item) for item in valor[:50]]
    return valor


class _NoOp:
    """Span que nao existe: aceita qualquer chamada e nao faz nada.

    Permite que o codigo de tracing seja escrito sem `if enabled()` em cada
    ponto -- o caminho sem credencial passa por aqui e segue igual.
    """

    def update(self, **_: Any) -> None: ...

    def end(self, **_: Any) -> None: ...

    def score(self, **_: Any) -> None: ...

    def score_trace(self, **_: Any) -> None: ...

    def start_as_current_observation(self, **kwargs: Any) -> Any:
        return observation(**kwargs)

    def __enter__(self) -> "_NoOp":
        return self

    def __exit__(self, *_: Any) -> bool:
        return False


@contextlib.contextmanager
def observation(name: str, **kwargs: Any) -> Iterator[Any]:
    """Abre uma span, ou entrega um no-op se o tracing estiver desligado.

    Abrir a span e o corpo ficam em try separados de proposito: se o Langfuse
    falhar ao ABRIR, entregamos o no-op e o trabalho real continua; se o corpo
    levantar, a excecao sobe normalmente (nao engolimos erro do grafo).
    """
    cli = client()
    if cli is None:
        yield _NoOp()
        return

    try:
        gerenciador = cli.start_as_current_observation(name=name, **kwargs)
        span = gerenciador.__enter__()
    except Exception:  # noqa: BLE001
        yield _NoOp()
        return

    erro: tuple[Any, Any, Any] = (None, None, None)
    try:
        yield span
    except BaseException:
        erro = sys.exc_info()
        raise
    finally:
        with contextlib.suppress(Exception):
            gerenciador.__exit__(*erro)


@contextlib.contextmanager
def _atributos(**kwargs: Any) -> Iterator[None]:
    """`propagate_attributes` do Langfuse, ou nada.

    E o que carrega session_id/user_id/tags/trace_name para o trace inteiro.
    """
    cli = client()
    if cli is None:
        yield
        return
    try:
        from langfuse import propagate_attributes

        # Chaves ausentes viram None e o SDK ignora; passar direto e mais
        # simples que montar o dict condicionalmente.
        with propagate_attributes(**kwargs):
            yield
    except Exception:  # noqa: BLE001
        yield


class TracedLLM:
    """Envolve um `LLMClient` e abre uma span `generation` por chamada.

    Preserva o Protocol `generate(system, messages) -> Completion`, entao o
    grafo nao sabe que existe tracing.

    O custo NAO e calculado aqui. Mandamos `model` + `usage_details` e deixamos
    o Langfuse precificar: ele casa o nome do modelo com as definicoes que ele
    proprio mantem, e um preco que mudasse la nao exigiria deploy nosso.

    Isso so vale se o nome casar com alguma definicao. `gpt-4.1` casa -- o
    Langfuse tem esse modelo na tabela dele, com o padrao ancorado
    `(?i)^(openai/)?(gpt-4.1)$`. Ja um nome que so existe no GenPlat nao casa:
    `claude-sonnet-5-bedrock`, por exemplo, nao bate com nenhum padrao de Claude
    (todos ancorados), e a span sairia com tokens e custo VAZIO, sem erro
    nenhum. Nesse caso a saida e definir o modelo em Settings -> Models, ou com
    `scripts/ensure_langfuse_model.py`. Preencher com um preco nosso seria pior:
    um numero inventado com cara de medido.
    """

    def __init__(self, inner: Any, model: str | None = None) -> None:
        self._inner = inner
        self._model = model or getattr(inner, "model", None)

    def generate(self, system: str, messages: list[dict[str, Any]]) -> Any:
        with observation(
            "generate",
            as_type="generation",
            model=self._model,
            input={"system": _resumir(system), "messages": _resumir(messages)},
        ) as span:
            try:
                completion = self._inner.generate(system, messages)
            except Exception as exc:
                span.update(
                    level="ERROR",
                    status_message=f"{type(exc).__name__}: {exc}",
                )
                raise
            span.update(
                output=completion.text,
                usage_details=completion.usage_details(),
                metadata={"stop_reason": completion.stop_reason},
            )
            return completion


def node_span(name: str, fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Envolve um no do grafo numa span.

    Grava o DELTA que o no devolveu, nao o estado inteiro: o estado acumula o
    system prompt e o fact sheet, e repetir isso em cada no infla o trace.
    """

    def envolvido(state: Any) -> Any:
        with observation(name) as span:
            resultado = fn(state)
            span.update(output=_resumir(resultado))
            return resultado

    envolvido.__name__ = f"traced_{name}"
    return envolvido


class TracedGraph:
    """Envolve o grafo compilado e abre o trace da request.

    A identidade da sessao vem do `config` do LangGraph (`config["metadata"]`),
    nao do `AssistantState`: o estado e do dominio e nao deve ganhar campo de
    observabilidade.
    """

    def __init__(self, compiled: Any, trace_name: str = "assistant-hotel") -> None:
        self._compiled = compiled
        self._trace_name = trace_name

    def __getattr__(self, item: str) -> Any:
        # `stream`, `get_graph`, etc. seguem funcionando sem envolucro.
        return getattr(self._compiled, item)

    def invoke(self, state: Any, config: Any = None) -> Any:
        meta = dict((config or {}).get("metadata") or {})

        with _atributos(
            session_id=meta.get("session_id"),
            user_id=meta.get("user_id"),
            tags=meta.get("tags"),
            trace_name=meta.get("trace_name") or self._trace_name,
            metadata={"case_id": meta["case_id"]} if meta.get("case_id") else None,
        ):
            with observation(
                self._trace_name,
                input={
                    "question": state.get("question"),
                    "hotel_id": state.get("hotel_id"),
                    "history": _resumir(state.get("history") or []),
                },
            ) as span:
                resultado = self._invoke(state, config)
                span.update(output=_resumo_da_resposta(resultado))
                return resultado

    def _invoke(self, state: Any, config: Any) -> Any:
        if config is None:
            return self._compiled.invoke(state)
        return self._compiled.invoke(state, config)


def _resumo_da_resposta(resultado: Any) -> dict[str, Any]:
    """O que interessa olhar depois: a resposta e por que ela saiu assim."""
    if not isinstance(resultado, dict):
        return {"resultado": _resumir(resultado)}

    diagnostico = resultado.get("diagnosis") or {}
    return {
        "answer": _resumir(resultado.get("answer")),
        "hotel_id": resultado.get("hotel_id"),
        "hotel_name": resultado.get("hotel_name"),
        "language": resultado.get("language"),
        "confidence": diagnostico.get("confidence"),
        "levers": [alavanca.get("id") for alavanca in diagnostico.get("levers", [])],
        "guardrail_flags": resultado.get("guardrail_flags") or [],
        "stop_reason": resultado.get("stop_reason"),
        "resolution_error": resultado.get("resolution_error"),
    }
