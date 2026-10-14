"""Tokenizacao para o BM25.

Tres coisas importam aqui:
  1. remover acentos -- o hoteleiro escreve "conversão", "precio", "avaliação";
  2. quebrar identificadores -- `cvr_search_success` vira cvr/search/success;
  3. quebrar camelCase -- `descuentoOpaco` vira descuento/opaco.
"""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(text: str) -> str:
    """Texto -> forma canonica tokenizavel, separada por espaco."""
    if not text:
        return ""
    text = _CAMEL.sub(" ", text)
    text = strip_accents(text).lower()
    return _NON_WORD.sub(" ", text).strip()


def tokens(text: str) -> list[str]:
    normalized = normalize(text)
    return normalized.split() if normalized else []
