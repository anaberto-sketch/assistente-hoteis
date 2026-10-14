"""Implementacao local (CSV) do HotelRepository.

Trocar por SQL/Databricks depois e escrever outra classe com a mesma interface:
nem o grafo nem o diagnostico conhecem esta implementacao.
"""

from __future__ import annotations

import csv
import difflib
from pathlib import Path

from ..config import Settings
from ..domain.models import HotelRow
from ..retrieval.tokenize import normalize
from .schemas import normalize_row

# Abaixo disso, o nome e considerado nao relacionado.
NAME_MATCH_THRESHOLD = 0.6


class CsvHotelRepository:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Settings.from_env().hotels_file
        self._rows: dict[str, HotelRow] = {}
        self._order: list[str] = []
        self._load()

    def _load(self) -> None:
        with self._path.open(newline="", encoding="utf-8") as handle:
            for raw in csv.DictReader(handle):
                row = normalize_row(raw)
                hotel_id = row.get("hotel_id")
                if not hotel_id:
                    continue
                self._rows[hotel_id] = row
                self._order.append(hotel_id)

    def get(self, hotel_id: str) -> HotelRow | None:
        return self._rows.get(str(hotel_id).strip())

    def find_by_name(self, name: str) -> list[HotelRow]:
        needle = normalize(name)
        if not needle:
            return []

        scored: list[tuple[float, str]] = []
        for hotel_id, row in self._rows.items():
            candidate = normalize(str(row.get("hotel_name") or ""))
            if not candidate:
                continue
            if candidate == needle:
                score = 1.0
            elif needle in candidate or candidate in needle:
                # Substring e um sinal forte, mas menos que igualdade.
                score = 0.9
            else:
                score = difflib.SequenceMatcher(None, needle, candidate).ratio()
            if score >= NAME_MATCH_THRESHOLD:
                scored.append((score, hotel_id))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [self._rows[hotel_id] for _, hotel_id in scored]

    def all_ids(self) -> list[str]:
        return list(self._order)

    def names(self) -> list[str]:
        return [str(self._rows[i].get("hotel_name") or i) for i in self._order]
