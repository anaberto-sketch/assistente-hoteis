"""Topologia do grafo.

Grafo LINEAR com UMA unica aresta condicional. Sem multi-agente, sem supervisor,
sem checkpointer.

  START -> resolve_hotel -+-> fetch_row -> diagnose -> retrieve_docs
                          |                              -> assemble
                          |                              -> generate
                          |                              -> validate -> END
                          +-> clarify -> END

Duas escolhas de ordem que nao sao arbitrarias:

  * `diagnose` roda ANTES de `retrieve_docs`. "Como esta meu hotel?" nao tem
    sinal lexico nenhum; se o retrieval dependesse so do texto, nao acharia
    nada. Com o diagnostico primeiro, as alavancas acionadas semeiam a busca.
  * `clarify` e um curto-circuito sem LLM: perguntar "qual hotel?" nao precisa
    de modelo.

As dependencias entram por injecao (`Deps`), nao por import global, para os
testes trocarem o LLM por um stub sem tocar em rede.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from .data.csv_repository import CsvHotelRepository
from .data.repository import HotelRepository
from .llm import GenPlatLLM, LLMClient
from .nodes.assemble import assemble_prompt
from .nodes.diagnose import diagnose_row
from .nodes.fetch import make_fetch_node
from .nodes.generate import make_generate_node
from .nodes.resolve import make_clarify_node, make_resolve_node, route_after_resolve
from .nodes.retrieve import make_retrieve_node
from .nodes.validate import make_validate_node
from .retrieval.index import FieldIndex, build_index
from .state import AssistantState
from .tracing import TracedGraph, TracedLLM


@dataclass(frozen=True)
class Deps:
    repository: HotelRepository
    index: FieldIndex
    llm: LLMClient


def build_graph(deps: Deps) -> Any:
    graph = StateGraph(AssistantState)

    nos = {
        "resolve_hotel": make_resolve_node(deps.repository),
        "clarify": make_clarify_node(deps.repository),
        "fetch_row": make_fetch_node(deps.repository),
        "diagnose": diagnose_row,
        "retrieve_docs": make_retrieve_node(deps.index),
        "assemble": assemble_prompt,
        "generate": make_generate_node(deps.llm),
        "validate": make_validate_node(deps.llm),
    }
    for nome, no in nos.items():
        graph.add_node(nome, no)

    graph.add_edge(START, "resolve_hotel")
    graph.add_conditional_edges(
        "resolve_hotel", route_after_resolve, ["clarify", "fetch_row"]
    )
    graph.add_edge("clarify", END)
    graph.add_edge("fetch_row", "diagnose")
    graph.add_edge("diagnose", "retrieve_docs")
    graph.add_edge("retrieve_docs", "assemble")
    graph.add_edge("assemble", "generate")
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", END)

    return TracedGraph(graph.compile())


def build_deps() -> Deps:
    # O LLM real vai envolvido: e aqui que a span de geracao passa a existir,
    # com modelo e tokens. Sem credencial do Langfuse, `TracedLLM` e
    # transparente.
    return Deps(
        repository=CsvHotelRepository(),
        index=build_index(),
        llm=TracedLLM(GenPlatLLM()),
    )


@lru_cache(maxsize=1)
def default_graph() -> Any:
    """Grafo com as dependencias reais, montado uma vez por processo."""
    return build_graph(build_deps())
