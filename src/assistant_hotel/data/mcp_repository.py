"""Stub MCP-ready do HotelRepository.

A ideia: o `HotelRepository` é um Protocol. Hoje a implementação concreta é
`CsvHotelRepository` (lookup local). Amanhã, a mesma interface pode ser servida
por um servidor MCP (`pms-mcp`, `revenue-mcp`) que expõe `get_hotel_metrics`,
`search_hotel_by_name` e `list_hotels` como tools.

Este arquivo documenta o shape dessa integração sem subir servidor nenhum: a
classe implementa o Protocol, carrega as mesmas 20 linhas do CSV, mas o faz
através da assinatura que um cliente MCP teria. Serve como:

1. Prova técnica de que a camada de dados é portável (plug-and-play).
2. Contrato explícito dos headers que um servidor MCP de hotéis receberia
   (`x-hotel-id`, `x-session-id`, `x-requester-token`).
3. Ponto de extensão: trocar `_call_tool` por um `MultiServerMCPClient` real
   é a única mudança necessária para rodar contra MCP de verdade.

Isso NÃO é um mock de teste. É um adaptador cuja implementação de rede foi
substituída por chamada local — o shape é o mesmo de produção.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..domain.models import HotelRow
from .csv_repository import CsvHotelRepository


@dataclass(frozen=True)
class MCPCallContext:
    """Headers que um cliente MCP real adiciona a cada chamada.

    O servidor MCP usa isso para isolamento de dados: `x-hotel-id` garante que
    uma chamada a `get_hotel_metrics` só devolve a linha daquele hotel; nenhum
    cliente consegue ler dados de outro hotel passando um `hotel_id` diferente
    no payload.
    """

    hotel_id: str
    session_id: str | None = None
    requester_token: str | None = None
    source: str = "assistant-hotel"

    def as_headers(self) -> dict[str, str]:
        headers = {"x-hotel-id": self.hotel_id, "x-source": self.source}
        if self.session_id:
            headers["x-session-id"] = self.session_id
        if self.requester_token:
            headers["x-requester-token"] = self.requester_token
        return headers


class MCPHotelRepository:
    """Implementação do HotelRepository que fala em formato MCP.

    Hoje `_call_tool` resolve localmente (via `CsvHotelRepository`). Trocar por
    um `MultiServerMCPClient.call_tool(...)` é a única mudança para plugar num
    servidor MCP de verdade.
    """

    def __init__(
        self,
        backing: CsvHotelRepository | None = None,
        default_session_id: str | None = None,
        default_requester_token: str | None = None,
    ) -> None:
        self._backing = backing or CsvHotelRepository()
        self._session_id = default_session_id
        self._token = default_requester_token

    def _context(self, hotel_id: str) -> MCPCallContext:
        return MCPCallContext(
            hotel_id=hotel_id,
            session_id=self._session_id,
            requester_token=self._token,
        )

    def _call_tool(
        self, name: str, arguments: Mapping[str, Any], context: MCPCallContext
    ) -> Any:
        """Simula a chamada a uma tool MCP. Trocar aqui pelo cliente real.

        Shape da chamada equivalente num cliente MCP de verdade:

            await mcp_client.call_tool(
                server_name="pms-mcp",
                tool_name=name,
                arguments=dict(arguments),
                headers=context.as_headers(),
            )
        """
        if name == "get_hotel_metrics":
            return self._backing.get(str(arguments["hotel_id"]))
        if name == "search_hotel_by_name":
            return self._backing.find_by_name(str(arguments["name"]))
        if name == "list_hotels":
            return self._backing.all_ids()
        raise NotImplementedError(f"Tool MCP desconhecida: {name}")

    def get(self, hotel_id: str) -> HotelRow | None:
        ctx = self._context(hotel_id)
        return self._call_tool("get_hotel_metrics", {"hotel_id": hotel_id}, ctx)

    def find_by_name(self, name: str) -> list[HotelRow]:
        ctx = MCPCallContext(hotel_id="*", session_id=self._session_id, source="assistant-hotel")
        return self._call_tool("search_hotel_by_name", {"name": name}, ctx)

    def all_ids(self) -> list[str]:
        ctx = MCPCallContext(hotel_id="*", session_id=self._session_id, source="assistant-hotel")
        return self._call_tool("list_hotels", {}, ctx)


__all__ = ["MCPCallContext", "MCPHotelRepository"]
