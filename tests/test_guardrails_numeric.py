"""Guardrail numerico.

Fonte sintetica de proposito: com um texto conhecido da para afirmar
exatamente o que tem e o que nao tem lastro.
"""

from __future__ import annotations

from assistant_hotel.guardrails.numeric import (
    allowed_numbers,
    check_numbers,
    check_years,
    extract_numbers,
)

SOURCE = (
    "delta_precio_compset_pct: 11,63\n"
    "profundidad_total_compset: 21,87\n"
    "reviews_count: 3330\n"
    "gb_cy: 1494870,06\n"
    "limiar: content_score < 0.70\n"
)


# --- extracao ---------------------------------------------------------------

def test_extrai_numeros_com_virgula_e_ponto():
    assert extract_numbers("11,63 e 21.87") == [11.63, 21.87]


def test_extrai_negativo():
    assert extract_numbers("caiu -10,5%") == [-10.5]


# --- com lastro -------------------------------------------------------------

def test_numero_presente_nao_e_acusado():
    assert check_numbers("Você está 11,63% acima do compset.", SOURCE) == []


def test_numero_presente_em_escala_maior_nao_e_acusado():
    assert check_numbers("Foram 3330 avaliações.", SOURCE) == []


def test_arredondamento_legitimo_nao_e_acusado():
    assert check_numbers("O faturamento foi de 1.494.870.", SOURCE) == []


def test_limiar_citado_nao_e_acusado():
    assert check_numbers("O corte é 0,70.", SOURCE) == []


def test_magnitude_de_valor_negativo_nao_e_acusada():
    """Citar a magnitude de um negativo e reformulacao, nao invencao."""
    source = "rn_yoy_pct: -10,5"
    assert check_numbers("A queda foi de 10,5%.", source) == []
    assert check_numbers("A queda foi de -10,5%.", source) == []


# --- sem lastro -------------------------------------------------------------

def test_numero_inventado_e_acusado():
    assert check_numbers("Você perde 45% das comparações.", SOURCE) == ["45"]


def test_varios_numeros_inventados():
    assert check_numbers("Perdeu 45% e ganhou 88%.", SOURCE) == ["45", "88"]


def test_resposta_sem_numero_nao_acusa():
    assert check_numbers("Sua ficha está incompleta.", SOURCE) == []


def test_ancora_do_teste_esta_no_lugar():
    """Se isto quebrar, os testes acima passaram por acidente."""
    allowed = allowed_numbers(SOURCE)
    assert 11.63 in allowed
    assert 1494870.06 in allowed
    assert 45.0 not in allowed


# --- anos -------------------------------------------------------------------

def test_ano_presente_na_fonte_nao_e_acusado():
    assert check_years("Dado de Q3/2025.", "cancel_rate_pct é de Q3/2025") == []


def test_ano_inventado_e_acusado():
    """O material nao traz datas: converter "90 dias" em data e invencao."""
    assert check_years("O período vai de out/2026 a jan/2027.", SOURCE) == [
        "2026",
        "2027",
    ]


def test_resposta_sem_ano_nao_acusa():
    assert check_years("Os próximos 90 dias.", SOURCE) == []
