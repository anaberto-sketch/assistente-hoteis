"""Garante que o modelo do assistente exista no Langfuse, com preco.

POR QUE ISTO EXISTE

O Langfuse nao recebe custo de nos: ele INFERE, casando o `model` da span com
as definicoes de modelo que ele proprio mantem. O problema e que
`claude-sonnet-5-bedrock` e um nome do GenPlat, e todos os padroes de Claude na
tabela do Langfuse sao ancorados (`^...$`, verificado em
`worker/src/constants/default-model-prices.json`) -- nenhum casa. Resultado: a
span sai com tokens e sem custo.

Este script cria a definicao que falta. A partir dela o custo passa a ser
inferido pelo Langfuse, sem variavel de ambiente nenhuma e sem preco no nosso
codigo.

E IDEMPOTENTE: se ja existir um modelo cujo `match_pattern` reconhece o nome,
nao faz nada. Rodar de novo e seguro.

    uv run --env-file .env python scripts/ensure_langfuse_model.py
    uv run --env-file .env python scripts/ensure_langfuse_model.py --dry-run

OBSERVACAO: o custo e calculado na INGESTAO. Definir o modelo hoje nao reescreve
o custo de spans ja enviadas -- so as novas.

Precos em USD por MILHAO de tokens, como a Anthropic publica. A API do Langfuse
guarda por TOKEN, entao a divisao por 1e6 acontece aqui.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone

# Defaults verificados em claude.com/pricing (para onde anthropic.com/pricing
# redireciona) em 2026-10-14: Sonnet 5 custa $2/MTok de entrada e $10/MTok de
# saida. Cache: leitura $0,20/MTok, escrita $2,50/MTok.
PRECO_ENTRADA_POR_MTOK = 2.0
PRECO_SAIDA_POR_MTOK = 10.0

MODELO = "claude-sonnet-5-bedrock"


def _padrao(modelo: str) -> str:
    """Ancorado, como o proprio Langfuse escreve os padroes dele.

    Ancorado de proposito: um padrao solto como `claude` casaria com qualquer
    modelo da familia e daria preco errado em silencio.
    """
    return f"(?i)^({re.escape(modelo)})$"


def _todos_os_modelos(cliente) -> list:
    """Percorre a paginacao da API de modelos."""
    modelos: list = []
    pagina = 1
    while True:
        resposta = cliente.api.models.list(page=pagina, limit=100)
        lote = list(getattr(resposta, "data", []) or [])
        modelos.extend(lote)
        if len(lote) < 100:
            return modelos
        pagina += 1


def _ja_existe(modelos: list, nome: str) -> object | None:
    """Algum modelo ja reconhece este nome?"""
    for modelo in modelos:
        padrao = getattr(modelo, "match_pattern", None)
        if not padrao:
            continue
        try:
            if re.match(padrao, nome):
                return modelo
        except re.error:
            # Padrao invalido nao pode derrubar a checagem dos outros.
            continue
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ensure_langfuse_model",
        description="Cria no Langfuse a definicao de modelo que faz o custo aparecer.",
    )
    parser.add_argument("--model", default=MODELO, help=f"nome do modelo (default: {MODELO})")
    parser.add_argument(
        "--input-price",
        type=float,
        default=PRECO_ENTRADA_POR_MTOK,
        help=f"USD por milhao de tokens de entrada (default: {PRECO_ENTRADA_POR_MTOK})",
    )
    parser.add_argument(
        "--output-price",
        type=float,
        default=PRECO_SAIDA_POR_MTOK,
        help=f"USD por milhao de tokens de saida (default: {PRECO_SAIDA_POR_MTOK})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="mostra o que faria, sem criar nada",
    )
    args = parser.parse_args(argv)

    from langfuse import Langfuse

    cliente = Langfuse()
    if not cliente.auth_check():
        print("Credencial do Langfuse nao aceita. Nada foi criado.", file=sys.stderr)
        return 1

    modelos = _todos_os_modelos(cliente)
    print(f"{len(modelos)} modelos definidos no Langfuse.")

    existente = _ja_existe(modelos, args.model)
    if existente is not None:
        print(f"Ja existe: {existente.model_name!r} casa com {args.model!r}.")
        print(f"  padrao : {existente.match_pattern}")
        print(f"  entrada: {existente.input_price}")
        print(f"  saida  : {existente.output_price}")
        print("Nada a fazer.")
        return 0

    padrao = _padrao(args.model)
    entrada = args.input_price / 1_000_000
    saida = args.output_price / 1_000_000

    print(f"Nao ha modelo casando {args.model!r}. Vou criar:")
    print(f"  padrao : {padrao}")
    print(f"  entrada: {entrada} USD/token (${args.input_price}/MTok)")
    print(f"  saida  : {saida} USD/token (${args.output_price}/MTok)")

    if args.dry_run:
        print("\n--dry-run: nada foi criado.")
        return 0

    from langfuse.api.commons.types.model_usage_unit import ModelUsageUnit
    from langfuse.api.models.types.model_tokenizer_id import ModelTokenizerId

    criado = cliente.api.models.create(
        model_name=args.model,
        match_pattern=padrao,
        unit=ModelUsageUnit.TOKENS,
        input_price=entrada,
        output_price=saida,
        # O tokenizer do Claude deixa o Langfuse contar tokens quando a span nao
        # traz `usage_details` -- aqui sempre traz, mas o campo e barato.
        tokenizer_id=ModelTokenizerId.CLAUDE,
        start_date=datetime.now(timezone.utc),
    )
    print(f"\nCriado: {criado.model_name} (id={criado.id})")
    print("O custo passa a aparecer nas PROXIMAS geracoes -- o calculo e na ingestao.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
