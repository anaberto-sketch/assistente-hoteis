"""Tipos do dominio."""

from __future__ import annotations

from typing import Any, Mapping

# Uma linha do hotel ja normalizada (numeros como float, NULL como None).
HotelRow = Mapping[str, Any]
