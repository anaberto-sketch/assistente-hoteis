"""Motor do diagnostico: roda as regras e aplica os modificadores.

Saida: um `Diagnosis` com as alavancas acionadas, as regras avaliadas e NAO
acionadas, os avisos de qualidade de dado e um nivel de confianca.

O LLM nao participa de nada aqui. Este e o ponto que impede o modelo de
"descobrir" flags por conta propria.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..state import Confidence, Diagnosis, Lever, SEVERITY_ORDER
from . import rules as R
from . import thresholds as T
from .models import HotelRow

# --------------------------------------------------------------------------
# Especificacao de cada regra: o que ela checa e o que dizer quando NAO aciona.
# `primary_field` e o campo cuja ausencia torna a regra inavaliavel.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleSpec:
    fn: Callable[[HotelRow], Lever | None]
    primary_field: str
    ok_text: str


RULE_SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(R.rule_completa_ficha, "content_score",
             f"content_score >= {T.CONTENT_SCORE_MIN}"),
    RuleSpec(R.rule_nota_baixa, "rate_score",
             f"rate_score >= {T.RATE_SCORE_MIN}"),
    RuleSpec(R.rule_precio_bkg, "total_lose_logueado_pct_35d",
             f"total_lose_logueado_pct_35d <= {T.TOTAL_LOSE_BKG_MAX}"),
    RuleSpec(R.rule_precio_compset, "delta_precio_compset_pct",
             f"delta_precio_compset_pct <= {T.DELTA_PRECIO_COMPSET_MAX}"),
    RuleSpec(R.rule_opaco, "descuento_opaco_pct",
             f"descuento_opaco_pct >= {T.DESCUENTO_OPACO_MIN}"),
    RuleSpec(R.rule_package, "descuento_package_pct",
             f"descuento_package_pct >= {T.DESCUENTO_PACKAGE_MIN}"),
    RuleSpec(R.rule_genius_mayor_opaco, "avg_genius_discount_pct",
             "avg_genius_discount_pct <= descuento_opaco_pct + 1"),
    RuleSpec(R.rule_profundidad_bkg, "profundidad_total_bkg_35d",
             "profundidad vs Booking dentro do esperado"),
    RuleSpec(R.rule_profundidad_compset, "profundidad_total_compset",
             "profundidad vs compset dentro do esperado"),
    RuleSpec(R.rule_problema_preco_real, "appearances_pct",
             "compete e vence na maioria das comparações"),
    RuleSpec(R.rule_rn_below_compset, "perf_rn_90d_cy",
             f"perf_rn_90d_cy >= {T.COMPSET_RN_RATIO_MIN} x compset"),
    RuleSpec(R.rule_queda_yoy, "rn_yoy_pct",
             f"rn_yoy_pct >= {T.RN_YOY_DROP_RELEVANT}"),
    RuleSpec(R.rule_perda_participacao, "hotel_growth_pct",
             "hotel_growth_pct >= dest_growth_pct"),
)

# Alavancas cuja comparacao de preco depende do ajuste por qualidade.
PRICE_COMPARISON_LEVERS = frozenset({
    "flag_precio_bkg",
    "flag_precio_compset",
    "brecha_bkg",
    "campanha_bkg",
    "brecha_compset",
    "campanha_compset",
    "problema_preco_real",
})

# Alavancas de tendencia, sensiveis a amostra pequena nos ultimos 35 dias.
TREND_LEVERS = frozenset({"queda_yoy", "perda_participacao"})

def diagnose(row: HotelRow, hotel_id: str) -> Diagnosis:
    """Aplica todas as regras e devolve o diagnostico completo."""
    levers: list[Lever] = []
    ok_checks: list[str] = []
    data_quality: list[str] = []

    for spec in RULE_SPECS:
        # Se o campo-base nem existe, a regra nao foi avaliada: nao podemos
        # afirmar nem que passou nem que falhou.
        if R.num(row, spec.primary_field) is None and row.get(spec.primary_field) is None:
            _note(
                data_quality,
                f"{spec.primary_field} ausente: regra '{spec.ok_text}' não avaliada.",
            )
            continue
        lever = spec.fn(row)
        if lever is None:
            ok_checks.append(spec.ok_text)
        else:
            levers.append(lever)

    _apply_modifiers(row, levers, data_quality)
    _collect_data_quality(row, data_quality)

    levers.sort(key=lambda lv: (SEVERITY_ORDER[lv["severity"]], lv["block"], lv["id"]))

    return Diagnosis(
        hotel_id=hotel_id,
        levers=levers,
        ok_checks=ok_checks,
        data_quality=data_quality,
        confidence=_confidence(row),
    )


def _note(notes: list[str], message: str) -> None:
    """Adiciona um aviso sem repetir."""
    if message not in notes:
        notes.append(message)


def _apply_modifiers(
    row: HotelRow, levers: list[Lever], data_quality: list[str]
) -> None:
    """Ajusta caveats depois que as regras rodaram.

    IMPORTANTE: o nivel de ajuste de qualidade NAO altera a severidade. O
    material diz apenas que a comparacao de preco fica menos confiavel quando o
    ajuste e parcial (nivel 2) ou inexistente (nivel 3). Rebaixar severidade
    esconderia um problema real de preco, que e o oposto do que o hoteleiro
    precisa. O nivel afeta o caveat e o nivel de confianca do diagnostico.
    """
    qal = R.num(row, "quality_adjustment_level")
    reviews = R.num(row, "reviews_count")
    bk_35d = R.num(row, "bk_35d")

    for lever in levers:
        if lever["id"] in PRICE_COMPARISON_LEVERS:
            if qal == T.QUALITY_ADJUSTMENT_UNRELIABLE:
                lever["caveats"].append(
                    "Comparação de preço sem nenhum ajuste de qualidade "
                    "(quality_adjustment_level=3): trate como indicação, não como conclusão."
                )
            elif qal == 2:
                lever["caveats"].append(
                    "Comparação de preço ajustada apenas por estrelas "
                    "(quality_adjustment_level=2): rate score e reviews não entraram no ajuste."
                )

        # Poucas avaliacoes tornam a nota instavel.
        if lever["id"] == "nota_baixa" and reviews is not None and reviews < T.REVIEWS_COUNT_MIN_RELIABLE:
            lever["caveats"].append(
                f"Poucas avaliações ({int(reviews)}): a nota é pouco confiável."
            )

        # Amostra pequena torna tendencia ruidosa.
        if lever["id"] in TREND_LEVERS and bk_35d is not None and bk_35d < T.BK_35D_AMOSTRA_PEQUENA:
            lever["caveats"].append(
                f"Poucas reservas nos últimos 35 dias ({int(bk_35d)}): a tendência é ruidosa."
            )

    if qal == T.QUALITY_ADJUSTMENT_UNRELIABLE:
        _note(
            data_quality,
            "quality_adjustment_level=3: a comparação de preço contra o compset não tem "
            "ajuste de qualidade.",
        )


def _collect_data_quality(row: HotelRow, data_quality: list[str]) -> None:
    """Avisos que nao sao alavanca, mas mudam como o dado deve ser lido."""
    reviews = R.num(row, "reviews_count")
    if reviews is not None and reviews < T.REVIEWS_COUNT_MIN_RELIABLE:
        _note(
            data_quality,
            f"reviews_count={int(reviews)} < {T.REVIEWS_COUNT_MIN_RELIABLE}: "
            "o rate_score é pouco confiável.",
        )

    cancel = R.num(row, "cancel_rate_pct")
    if cancel is not None and cancel > T.CANCEL_RATE_ALTO:
        _note(
            data_quality,
            f"cancel_rate_pct={cancel} é de Q3/2025 e não tem comparação com o destino: "
            "não afirmar que piorou, nem que é melhor ou pior que o mercado.",
        )

    if not R.compset_is_comparable(row):
        compset = row.get("perf_compset_rn_90d_cy")
        if compset is None:
            motivo = "perf_compset_rn_90d_cy=NULL (sem compset definido)"
        else:
            motivo = f"perf_compset_rn_90d_cy={compset} (compset zerado)"
        _note(
            data_quality,
            f"{motivo}: não é possível comparar room nights futuros com concorrentes. "
            "NULL não é zero.",
        )

    bk_35d = R.num(row, "bk_35d")
    if bk_35d is not None and bk_35d < T.BK_35D_AMOSTRA_PEQUENA:
        _note(
            data_quality,
            f"bk_35d={int(bk_35d)} é uma amostra pequena: leia as métricas de 35 dias "
            "com cautela.",
        )


def _confidence(row: HotelRow) -> Confidence:
    qal = R.num(row, "quality_adjustment_level")
    if qal == T.QUALITY_ADJUSTMENT_UNRELIABLE:
        base: Confidence = "low"
    elif qal == 2:
        base = "medium"
    else:
        base = "high"

    reviews = R.num(row, "reviews_count")
    if reviews is not None and reviews < T.REVIEWS_COUNT_MIN_RELIABLE and base == "high":
        base = "medium"
    return base
