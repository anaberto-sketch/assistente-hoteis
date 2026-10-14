"""Regras do diagnostico: funcoes puras `row -> Lever | None`.

Nenhuma chamada de rede, nenhum LLM. Cada regra aplica UM limiar do material.

Fronteiras: o material usa `<` e `>` ESTRITOS. `content_score == 0.70` NAO
aciona; `0.699` aciona. `total_lose == 30` NAO aciona; `30.1` aciona.
"""

from __future__ import annotations

from typing import Any, Callable

from ..state import Lever, Severity
from . import thresholds as T
from .models import HotelRow

# Colunas de faixa de antecedencia (AP). Sao STRING, nunca numero.
AP_COLUMNS = (
    "worst_ap_bkg_35d",
    "worst_ap_compset",
)


def num(row: HotelRow, key: str) -> float | None:
    """Le um valor numerico da linha. NULL -> None. Booleano nunca e numero."""
    value: Any = row.get(key)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _lever(
    *,
    id: str,
    block: str,
    severity: Severity,
    rule: str,
    field_refs: list[str],
    evidence: dict[str, Any],
    message_pt: str,
    message_es: str,
) -> Lever:
    # Remove do evidence as chaves sem valor: nao afirmamos o que nao temos.
    clean = {k: v for k, v in evidence.items() if v is not None}
    return Lever(
        id=id,
        block=block,
        severity=severity,
        rule=rule,
        field_refs=field_refs,
        evidence=clean,
        message_pt=message_pt,
        message_es=message_es,
        caveats=[],
    )


def compset_is_comparable(row: HotelRow) -> bool:
    """Ha compset utilizavel para comparar?

    O material diz que NULL = "sin compset definido". Tratamos tambem 0 como
    nao-comparavel: um compset de 0 room nights tornaria a razao sem sentido
    (o hotel seria "infinitamente melhor"). Isso e guarda de engenharia, nao
    regra do material.
    """
    compset = num(row, "perf_compset_rn_90d_cy")
    return compset is not None and compset > 0


# --------------------------------------------------------------------------
# CALIDAD
# --------------------------------------------------------------------------

def rule_completa_ficha(row: HotelRow) -> Lever | None:
    v = num(row, "content_score")
    if v is None or v >= T.CONTENT_SCORE_MIN:
        return None
    return _lever(
        id="completa_ficha",
        block="CALIDAD",
        severity="high",
        rule=f"content_score < {T.CONTENT_SCORE_MIN}",
        field_refs=["content_score", "hotel_name"],
        evidence={"content_score": v},
        message_pt=(
            "A ficha do hotel está incompleta (fotos, descrição, amenities). "
            "Completar a ficha é a alavanca mais barata e rápida daqui."
        ),
        message_es=(
            "La ficha del hotel está incompleta (fotos, descripción, amenities). "
            "Completar la ficha es la palanca más barata y rápida de aquí."
        ),
    )


def rule_nota_baixa(row: HotelRow) -> Lever | None:
    v = num(row, "rate_score")
    if v is None or v >= T.RATE_SCORE_MIN:
        return None
    return _lever(
        id="nota_baixa",
        block="CALIDAD",
        severity="medium",
        rule=f"rate_score < {T.RATE_SCORE_MIN}",
        field_refs=["rate_score", "reviews_count", "star_rating"],
        evidence={
            "rate_score": v,
            "reviews_count": num(row, "reviews_count"),
            "star_rating": num(row, "star_rating"),
        },
        message_pt=(
            "A nota de avaliações do hotel está baixa. Comparar com a média do destino "
            "antes de tratar como problema isolado."
        ),
        message_es=(
            "El puntaje de reseñas del hotel está bajo. Comparar con el promedio del "
            "destino antes de tratarlo como problema aislado."
        ),
    )


# --------------------------------------------------------------------------
# TARIFAS
# --------------------------------------------------------------------------

def rule_precio_bkg(row: HotelRow) -> Lever | None:
    v = num(row, "total_lose_logueado_pct_35d")
    if v is None or v <= T.TOTAL_LOSE_BKG_MAX:
        return None
    return _lever(
        id="flag_precio_bkg",
        block="TARIFAS",
        severity="high",
        rule=f"total_lose_logueado_pct_35d > {T.TOTAL_LOSE_BKG_MAX}",
        field_refs=[
            "total_lose_logueado_pct_35d",
            "profundidad_total_bkg_35d",
            "worst_ap_bkg_35d",
            "target_asp",
            "root_cause",
        ],
        evidence={
            "total_lose_logueado_pct_35d": v,
            "profundidad_total_bkg_35d": num(row, "profundidad_total_bkg_35d"),
            "worst_ap_bkg_35d": row.get("worst_ap_bkg_35d"),
            "target_asp": num(row, "target_asp"),
            "root_cause": row.get("root_cause"),
        },
        message_pt=(
            "O preço da Despegar perde para o Booking na maioria das comparações "
            "com usuário logado. É problema de paridade, não de visibilidade."
        ),
        message_es=(
            "El precio de Despegar pierde frente a Booking en la mayoría de las "
            "comparaciones con usuario logueado. Es un problema de paridad, no de visibilidad."
        ),
    )


def rule_precio_compset(row: HotelRow) -> Lever | None:
    v = num(row, "delta_precio_compset_pct")
    if v is None or v <= T.DELTA_PRECIO_COMPSET_MAX:
        return None
    return _lever(
        id="flag_precio_compset",
        block="TARIFAS",
        severity="high",
        rule=f"delta_precio_compset_pct > {T.DELTA_PRECIO_COMPSET_MAX}",
        field_refs=[
            "delta_precio_compset_pct",
            "target_asp",
            "compset_asp_avg",
            "profundidad_total_compset",
            "quality_adjustment_level",
        ],
        evidence={
            "delta_precio_compset_pct": v,
            "target_asp": num(row, "target_asp"),
            "compset_asp_avg": num(row, "compset_asp_avg"),
            "profundidad_total_compset": num(row, "profundidad_total_compset"),
            "quality_adjustment_level": num(row, "quality_adjustment_level"),
        },
        message_pt=(
            "O hotel está mais caro que os concorrentes diretos, já descontado o "
            "ajuste por qualidade."
        ),
        message_es=(
            "El hotel está más caro que los competidores directos, ya descontado el "
            "ajuste por calidad."
        ),
    )


def rule_opaco(row: HotelRow) -> Lever | None:
    v = num(row, "descuento_opaco_pct")
    if v is None or v >= T.DESCUENTO_OPACO_MIN:
        return None
    return _lever(
        id="flag_opaco",
        block="TARIFAS",
        severity="medium",
        rule=f"descuento_opaco_pct < {T.DESCUENTO_OPACO_MIN}",
        field_refs=["descuento_opaco_pct", "descuento_advanced_purchase_pct"],
        evidence={
            "descuento_opaco_pct": v,
            "descuento_advanced_purchase_pct": num(
                row, "descuento_advanced_purchase_pct"
            ),
        },
        message_pt=(
            "O desconto opaco está insuficiente. A tarifa opaca não revela o nome do "
            "hotel até a compra, então o desconto é o que sustenta a venda."
        ),
        message_es=(
            "El descuento opaco está insuficiente. La tarifa opaca no revela el nombre "
            "del hotel hasta la compra, así que el descuento es lo que sostiene la venta."
        ),
    )


def rule_package(row: HotelRow) -> Lever | None:
    v = num(row, "descuento_package_pct")
    if v is None or v >= T.DESCUENTO_PACKAGE_MIN:
        return None
    return _lever(
        id="flag_package",
        block="TARIFAS",
        severity="medium",
        rule=f"descuento_package_pct < {T.DESCUENTO_PACKAGE_MIN}",
        field_refs=["descuento_package_pct"],
        evidence={"descuento_package_pct": v},
        message_pt="O desconto para venda em pacote está baixo.",
        message_es="El descuento para venta en paquete está bajo.",
    )


def rule_genius_mayor_opaco(row: HotelRow) -> Lever | None:
    genius = num(row, "avg_genius_discount_pct")
    opaco = num(row, "descuento_opaco_pct")
    if genius is None or opaco is None:
        return None
    if genius <= opaco + T.GENIUS_OVER_OPACO_MARGIN:
        return None
    return _lever(
        id="flag_genius_mayor_opaco",
        block="TARIFAS",
        severity="medium",
        rule=f"avg_genius_discount_pct > descuento_opaco_pct + {T.GENIUS_OVER_OPACO_MARGIN}",
        field_refs=["avg_genius_discount_pct", "descuento_opaco_pct"],
        evidence={"avg_genius_discount_pct": genius, "descuento_opaco_pct": opaco},
        message_pt=(
            "O hotel dá mais desconto ao Booking (Genius) do que ao desconto opaco "
            "próprio. É uma causa direta de perda de paridade."
        ),
        message_es=(
            "El hotel da más descuento a Booking (Genius) que al descuento opaco "
            "propio. Es una causa directa de pérdida de paridad."
        ),
    )


def rule_profundidad_bkg(row: HotelRow) -> Lever | None:
    """Gravidade da perda vs Booking. So faz sentido se ha problema de preco."""
    lose = num(row, "total_lose_logueado_pct_35d")
    prof = num(row, "profundidad_total_bkg_35d")
    if prof is None or lose is None or lose <= T.TOTAL_LOSE_BKG_MAX:
        return None
    grande = prof >= T.PROFUNDIDAD_BRECHA_GRANDE
    return _lever(
        id="campanha_bkg" if grande else "brecha_bkg",
        block="TARIFAS",
        severity="medium" if grande else "low",
        rule=(
            f"profundidad_total_bkg_35d {'>=' if grande else '<'} "
            f"{T.PROFUNDIDAD_BRECHA_GRANDE}"
        ),
        field_refs=[
            "profundidad_total_bkg_35d",
            "total_lose_logueado_pct_35d",
            "worst_ap_bkg_35d",
            "profundidad_worst_ap_bkg_35d",
        ],
        evidence={
            "profundidad_total_bkg_35d": prof,
            "total_lose_logueado_pct_35d": lose,
            "worst_ap_bkg_35d": row.get("worst_ap_bkg_35d"),
            "profundidad_worst_ap_bkg_35d": num(row, "profundidad_worst_ap_bkg_35d"),
        },
        message_pt=(
            "A diferença de preço contra o Booking é grande: costuma exigir campanha, "
            "não só ajuste de tarifa."
            if grande
            else
            "A diferença de preço contra o Booking é pequena: tende a se resolver "
            "ajustando a tarifa."
        ),
        message_es=(
            "La diferencia de precio contra Booking es grande: suele exigir campaña, "
            "no solo ajuste de tarifa."
            if grande
            else
            "La diferencia de precio contra Booking es pequeña: tiende a resolverse "
            "ajustando la tarifa."
        ),
    )


def rule_profundidad_compset(row: HotelRow) -> Lever | None:
    """Gravidade da perda vs compset. Gate: delta ajustado > 5."""
    delta = num(row, "delta_precio_compset_pct")
    prof = num(row, "profundidad_total_compset")
    if prof is None or delta is None or delta <= T.DELTA_PRECIO_COMPSET_MAX:
        return None
    grande = prof >= T.PROFUNDIDAD_BRECHA_GRANDE
    return _lever(
        id="campanha_compset" if grande else "brecha_compset",
        block="TARIFAS",
        severity="medium" if grande else "low",
        rule=(
            f"profundidad_total_compset {'>=' if grande else '<'} "
            f"{T.PROFUNDIDAD_BRECHA_GRANDE}"
        ),
        field_refs=[
            "profundidad_total_compset",
            "delta_precio_compset_pct",
            "worst_ap_compset",
            "profundidad_worst_ap_compset",
        ],
        evidence={
            "profundidad_total_compset": prof,
            "delta_precio_compset_pct": delta,
            "worst_ap_compset": row.get("worst_ap_compset"),
            "profundidad_worst_ap_compset": num(row, "profundidad_worst_ap_compset"),
        },
        message_pt=(
            "A brecha contra os concorrentes diretos é grande: costuma exigir campanha."
            if grande
            else
            "A brecha contra os concorrentes diretos é pequena: tende a se resolver "
            "ajustando a tarifa."
        ),
        message_es=(
            "La brecha contra los competidores directos es grande: suele exigir campaña."
            if grande
            else
            "La brecha contra los competidores directos es pequeña: tiende a resolverse "
            "ajustando la tarifa."
        ),
    )


def rule_problema_preco_real(row: HotelRow) -> Lever | None:
    """Aparece nas buscas E perde quando compete -> problema real de preco."""
    appearances = num(row, "appearances_pct")
    lose_rate = num(row, "lose_rate_on_compete_pct")
    if appearances is None or lose_rate is None:
        return None
    if appearances >= T.APPEARANCES_BAIXO or lose_rate <= T.LOSE_RATE_ALTO:
        return None
    return _lever(
        id="problema_preco_real",
        block="TARIFAS",
        severity="high",
        rule=(
            f"appearances_pct < {T.APPEARANCES_BAIXO} "
            f"e lose_rate_on_compete_pct > {T.LOSE_RATE_ALTO}"
        ),
        field_refs=[
            "appearances_pct",
            "lose_rate_on_compete_pct",
            "adjustment_pct_avg",
        ],
        evidence={
            "appearances_pct": appearances,
            "lose_rate_on_compete_pct": lose_rate,
            "adjustment_pct_avg": num(row, "adjustment_pct_avg"),
        },
        message_pt=(
            "O hotel aparece nas buscas e mesmo assim perde na maioria das vezes em "
            "que compete: é problema de preço, não de disponibilidade."
        ),
        message_es=(
            "El hotel aparece en las búsquedas y aun así pierde la mayoría de las veces "
            "en que compite: es problema de precio, no de disponibilidad."
        ),
    )


# --------------------------------------------------------------------------
# RESERVAS
# --------------------------------------------------------------------------

def rule_rn_below_compset(row: HotelRow) -> Lever | None:
    if not compset_is_comparable(row):
        return None
    rn = num(row, "perf_rn_90d_cy")
    compset = num(row, "perf_compset_rn_90d_cy")
    if rn is None or compset is None:
        return None
    if rn >= T.COMPSET_RN_RATIO_MIN * compset:
        return None
    return _lever(
        id="flag_rn_below_compset",
        block="RESERVAS",
        severity="high",
        rule=f"perf_rn_90d_cy < {T.COMPSET_RN_RATIO_MIN} x perf_compset_rn_90d_cy",
        field_refs=[
            "perf_rn_90d_cy",
            "perf_compset_rn_90d_cy",
            "rn_90d_cy",
            "rn_90d_vs_ly",
        ],
        evidence={
            "perf_rn_90d_cy": rn,
            "perf_compset_rn_90d_cy": compset,
            "rn_90d_cy": num(row, "rn_90d_cy"),
            "rn_90d_vs_ly": num(row, "rn_90d_vs_ly"),
        },
        message_pt=(
            "O hotel tem menos reservas futuras (próximos 90 dias) que os concorrentes "
            "diretos. É sinal de alerta antecipado."
        ),
        message_es=(
            "El hotel tiene menos reservas futuras (próximos 90 días) que los "
            "competidores directos. Es una señal de alerta anticipada."
        ),
    )


def rule_queda_yoy(row: HotelRow) -> Lever | None:
    v = num(row, "rn_yoy_pct")
    if v is None or v >= T.RN_YOY_DROP_RELEVANT:
        return None
    return _lever(
        id="queda_yoy",
        block="RESERVAS",
        severity="high",
        rule=f"rn_yoy_pct < {T.RN_YOY_DROP_RELEVANT}",
        field_refs=[
            "rn_yoy_pct",
            "rn_cy",
            "rn_ly",
            "gb_yoy_pct",
            "bk_yoy_pct",
            "bk_35d",
        ],
        evidence={
            "rn_yoy_pct": v,
            "rn_cy": num(row, "rn_cy"),
            "rn_ly": num(row, "rn_ly"),
            "gb_yoy_pct": num(row, "gb_yoy_pct"),
            "bk_yoy_pct": num(row, "bk_yoy_pct"),
            "bk_35d": num(row, "bk_35d"),
        },
        message_pt=(
            "As diárias vendidas no ano caíram mais de 10% contra o mesmo período do "
            "ano passado."
        ),
        message_es=(
            "Las diarias vendidas en el año cayeron más de 10% contra el mismo período "
            "del año pasado."
        ),
    )


def rule_perda_participacao(row: HotelRow) -> Lever | None:
    """Leitura do material para hotel_growth_pct vs dest_growth_pct."""
    hotel = num(row, "hotel_growth_pct")
    dest = num(row, "dest_growth_pct")
    if hotel is None or dest is None:
        return None
    if hotel >= dest:
        return None
    return _lever(
        id="perda_participacao",
        block="RESERVAS",
        severity="low",
        rule="hotel_growth_pct < dest_growth_pct",
        field_refs=[
            "hotel_growth_pct",
            "dest_growth_pct",
            "gb_35d",
            "bk_35d",
            "rn_35d",
        ],
        evidence={
            "hotel_growth_pct": hotel,
            "dest_growth_pct": dest,
            "gb_35d": num(row, "gb_35d"),
            "bk_35d": num(row, "bk_35d"),
            "rn_35d": num(row, "rn_35d"),
        },
        message_pt=(
            "O destino está crescendo mais que o hotel, ou caindo menos: o hotel está "
            "perdendo participação, não é só efeito de mercado."
        ),
        message_es=(
            "El destino está creciendo más que el hotel, o cayendo menos: el hotel está "
            "perdiendo participación, no es solo efecto de mercado."
        ),
    )


# Ordem em que as regras rodam. Estavel, para o diagnostico ser reproduzivel.
ALL_RULES: tuple[Callable[[HotelRow], Lever | None], ...] = (
    rule_completa_ficha,
    rule_nota_baixa,
    rule_precio_bkg,
    rule_precio_compset,
    rule_opaco,
    rule_package,
    rule_genius_mayor_opaco,
    rule_profundidad_bkg,
    rule_profundidad_compset,
    rule_problema_preco_real,
    rule_rn_below_compset,
    rule_queda_yoy,
    rule_perda_participacao,
)
