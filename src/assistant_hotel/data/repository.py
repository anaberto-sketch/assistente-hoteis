"""Interface de acesso a linha do hotel.

Lookup determinista por chave. NAO e retrieval: nao ha similaridade, nao ha
top-k. Recuperar a linha por semelhanca poderia devolver o hotel de outro
cliente -- falha de isolamento de dados, nao so de qualidade.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import HotelRow


@runtime_checkable
class HotelRepository(Protocol):
    def get(self, hotel_id: str) -> HotelRow | None:
        """Linha exata pelo ID, ou None."""
        ...

    def find_by_name(self, name: str) -> list[HotelRow]:
        """Candidatos por nome, do melhor para o pior. Vazio se nada casar."""
        ...

    def all_ids(self) -> list[str]:
        """Todos os IDs, para mensagens de ajuda."""
        ...
