"""Diz POR QUE as requests nao estao chegando no Langfuse.

O tracing e um no-op silencioso quando falta credencial: nada e enviado e nada e
impresso. Isso e proposital -- observabilidade nao pode derrubar o chat -- mas e
pessimo para diagnosticar. Este script torna o silencio visivel.

Ele roda a cadeia na ordem em que ela pode falhar, e para no primeiro degrau que
quebra:

  1. as variaveis LANGFUSE_* estao no ambiente?  (sem elas, no-op)
  2. a credencial e aceita pelo servidor?        (chave rotacionada cai aqui)
  3. o grafo responde?
  4. o trace DESTA execucao chegou?
  5. o que o SERVIDOR guardou de cada span       (o input chegou la?)

Nenhuma chave e impressa -- so se ela existe.

    uv run --env-file .env python scripts/diagnose_tracing.py
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

PERGUNTA = "estou caro?"
HOTEL_ID = "345798"


def _ambiente() -> bool:
    print("== 1. Ambiente ==")
    for chave in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        valor = os.environ.get(chave)
        estado = f"presente ({len(valor)} chars)" if valor else "AUSENTE"
        print(f"  {chave}: {estado}")

    host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
    print(f"  host: {host or '(default do SDK)'}")
    return True


def _credencial(cliente) -> bool:
    print()
    print("== 2. Credencial ==")
    try:
        # `auth_check` LEVANTA quando a chave nao e aceita -- nao devolve False.
        # Por isso o try: a excecao e justamente o diagnostico.
        cliente.auth_check()
    except Exception as exc:  # noqa: BLE001 - a excecao E o diagnostico
        print(f"  FALHOU: {type(exc).__name__}: {exc}")
        print("  -> a chave nao e aceita por este host. Se a chave foi rotacionada")
        print("     no Langfuse, o .env ainda tem a antiga (ou o contrario).")
        return False
    print("  ok: a chave e aceita.")
    return True


def _grafo() -> bool:
    print()
    print("== 3. O grafo responde ==")
    from assistant_hotel.graph import default_graph

    resultado = default_graph().invoke({"question": PERGUNTA, "hotel_id": HOTEL_ID})
    resposta = (resultado.get("answer") or "").replace("\n", " ")
    print(f"  answer: {resposta[:100]}")
    if not resultado.get("answer"):
        print("  -> sem resposta. O grafo parou antes de gerar (clarify?).")
        return False
    return True


def _chegou(cliente, desde: datetime) -> bool:
    print()
    print("== 4. O trace desta execucao chegou ==")
    from assistant_hotel import tracing

    tracing.flush()

    # `from_start_time` e o que separa "chegou agora" de "chegou semana passada":
    # sem ele, um trace antigo mascararia a falha de agora.
    resposta = cliente.api.observations.get_many(
        type="GENERATION",
        fields="model,usage",
        limit=5,
        from_start_time=desde,
    )
    novas = list(getattr(resposta, "data", []) or [])
    if not novas:
        print("  NADA chegou. O grafo rodou, mas o trace nao foi enviado.")
        print("  -> a exportacao esta falhando em silencio (401? rede?).")
        return False

    for obs in novas:
        uso = obs.usage_details or {}
        custo = obs.total_cost
        print(f"  {obs.name} | model={obs.model} | {uso} | custo={custo}")
    print(f"  url: {cliente.get_trace_url(trace_id=novas[0].trace_id)}")

    # O que o SERVIDOR guardou, nao o que mandamos. Se o input vier vazio aqui,
    # o payload saiu certo e a ingestao perdeu -- ou seja, o problema e a versao
    # do servidor, nao o nosso codigo.
    print()
    print("== 5. O que o servidor guardou ==")
    do_trace = cliente.api.observations.get_many(
        trace_id=novas[0].trace_id,
        fields="io",
        limit=50,
    )
    for obs in list(getattr(do_trace, "data", []) or []):
        raiz = "RAIZ" if obs.is_root_observation else "    "
        entrada = "None" if obs.input is None else repr(obs.input)[:70]
        print(f"  {raiz} {obs.type:<10} {obs.name:<14} input={entrada}")
    return True


def main() -> int:
    from assistant_hotel import tracing

    _ambiente()
    if not tracing.enabled():
        print()
        print("  Sem as duas chaves o tracing e um no-op: nada e enviado e nada e")
        print("  impresso. Rode com --env-file .env.")
        return 1

    cliente = tracing.client()
    if cliente is None:
        print()
        print("  O cliente nao pode ser construido (ver a excecao acima).")
        return 1

    if not _credencial(cliente):
        return 1

    desde = datetime.now(timezone.utc)
    if not _grafo():
        return 1
    if not _chegou(cliente, desde):
        return 1

    print()
    print("Tudo certo: o trace saiu. Confira o custo com check_langfuse_cost.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
