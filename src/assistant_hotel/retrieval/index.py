"""Indice BM25 sobre o dicionario de campos, com garantias de inclusao.

O corpus e pequeno (~59 campos), entao o retrieval aqui e FOCO, nao dependencia
de correcao. Por isso as quatro garantias, nesta ordem:

  1. inclusao garantida: todo campo citado por uma alavanca acionada entra no
     prompt, independente do texto da pergunta. E o que faz "como esta meu
     hotel?" funcionar -- a pergunta nao tem sinal lexico nenhum.
  2. piso por bloco: se a pergunta e vaga, entra um campo representativo por
     bloco, para dar cobertura de vocabulario ao modelo.
  3. o dossie de limiares NAO passa por aqui (ver domain/thresholds.py).
  4. fallback: se ainda assim vier vazio, entra o dicionario inteiro.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from ..domain.fields import BLOCKS, FieldEntry, field_dictionary
from ..state import FieldDoc
from .tokenize import tokens

# Peso de cada parte do documento. O nome do campo e o sinonimo carregam o
# sinal; a definicao e a leitura entram como desempate.
WEIGHTS: dict[str, float] = {
    "field": 3.0,
    "synonyms": 2.5,
    "block": 2.0,
    "definition": 1.0,
    "how_to_read": 0.8,
}

# Um campo representativo por bloco, para o piso de cobertura.
REPRESENTATIVE_FIELD: dict[str, str] = {
    "Identificación": "destiny",
    "EXPO": "cvr_total",
    "RESERVAS": "rn_yoy_pct",
    "TARIFAS": "delta_precio_compset_pct",
    "CALIDAD": "content_score",
}

DEFAULT_LIMIT = 14
K1 = 1.5
B = 0.75
# Score usado para inclusao garantida: sempre acima de qualquer BM25 real.
GUARANTEED = math.inf
# Score do representante de um bloco detectado na pergunta. Fica acima dos
# representantes dos blocos nao detectados, e abaixo de um bom match BM25.
BLOCK_BOOST = 1.0


@dataclass
class FieldIndex:
    entries: tuple[FieldEntry, ...]
    _tf: list[dict[str, float]] = field(default_factory=list)
    _length: list[float] = field(default_factory=list)
    _df: Counter = field(default_factory=Counter)
    _by_name: dict[str, int] = field(default_factory=dict)
    _avg_length: float = 0.0

    def __post_init__(self) -> None:
        for position, entry in enumerate(self.entries):
            self._by_name[entry.field] = position
            self._tf.append(self._term_frequencies(entry))
            self._length.append(sum(self._tf[position].values()) or 1.0)

        for frequencies in self._tf:
            for term in frequencies:
                self._df[term] += 1

        self._avg_length = sum(self._length) / len(self._length) if self._length else 1.0

    @staticmethod
    def _term_frequencies(entry: FieldEntry) -> dict[str, float]:
        parts: dict[str, Iterable[str]] = {
            "field": tokens(entry.field),
            "synonyms": [t for syn in entry.synonyms for t in tokens(syn)],
            "block": tokens(entry.block),
            "definition": tokens(f"{entry.es_definition} {entry.pt_definition}"),
            "how_to_read": tokens(f"{entry.es_how_to_read} {entry.pt_how_to_read}"),
        }
        frequencies: dict[str, float] = {}
        for part, terms in parts.items():
            weight = WEIGHTS[part]
            for term in terms:
                frequencies[term] = frequencies.get(term, 0.0) + weight
        return frequencies

    def score(self, query: str) -> dict[str, float]:
        """BM25 do texto da pergunta contra cada campo do dicionario."""
        query_terms = tokens(query)
        if not query_terms:
            return {}

        total = len(self.entries)
        scores: dict[str, float] = {}

        for position, entry in enumerate(self.entries):
            frequencies = self._tf[position]
            length = self._length[position]
            score = 0.0
            for term in set(query_terms):
                frequency = frequencies.get(term, 0.0)
                if frequency <= 0:
                    continue
                df = self._df[term]
                idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
                denominator = frequency + K1 * (1 - B + B * length / self._avg_length)
                score += idf * (frequency * (K1 + 1)) / denominator
            if score > 0:
                scores[entry.field] = score
        return scores

    def has_field(self, name: str) -> bool:
        return name in self._by_name

    def doc(self, name: str, lang: str, score: float) -> FieldDoc | None:
        position = self._by_name.get(name)
        if position is None:
            return None
        entry = self.entries[position]
        return FieldDoc(
            field=entry.field,
            block=entry.block,
            definition=entry.definition(lang),
            how_to_read=entry.how_to_read(lang),
            score=score,
        )


def build_index() -> FieldIndex:
    return FieldIndex(entries=field_dictionary())


def search(
    index: FieldIndex,
    query: str,
    lang: str,
    must_include: Sequence[str] = (),
    blocks: Sequence[str] = (),
    limit: int = DEFAULT_LIMIT,
) -> list[FieldDoc]:
    """Seleciona os campos que entram no prompt, aplicando as garantias."""
    scores = index.score(query)

    selected: dict[str, float] = dict(
        sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
    )

    # Garantia 2: piso por bloco. Cobre SEMPRE os cinco blocos, para o modelo
    # ter vocabulario de todas as dimensoes mesmo numa pergunta vaga. Os blocos
    # detectados pelo texto ganham um score maior, entao ordenam acima -- mas
    # todos os representantes entram.
    detected = set(blocks)
    for block in BLOCKS:
        representative = REPRESENTATIVE_FIELD.get(block)
        if representative:
            selected.setdefault(representative, BLOCK_BOOST if block in detected else 0.0)

    # Garantia 1: inclusao obrigatoria. Sobrescreve o score.
    for name in must_include:
        if index.has_field(name):
            selected[name] = GUARANTEED

    docs = [
        doc
        for name, score in selected.items()
        if (doc := index.doc(name, lang, score)) is not None
    ]
    docs.sort(key=lambda d: (-d["score"], d["field"]))

    # Garantia 4: fallback para o dicionario inteiro.
    if not docs:
        docs = [
            FieldDoc(
                field=e.field,
                block=e.block,
                definition=e.definition(lang),
                how_to_read=e.how_to_read(lang),
                score=0.0,
            )
            for e in index.entries
        ]
    return docs
