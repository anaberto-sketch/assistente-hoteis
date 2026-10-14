"""Fixtures compartilhadas.

O `FakeLLM` e o que permite testar a TOPOLOGIA do grafo sem rede: ele implementa
o mesmo Protocol do cliente real e guarda o que recebeu, entao da para afirmar
coisas sobre o prompt montado.
"""

from __future__ import annotations

from typing import Any

import pytest

from assistant_hotel.data.csv_repository import CsvHotelRepository
from assistant_hotel.graph import Deps, build_graph
from assistant_hotel.llm import Completion
from assistant_hotel.retrieval.index import build_index


class FakeLLM:
    """Cliente de mentira: devolve respostas roteirizadas e grava as chamadas."""

    def __init__(
        self, replies: list[str] | None = None, stop_reason: str | None = "end_turn"
    ) -> None:
        self.replies = list(replies or ["Resposta de teste."])
        self.stop_reason = stop_reason
        self.calls: list[dict[str, Any]] = []

    def generate(self, system: str, messages: list[dict[str, Any]]) -> Completion:
        self.calls.append({"system": system, "messages": messages})
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return Completion(text=text, stop_reason=self.stop_reason)


@pytest.fixture(scope="session")
def repository() -> CsvHotelRepository:
    return CsvHotelRepository()


@pytest.fixture(scope="session")
def index():
    return build_index()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def graph(repository, index, fake_llm):
    return build_graph(Deps(repository=repository, index=index, llm=fake_llm))


# Hotel que passa em TODAS as regras. Os campos sao exatamente os `primary_field`
# de RULE_SPECS: sem eles a regra nao e avaliada, e o teste nao testaria nada.
CLEAN_ROW: dict[str, Any] = {
    "hotel_id": "TESTE",
    "hotel_name": "Hotel de Teste",
    "country_code": "BR",
    "content_score": 0.95,
    "rate_score": 8.7,
    "reviews_count": 500.0,
    "star_rating": 4.0,
    "cancel_rate_pct": 20.0,
    "total_lose_logueado_pct_35d": 10.0,
    "delta_precio_compset_pct": 1.0,
    "descuento_opaco_pct": 12.0,
    "descuento_package_pct": 15.0,
    "descuento_advanced_purchase_pct": 8.0,
    "avg_genius_discount_pct": 8.0,
    "profundidad_total_bkg_35d": 3.0,
    "profundidad_total_compset": 3.0,
    "appearances_pct": 80.0,
    "lose_rate_on_compete_pct": 10.0,
    "adjustment_pct_avg": 1.0,
    "perf_rn_90d_cy": 1000.0,
    "perf_compset_rn_90d_cy": 900.0,
    "rn_yoy_pct": 5.0,
    "hotel_growth_pct": 10.0,
    "dest_growth_pct": 5.0,
    "bk_35d": 100.0,
    "quality_adjustment_level": 1,
}


@pytest.fixture
def clean_row():
    """Fabrica de linha saudavel: `clean_row(content_score=0.5)` sobrescreve."""

    def build(**overrides: Any) -> dict[str, Any]:
        row = dict(CLEAN_ROW)
        row.update(overrides)
        return row

    return build
