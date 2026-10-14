"""Diz POR QUE o custo nao aparece no Langfuse.

O custo nao sai daqui. Quem o calcula e o Langfuse, na INGESTAO, e so quando as
tres condicoes valem juntas:

  1. a observacao e do tipo GENERATION;
  2. ela traz `usage_details` -- sem uso nao ha o que precificar;
  3. o `model` dela casa com uma definicao de modelo que TENHA preco.

Faltando a 3, a observacao aparece com tokens e sem custo -- e sem aviso nenhum.
E o que acontece com um nome que so existe no GenPlat: `claude-sonnet-5-bedrock`,
por exemplo, nao casa com nenhum padrao de Claude da tabela (todos ancorados em
`^...$`). Ja `gpt-4.1` casa, porque o Langfuse mantem esse modelo.

Este script le o que REALMENTE chegou na sua conta e diz qual das tres esta
falhando, em vez de adivinhar. Nao escreve nada.

    uv run --env-file .env python scripts/check_langfuse_cost.py
    uv run --env-file .env python scripts/check_langfuse_cost.py --limit 50

Sobre a janela de tempo: o custo e calculado na ingestao. Um trace enviado
ANTES da definicao existir continua sem custo para sempre -- so os novos sao
precificados. Por isso o script olha as generations mais recentes.
"""

from __future__ import annotations

import argparse
import re
import sys

MODELO = "gpt-4.1"


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


def _casam(modelos: list, nome: str) -> list:
    """Todas as definicoes cujo `match_pattern` reconhece este nome.

    Todas, e nao a primeira: duas definicoes casando e sinal de que alguem criou
    um padrao largo demais, e a de cima ganha em silencio.
    """
    achadas = []
    for modelo in modelos:
        padrao = getattr(modelo, "match_pattern", None)
        if not padrao:
            continue
        try:
            if re.match(padrao, nome):
                achadas.append(modelo)
        except re.error:
            continue
    return achadas


def _definicoes(cliente, nome: str) -> bool:
    """Imprime o estado das definicoes. Devolve True se alguma casa."""
    print("== Definicoes de modelo ==")
    modelos = _todos_os_modelos(cliente)
    print(f"{len(modelos)} definicoes no projeto.")

    casam = _casam(modelos, nome)
    if not casam:
        print(f"  NENHUMA casa com {nome!r}.")
        return False

    for modelo in casam:
        print(f"  CASA: {modelo.model_name!r}")
        print(f"        padrao  : {modelo.match_pattern}")
        print(f"        entrada : {modelo.input_price} USD/token")
        print(f"        saida   : {modelo.output_price} USD/token")
        if not modelo.input_price and not modelo.output_price:
            print("        ATENCAO: sem preco -- a definicao casa mas nao precifica.")
    return True


def _generations(cliente, limite: int) -> list:
    """As ultimas generations, com os campos que decidem o custo."""
    resposta = cliente.api.observations.get_many(
        type="GENERATION",
        fields="model,usage",
        limit=limite,
    )
    return list(getattr(resposta, "data", []) or [])


def _linha(obs) -> str:
    # Todo campo aqui pode vir nulo: `name` e `model` porque a observacao pode
    # nao trazer nenhum dos dois, e `usage_details`/`total_cost` porque e
    # exatamente a ausencia deles que estamos investigando.
    uso = obs.usage_details or {}
    tokens = f"in={uso.get('input')} out={uso.get('output')}" if uso else "SEM USO"
    custo = obs.total_cost
    valor = f"${custo:.6f}" if custo else "SEM CUSTO"
    nome = obs.name or "(sem nome)"
    modelo = obs.model or "(sem model)"
    return f"  {nome:<12} {modelo:<26} {tokens:<24} {valor}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_langfuse_cost",
        description="Mostra por que o custo nao aparece no Langfuse.",
    )
    parser.add_argument("--model", default=MODELO, help=f"nome do modelo (default: {MODELO})")
    parser.add_argument("--limit", type=int, default=20, help="quantas generations olhar")
    args = parser.parse_args(argv)

    from langfuse import Langfuse

    cliente = Langfuse()
    if not cliente.auth_check():
        print("Credencial do Langfuse nao aceita.", file=sys.stderr)
        return 1

    tem_definicao = _definicoes(cliente, args.model)

    print()
    print("== Ultimas generations ==")
    generations = _generations(cliente, args.limit)
    if not generations:
        print("  Nenhuma. Nada foi tracado ainda -- rode o CLI com --env-file.")
        return 0

    for obs in generations:
        print(_linha(obs))

    # O diagnostico e uma cascata: o primeiro degrau que falha e a causa.
    print()
    print("== Diagnostico ==")

    sem_uso = [o for o in generations if not o.usage_details]
    if sem_uso:
        print(f"  {len(sem_uso)}/{len(generations)} sem `usage_details`.")
        print("  -> sem uso nao ha custo. O provedor nao informou tokens, ou a")
        print("     span de geracao nao esta sendo preenchida.")
        return 1

    sem_modelo = [o for o in generations if not o.model_id]
    if sem_modelo and not tem_definicao:
        print(f"  {len(sem_modelo)}/{len(generations)} com uso mas sem `modelId`.")
        print(f"  -> nenhuma definicao casa com {args.model!r}. E a causa.")
        print("     Rode: uv run --env-file .env python scripts/ensure_langfuse_model.py")
        return 1

    if not any(o.total_cost for o in generations):
        print("  Ha uso e o modelo casa, mas nenhum custo foi calculado.")
        print("  -> confira se a definicao tem preco (input_price/output_price)")
        print("     e se estas generations foram ingeridas DEPOIS dela.")
        return 1

    com_custo = [o for o in generations if o.total_cost]
    print(f"  {len(com_custo)}/{len(generations)} com custo calculado. Esta funcionando.")
    print("  As sem custo sao anteriores a definicao -- o calculo e na ingestao.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
