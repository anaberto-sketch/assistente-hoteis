"""Consistencia do CSV com o field dictionary.

Estes testes leem data/hotels.csv diretamente (csv stdlib + yaml) e validam os
DADOS, nao a logica de app. Sao a rede de seguranca que pega regressoes na
regeneracao do CSV: coluna faltando, flag com valor estranho, faixa AP virada
numero, celula vazia virada zero, etc.
"""

from __future__ import annotations

import csv
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CSV_PATH = DATA_DIR / "hotels.csv"
DICTIONARY_PATH = DATA_DIR / "field_dictionary.yaml"

EXPECTED_ROWS = 20

STRING_COLUMNS = frozenset({
    "hotel_id",
    "hotel_name",
    "country_code",
    "destiny_code",
    "destiny",
    "worst_ap_bkg_35d",
    "worst_ap_compset",
    "root_cause",
})

BOOL_COLUMNS = frozenset({
    "flag_rn_below_compset",
    "flag_precio_bkg",
    "flag_precio_compset",
    "flag_opaco",
    "flag_package",
    "flag_genius_mayor_opaco",
})


def _fields() -> list[str]:
    raw = yaml.safe_load(DICTIONARY_PATH.read_text(encoding="utf-8"))
    return [item["field"] for item in raw]


def _rows() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_all_dictionary_fields_present_in_csv():
    fields = _fields()
    rows = _rows()
    assert rows, "hotels.csv vazio"
    columns = set(rows[0].keys())
    missing = [f for f in fields if f not in columns]
    assert not missing, f"campos do dicionario ausentes no CSV: {missing}"


def test_no_extra_columns():
    fields = set(_fields())
    rows = _rows()
    assert rows
    extra = [c for c in rows[0].keys() if c not in fields]
    assert not extra, f"colunas fora do dicionario: {extra}"


def test_row_count_is_20():
    assert len(_rows()) == EXPECTED_ROWS


def test_all_hotel_ids_non_null():
    for i, row in enumerate(_rows(), start=1):
        assert row.get("hotel_id", "").strip(), f"linha {i}: hotel_id vazio"


def test_br_and_do_hotels_present():
    codes = {row["country_code"] for row in _rows()}
    assert "BR" in codes, "nenhum hotel BR"
    assert "DO" in codes, "nenhum hotel DO"


def test_bool_columns_are_valid_values():
    for i, row in enumerate(_rows(), start=1):
        for col in BOOL_COLUMNS:
            assert row.get(col, "") in {"", "true", "false"}, (
                f"linha {i} coluna {col}: flag invalida {row.get(col)!r}"
            )


def test_ap_range_fields_are_strings():
    for i, row in enumerate(_rows(), start=1):
        for col in ("worst_ap_bkg_35d", "worst_ap_compset"):
            val = row.get(col, "").strip()
            if not val:
                continue
            try:
                float(val)
            except ValueError:
                continue
            assert False, f"linha {i} coluna {col}: faixa AP virou numero {val!r}"


def test_normalize_round_trip():
    from assistant_hotel.data.csv_repository import CsvHotelRepository

    repo = CsvHotelRepository()
    for hotel_id in repo.all_ids():
        row = repo.get(hotel_id)
        assert isinstance(row["hotel_id"], str)
        # content_score e numerico quando presente.
        if row["content_score"] is not None:
            assert isinstance(row["content_score"], float)
        # flags viram bool ou None, nunca string.
        for col in BOOL_COLUMNS:
            assert row[col] is None or isinstance(row[col], bool), (
                f"{hotel_id} coluna {col}: {row[col]!r}"
            )


def test_repository_get_all_ids():
    from assistant_hotel.data.csv_repository import CsvHotelRepository

    repo = CsvHotelRepository()
    ids = repo.all_ids()
    assert len(ids) == EXPECTED_ROWS
    for hotel_id in ids:
        assert repo.get(hotel_id) is not None, f"{hotel_id} nao resolveu"
