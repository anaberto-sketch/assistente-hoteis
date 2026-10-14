"""Valida data/hotels_cleaned.csv contra o field dictionary e as regras de tipo.

Sai com codigo 0 se tudo passar, 1 se houver qualquer erro. Imprime um
relatorio com os problemas encontrados.

Uso:
    uv run python3 scripts/validate_data.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
CSV_PATH = DATA_DIR / "hotels_cleaned.csv"
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

_VALID_BOOL = {"", "true", "false"}


def _load_fields() -> list[str]:
    raw = yaml.safe_load(DICTIONARY_PATH.read_text(encoding="utf-8"))
    return [item["field"] for item in raw]


def main() -> int:
    fields = _load_fields()
    errors: list[str] = []

    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        rows = list(reader)

    # 1. Todos os campos do dicionario existem como colunas.
    missing = [f for f in fields if f not in columns]
    if missing:
        errors.append(f"colunas faltando: {missing}")

    # 2. Nenhuma coluna extra.
    extra = [c for c in columns if c not in fields]
    if extra:
        errors.append(f"colunas extras: {extra}")

    # 3. Numero de linhas.
    if len(rows) != EXPECTED_ROWS:
        errors.append(f"esperado {EXPECTED_ROWS} linhas, veio {len(rows)}")

    for i, row in enumerate(rows, start=1):
        # 4. hotel_id nao-nulo.
        if not row.get("hotel_id", "").strip():
            errors.append(f"linha {i}: hotel_id vazio")

        # 5. STRING_COLUMNS: qualquer texto e valido; nada a validar alem de
        #    nao ter virado numero (o CSV so guarda string, entao e sempre ok).

        # 6. BOOL_COLUMNS.
        for col in BOOL_COLUMNS:
            val = row.get(col, "")
            if val not in _VALID_BOOL:
                errors.append(f"linha {i} coluna {col}: flag invalida {val!r}")

        # 7. Colunas numericas parseaveis.
        numeric = [f for f in fields if f not in STRING_COLUMNS and f not in BOOL_COLUMNS]
        for col in numeric:
            val = row.get(col, "").strip()
            if not val:
                continue
            try:
                float(val)
            except ValueError:
                errors.append(f"linha {i} coluna {col}: nao-numerico {val!r}")

        # 8. AP-ranges nao convertidos para numero (saem do xlsx como string,
        #    mas garantimos que nenhum valor numerico vazou).
        for col in ("worst_ap_bkg_35d", "worst_ap_compset"):
            val = row.get(col, "").strip()
            if val:
                try:
                    float(val)
                    errors.append(f"linha {i} coluna {col}: faixa AP virou numero {val!r}")
                except ValueError:
                    pass

    if errors:
        print(f"FALHOU: {len(errors)} problema(s) em {CSV_PATH.name}")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK: {CSV_PATH.name} valido ({len(rows)} linhas x {len(fields)} colunas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
