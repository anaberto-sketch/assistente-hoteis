"""Fonte unica dos limiares do pipeline de recomendacoes.

ATENCAO a procedencia de cada constante:

  [MATERIAL]  numero dado explicitamente no material do time.
  [ENG]       default de engenharia. O material NAO da numero para este caso;
              o valor esta aqui para o codigo ter um comportamento definido e
              esta marcado para poder ser calibrado com o time. Nao trate como
              regra de negocio validada.

Este modulo tambem monta o "dossie de limiares": a lista fixa que vai SEMPRE no
prompt, sem passar por retrieval (um limiar nunca pode "nao ser encontrado").
"""

from __future__ import annotations

from ..state import Threshold

# --- CALIDAD ---------------------------------------------------------------
CONTENT_SCORE_MIN = 0.70          # [MATERIAL] "Menos de 0,70 se considera ficha incompleta"
RATE_SCORE_MIN = 7.5              # [MATERIAL] "Menos de 7,5 se considera bajo"
REVIEWS_COUNT_MIN_RELIABLE = 50   # [MATERIAL] "Pocas reseñas (menos de 50) hacen que el rate_score sea poco confiable"
CANCEL_RATE_ALTO = 40.0           # [MATERIAL] "Mas de 40% se considera alta, como referencia orientativa"

# --- TARIFAS ---------------------------------------------------------------
TOTAL_LOSE_BKG_MAX = 30.0         # [MATERIAL] "Mas de 30% prende el flag de precio vs Booking"
DELTA_PRECIO_COMPSET_MAX = 5.0    # [MATERIAL] "Mas de 5% se considera caro"
DESCUENTO_OPACO_MIN = 5.0         # [MATERIAL] "Menos de 5 = descuento insuficiente"
DESCUENTO_PACKAGE_MIN = 10.0      # [MATERIAL] "Menos de 10 = descuento bajo para venta en paquete"
GENIUS_OVER_OPACO_MARGIN = 1.0    # [MATERIAL] "el descuento Genius es mas de 1 punto mayor que el opaco"
PROFUNDIDAD_BRECHA_GRANDE = 10.0  # [MATERIAL] "Menos de 10 = apenas fuera de paridad... 10 o mas = brecha grande"
LOSE_RATE_ALTO = 30.0             # [MATERIAL] "Mas de 30 es alto"
APPEARANCES_BAIXO = 50.0          # [ENG]      o material diz "appearances_pct bajo" sem dar numero
QUALITY_ADJUSTMENT_MIN_LEVEL = 1  # [MATERIAL] nivel 1 = ajuste completo
QUALITY_ADJUSTMENT_UNRELIABLE = 3 # [MATERIAL] nivel 3 = sem ajuste

# --- RESERVAS --------------------------------------------------------------
RN_YOY_DROP_RELEVANT = -10.0      # [MATERIAL] "Una caida de mas de 10% se considera relevante para el pipeline"
COMPSET_RN_RATIO_MIN = 0.95       # [MATERIAL] "menos de 95% de los room nights del compset"
BK_35D_AMOSTRA_PEQUENA = 30       # [ENG]      o material diz "pocas reservas" sem dar numero


def threshold_dossier() -> list[Threshold]:
    """Os limiares que vao sempre no prompt. Funcao pura."""
    return [
        Threshold(
            id="content_score",
            block="CALIDAD",
            rule=f"content_score < {CONTENT_SCORE_MIN}",
            meaning_pt="Ficha incompleta (fotos, descrição, amenities). Dispara a alavanca de completar a ficha.",
            meaning_es="Ficha incompleta (fotos, descripción, amenities). Dispara la palanca de completar la ficha.",
        ),
        Threshold(
            id="rate_score",
            block="CALIDAD",
            rule=f"rate_score < {RATE_SCORE_MIN}",
            meaning_pt="Nota de avaliações baixa. Comparar também com a média do destino.",
            meaning_es="Puntaje de reseñas bajo. Comparar también con el promedio del destino.",
        ),
        Threshold(
            id="reviews_count",
            block="CALIDAD",
            rule=f"reviews_count < {REVIEWS_COUNT_MIN_RELIABLE}",
            meaning_pt="Poucas avaliações: a nota fica pouco confiável. É ressalva, não alavanca.",
            meaning_es="Pocas reseñas: el puntaje queda poco confiable. Es una salvedad, no una palanca.",
        ),
        Threshold(
            id="cancel_rate_pct",
            block="CALIDAD",
            rule=f"cancel_rate_pct > {CANCEL_RATE_ALTO}",
            meaning_pt="Taxa de cancelamento alta como referência orientativa. Dado de Q3/2025 e sem comparativo com o destino: não afirmar que piorou nem que é melhor ou pior que o mercado.",
            meaning_es="Tasa de cancelación alta como referencia orientativa. Dato de Q3 2025 y sin comparación contra el destino: no afirmar que empeoró ni que es mejor o peor que el mercado.",
        ),
        Threshold(
            id="total_lose_logueado_pct_35d",
            block="TARIFAS",
            rule=f"total_lose_logueado_pct_35d > {TOTAL_LOSE_BKG_MAX}",
            meaning_pt="Perde paridade contra o Booking em mais de 30% das comparações (usuário logado, 35 dias).",
            meaning_es="Pierde paridad contra Booking en más del 30% de las comparaciones (usuario logueado, 35 días).",
        ),
        Threshold(
            id="delta_precio_compset_pct",
            block="TARIFAS",
            rule=f"delta_precio_compset_pct > {DELTA_PRECIO_COMPSET_MAX}",
            meaning_pt="Preço acima do compset depois de ajustar por qualidade. Já considera estrelas e rate score.",
            meaning_es="Precio por encima del compset tras ajustar por calidad. Ya considera estrellas y rate score.",
        ),
        Threshold(
            id="descuento_opaco_pct",
            block="TARIFAS",
            rule=f"descuento_opaco_pct < {DESCUENTO_OPACO_MIN}",
            meaning_pt="Desconto opaco insuficiente. A tarifa opaca não revela o nome do hotel até a compra.",
            meaning_es="Descuento opaco insuficiente. La tarifa opaca no revela el nombre del hotel hasta la compra.",
        ),
        Threshold(
            id="descuento_package_pct",
            block="TARIFAS",
            rule=f"descuento_package_pct < {DESCUENTO_PACKAGE_MIN}",
            meaning_pt="Desconto baixo para venda em pacote.",
            meaning_es="Descuento bajo para venta en paquete.",
        ),
        Threshold(
            id="genius_vs_opaco",
            block="TARIFAS",
            rule=f"avg_genius_discount_pct > descuento_opaco_pct + {GENIUS_OVER_OPACO_MARGIN}",
            meaning_pt="O hotel dá mais desconto ao Booking (Genius) do que ao desconto opaco próprio. Causa comum de perda de paridade.",
            meaning_es="El hotel da más descuento a Booking (Genius) que al descuento opaco propio. Causa común de pérdida de paridad.",
        ),
        Threshold(
            id="profundidad",
            block="TARIFAS",
            rule=f"profundidad_total_* < {PROFUNDIDAD_BRECHA_GRANDE} vs >= {PROFUNDIDAD_BRECHA_GRANDE}",
            meaning_pt="Menos de 10 = apenas fora de paridade, corrige-se ajustando a tarifa. 10 ou mais = brecha grande, costuma exigir campanha.",
            meaning_es="Menos de 10 = apenas fuera de paridad, se corrige ajustando la tarifa. 10 o más = brecha grande, suele requerir campaña.",
        ),
        Threshold(
            id="lose_rate_on_compete_pct",
            block="TARIFAS",
            rule=f"lose_rate_on_compete_pct > {LOSE_RATE_ALTO}",
            meaning_pt="Perde para outro fornecedor nas vezes em que competiu. Alto junto com appearances_pct alto indica problema real de preço.",
            meaning_es="Pierde contra otro proveedor en las veces que compitió. Alto junto con appearances_pct alto indica problema real de precio.",
        ),
        Threshold(
            id="rn_yoy_pct",
            block="RESERVAS",
            rule=f"rn_yoy_pct < {RN_YOY_DROP_RELEVANT}",
            meaning_pt="Queda de room nights contra o ano anterior acima de 10% é considerada relevante pelo pipeline.",
            meaning_es="Caída de room nights contra el año anterior por encima de 10% es considerada relevante por el pipeline.",
        ),
        Threshold(
            id="compset_rn_90d",
            block="RESERVAS",
            rule=f"rn_90d do hotel < {COMPSET_RN_RATIO_MIN} x compset",
            meaning_pt="Vende menos room nights futuros que os concorrentes diretos. NULL = sem compset definido, não é zero.",
            meaning_es="Vende menos room nights futuros que los competidores directos. NULL = sin compset definido, no es cero.",
        ),
    ]
