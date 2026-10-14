"""Uma regra por teste, com FRONTEIRA.

O material usa `<` e `>` estritos. Testar so o caso obvio ("nota 5 dispara")
nao pega o erro classico de trocar `<` por `<=` na refatoracao. Por isso cada
limiar e testado dos DOIS lados, no valor exato.
"""

from __future__ import annotations

import pytest

from assistant_hotel.domain import rules as R


# --- content_score < 0.70 ---------------------------------------------------

def test_ficha_incompleta_dispara_abaixo_de_070(clean_row):
    assert R.rule_completa_ficha(clean_row(content_score=0.699)) is not None


def test_ficha_incompleta_nao_dispara_no_valor_exato(clean_row):
    assert R.rule_completa_ficha(clean_row(content_score=0.70)) is None


def test_ficha_incompleta_ignora_null(clean_row):
    assert R.rule_completa_ficha(clean_row(content_score=None)) is None


# --- rate_score < 7.5 -------------------------------------------------------

def test_nota_baixa_dispara_abaixo_de_75(clean_row):
    assert R.rule_nota_baixa(clean_row(rate_score=7.49)) is not None


def test_nota_baixa_nao_dispara_no_valor_exato(clean_row):
    assert R.rule_nota_baixa(clean_row(rate_score=7.5)) is None


# --- total_lose_logueado_pct_35d > 30 ---------------------------------------

def test_preco_bkg_dispara_acima_de_30(clean_row):
    assert R.rule_precio_bkg(clean_row(total_lose_logueado_pct_35d=30.1)) is not None


def test_preco_bkg_nao_dispara_no_valor_exato(clean_row):
    assert R.rule_precio_bkg(clean_row(total_lose_logueado_pct_35d=30.0)) is None


# --- delta_precio_compset_pct > 5 -------------------------------------------

def test_preco_compset_dispara_acima_de_5(clean_row):
    assert R.rule_precio_compset(clean_row(delta_precio_compset_pct=5.1)) is not None


def test_preco_compset_nao_dispara_no_valor_exato(clean_row):
    assert R.rule_precio_compset(clean_row(delta_precio_compset_pct=5.0)) is None


# --- descuento_opaco_pct < 5 ------------------------------------------------

def test_opaco_dispara_abaixo_de_5(clean_row):
    assert R.rule_opaco(clean_row(descuento_opaco_pct=4.9)) is not None


def test_opaco_nao_dispara_no_valor_exato(clean_row):
    assert R.rule_opaco(clean_row(descuento_opaco_pct=5.0)) is None


# --- descuento_package_pct < 10 ---------------------------------------------

def test_package_dispara_abaixo_de_10(clean_row):
    assert R.rule_package(clean_row(descuento_package_pct=9.9)) is not None


def test_package_nao_dispara_no_valor_exato(clean_row):
    assert R.rule_package(clean_row(descuento_package_pct=10.0)) is None


# --- avg_genius_discount_pct > descuento_opaco_pct + 1 ----------------------

def test_genius_dispara_acima_da_margem(clean_row):
    row = clean_row(descuento_opaco_pct=10.0, avg_genius_discount_pct=11.1)
    assert R.rule_genius_mayor_opaco(row) is not None


def test_genius_nao_dispara_na_margem_exata(clean_row):
    row = clean_row(descuento_opaco_pct=10.0, avg_genius_discount_pct=11.0)
    assert R.rule_genius_mayor_opaco(row) is None


def test_genius_sem_opaco_nao_avalia(clean_row):
    row = clean_row(descuento_opaco_pct=None, avg_genius_discount_pct=20.0)
    assert R.rule_genius_mayor_opaco(row) is None


# --- profundidade (gatilho: so faz sentido se ha problema de preco) ---------

def test_brecha_pequena_quando_profundidade_abaixo_de_10(clean_row):
    row = clean_row(total_lose_logueado_pct_35d=50.0, profundidad_total_bkg_35d=9.9)
    lever = R.rule_profundidad_bkg(row)
    assert lever is not None
    assert lever["id"] == "brecha_bkg"
    assert lever["severity"] == "low"


def test_campanha_quando_profundidade_de_10_ou_mais(clean_row):
    row = clean_row(total_lose_logueado_pct_35d=50.0, profundidad_total_bkg_35d=10.0)
    lever = R.rule_profundidad_bkg(row)
    assert lever is not None
    assert lever["id"] == "campanha_bkg"
    assert lever["severity"] == "medium"


def test_profundidade_bkg_nao_avalia_sem_perda_de_preco(clean_row):
    row = clean_row(total_lose_logueado_pct_35d=30.0, profundidad_total_bkg_35d=50.0)
    assert R.rule_profundidad_bkg(row) is None


def test_profundidade_compset_nao_avalia_sem_delta(clean_row):
    row = clean_row(delta_precio_compset_pct=5.0, profundidad_total_compset=50.0)
    assert R.rule_profundidad_compset(row) is None


# --- problema_preco_real ----------------------------------------------------

def test_problema_preco_real_dispara_com_aparicoes_baixas_e_perda_alta(clean_row):
    row = clean_row(appearances_pct=49.9, lose_rate_on_compete_pct=30.1)
    assert R.rule_problema_preco_real(row) is not None


def test_problema_preco_real_nao_dispara_com_aparicoes_no_limite(clean_row):
    row = clean_row(appearances_pct=50.0, lose_rate_on_compete_pct=80.0)
    assert R.rule_problema_preco_real(row) is None


def test_problema_preco_real_nao_dispara_com_perda_no_limite(clean_row):
    row = clean_row(appearances_pct=10.0, lose_rate_on_compete_pct=30.0)
    assert R.rule_problema_preco_real(row) is None


# --- compset: NULL nao e zero -----------------------------------------------

def test_compset_null_nao_e_comparavel(clean_row):
    assert R.compset_is_comparable(clean_row(perf_compset_rn_90d_cy=None)) is False


def test_compset_zero_nao_e_comparavel(clean_row):
    assert R.compset_is_comparable(clean_row(perf_compset_rn_90d_cy=0.0)) is False


def test_rn_below_compset_suprimida_com_compset_null(clean_row):
    row = clean_row(perf_compset_rn_90d_cy=None, perf_rn_90d_cy=1.0)
    assert R.rule_rn_below_compset(row) is None


def test_rn_below_compset_dispara_abaixo_de_95_por_cento(clean_row):
    row = clean_row(perf_compset_rn_90d_cy=1000.0, perf_rn_90d_cy=949.9)
    assert R.rule_rn_below_compset(row) is not None


def test_rn_below_compset_nao_dispara_no_valor_exato(clean_row):
    row = clean_row(perf_compset_rn_90d_cy=1000.0, perf_rn_90d_cy=950.0)
    assert R.rule_rn_below_compset(row) is None


# --- rn_yoy_pct < -10 -------------------------------------------------------

def test_queda_yoy_dispara_abaixo_de_menos_10(clean_row):
    assert R.rule_queda_yoy(clean_row(rn_yoy_pct=-10.1)) is not None


def test_queda_yoy_nao_dispara_no_valor_exato(clean_row):
    assert R.rule_queda_yoy(clean_row(rn_yoy_pct=-10.0)) is None


# --- perda de participacao --------------------------------------------------

def test_perda_participacao_dispara_quando_hotel_cresce_menos(clean_row):
    row = clean_row(hotel_growth_pct=4.9, dest_growth_pct=5.0)
    assert R.rule_perda_participacao(row) is not None


def test_perda_participacao_nao_dispara_empatado(clean_row):
    row = clean_row(hotel_growth_pct=5.0, dest_growth_pct=5.0)
    assert R.rule_perda_participacao(row) is None


# --- num(): booleano nunca e numero -----------------------------------------

@pytest.mark.parametrize("value", [True, False])
def test_booleano_nao_e_numero(clean_row, value):
    assert R.num(clean_row(rate_score=value), "rate_score") is None


def test_num_le_float(clean_row):
    assert R.num(clean_row(rate_score=7), "rate_score") == 7.0
