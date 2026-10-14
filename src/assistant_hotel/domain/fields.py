"""Carrega o dicionario de campos (o corpus do RAG).

Os textos vem verbatim de data/field_dictionary.yaml, que por sua vez foi
transcrito do material do time. Este modulo nao inventa conteudo: so le e
organiza.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ..config import Settings

# Blocos na ordem em que aparecem no material.
BLOCKS: tuple[str, ...] = (
    "Identificación",
    "EXPO",
    "RESERVAS",
    "TARIFAS",
    "CALIDAD",
)


@dataclass(frozen=True)
class FieldEntry:
    field: str
    block: str
    type: str
    es_definition: str
    es_how_to_read: str
    pt_definition: str
    pt_how_to_read: str
    synonyms: tuple[str, ...]

    def definition(self, lang: str) -> str:
        return self.es_definition if lang == "es" else self.pt_definition

    def how_to_read(self, lang: str) -> str:
        return self.es_how_to_read if lang == "es" else self.pt_how_to_read


def load_field_dictionary(path: Path | None = None) -> list[FieldEntry]:
    dict_path = path or Settings.from_env().dictionary_file
    raw = yaml.safe_load(dict_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{dict_path} deveria conter uma lista de campos.")

    entries: list[FieldEntry] = []
    for item in raw:
        entries.append(
            FieldEntry(
                field=item["field"],
                block=item["block"],
                type=item.get("type", "varchar"),
                es_definition=item["es"]["definition"].strip(),
                es_how_to_read=item["es"]["how_to_read"].strip(),
                pt_definition=item["pt"]["definition"].strip(),
                pt_how_to_read=item["pt"]["how_to_read"].strip(),
                synonyms=tuple(item.get("synonyms") or ()),
            )
        )
    return entries


@lru_cache(maxsize=1)
def field_dictionary() -> tuple[FieldEntry, ...]:
    """Dicionario carregado uma vez por processo."""
    return tuple(load_field_dictionary())


def by_name(name: str) -> FieldEntry | None:
    for entry in field_dictionary():
        if entry.field == name:
            return entry
    return None
