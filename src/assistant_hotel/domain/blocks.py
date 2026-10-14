"""Mapeia vocabulario de negocio -> bloco do dicionario.

Isto semeia o retrieval quando a pergunta e vaga. E um mapa explicito de
palavras-chave, NAO um classificador LLM: precisa ser deterministico e testavel.

As palavras vem em PT e ES porque o hoteleiro pergunta no idioma dele.
"""

from __future__ import annotations

from ..retrieval.tokenize import normalize

# Palavras de negocio -> bloco. Curado a mao.
BLOCK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "EXPO": (
        "exposicao", "exposicion", "busca", "buscas", "pesquisa", "pesquisas",
        "conversao", "conversion", "cvr", "clique", "cliques", "click", "clics",
        "visita", "visitas", "visibilidad", "visibilidade", "funil", "embudo",
        "impressao", "impresion", "detalhe", "detalle", "ficha",
    ),
    "RESERVAS": (
        "reserva", "reservas", "booking", "bookings", "venda", "vendas", "ventas",
        "vender", "vende", "vendendo", "vendiendo", "vendo",
        "receita", "faturamento", "gmv", "gross", "room", "nights", "noites",
        "diarias", "quarto", "quartos", "habitacion", "habitaciones",
        "crescimento", "crecimiento", "queda", "caida", "yoy", "ano", "tendencia",
        "demanda", "futuro", "pickup", "otb", "compset", "concorrente",
        "concorrentes", "competidor", "competidores", "share", "participacao",
        "participacion", "volume", "volumen",
    ),
    "TARIFAS": (
        "preco", "precos", "preço", "precios", "tarifa", "tarifas", "valor",
        "desconto", "descuento", "promocao", "promocion", "paridade", "paridad",
        "booking", "genius", "opaco", "opaca", "pacote", "paquete", "package",
        "caro", "barato", "competitividade", "adversa", "adversas", "perder",
        "perda", "ap", "antecedencia", "anticipacion", "asp", "diaria",
        "disparidade", "disparidad", "roompack", "proveedor", "fornecedor",
    ),
    "CALIDAD": (
        "nota", "avaliacao", "avaliações", "avaliacoes", "puntaje", "puntuacion",
        "review", "reviews", "reseña", "resenas", "reputacao", "reputacion",
        "estrela", "estrelas", "estrellas", "categoria", "conteudo", "conteúdo",
        "contenido", "ficha", "completude", "completitud", "foto", "fotos",
        "amenities", "cancelamento", "cancelacion", "qualidade", "calidad",
    ),
    "Identificación": (
        "pais", "idioma", "destino", "ciudad", "cidade", "hotel", "nome",
        "nombre", "identificador",
    ),
}


def blocks_for(question: str) -> list[str]:
    """Blocos sugeridos pelo texto da pergunta, na ordem canonica."""
    tokens = set(normalize(question).split())
    hits: list[str] = []
    for block, keywords in BLOCK_KEYWORDS.items():
        if tokens & set(keywords):
            hits.append(block)
    # Ordem canonica do material, para o resultado ser estavel.
    from .fields import BLOCKS

    return [b for b in BLOCKS if b in hits]
