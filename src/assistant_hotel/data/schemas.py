"""Normalizacao da linha do hotel.

O export usa virgula decimal ("0,01294181599") e aspas de milhar
("1494870,06"). Aqui isso vira float. String vazia vira NULL -- e NULL NUNCA
vira zero: "sem compset definido" e diferente de "compset igual a zero".
"""

from __future__ import annotations

from typing import Any

# Colunas que permanecem texto. Inclui IDs e as faixas de antecedencia (AP),
# que parecem numero mas sao rotulos ("091-inf", "000-007", "046-090").
STRING_COLUMNS = frozenset({
    "hotel_id",
    "hotel_name",
    "country_code",
    "destiny_code",
    "destiny",
    "worst_ap_bkg_35d",
    "worst_ap_compset",
    "root_cause",
    "perfil_ejemplo",
})

BOOL_COLUMNS = frozenset({
    "flag_rn_below_compset",
    "flag_precio_bkg",
    "flag_precio_compset",
    "flag_opaco",
    "flag_package",
    "flag_genius_mayor_opaco",
})

_TRUE = {"true", "1", "yes", "sim", "verdadero"}
_FALSE = {"false", "0", "no", "nao", "não", "falso"}


def _parse_bool(raw: str) -> bool | None:
    token = raw.strip().lower()
    if token in _TRUE:
        return True
    if token in _FALSE:
        return False
    return None


def _parse_number(raw: str) -> float | None:
    token = raw.strip().replace(" ", "")
    if not token:
        return None
    # Virgula decimal (formato do export). Se houver ambos, o ultimo e o decimal.
    if "," in token and "." in token:
        token = token.replace(".", "").replace(",", ".")
    else:
        token = token.replace(",", ".")
    try:
        return float(token)
    except ValueError:
        return None


def normalize_value(column: str, raw: Any) -> Any:
    """Converte um campo cru do CSV para o tipo do dominio."""
    if raw is None:
        return None

    if column in STRING_COLUMNS:
        text = str(raw).strip()
        return text or None

    text = str(raw).strip()
    if not text:
        return None  # NULL, nunca zero

    if column in BOOL_COLUMNS:
        return _parse_bool(text)

    return _parse_number(text)


def normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    return {column: normalize_value(column, value) for column, value in raw.items()}
