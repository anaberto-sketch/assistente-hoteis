"""Casos de ouro do diagnostico. Sem LLM, sem rede."""

from __future__ import annotations

from assistant_hotel.domain.diagnosis import diagnose


def _ids(diagnosis) -> list[str]:
    return [lever["id"] for lever in diagnosis["levers"]]


# --- (a) hotel saudavel -----------------------------------------------------

def test_hotel_saudavel_nao_aciona_nada(clean_row):
    result = diagnose(clean_row(), "TESTE")

    assert result["levers"] == []
    assert result["confidence"] == "high"
    assert result["data_quality"] == []
    # Todas as regras foram avaliadas e passaram.
    assert len(result["ok_checks"]) == 13


# --- (b) ordem das alavancas ------------------------------------------------

def test_alavancas_saem_ordenadas_por_severidade(clean_row):
    row = clean_row(
        total_lose_logueado_pct_35d=50.0,      # flag_precio_bkg        (high)
        profundidad_total_bkg_35d=3.0,         # brecha_bkg             (low)
        delta_precio_compset_pct=10.0,         # flag_precio_compset    (high)
        profundidad_total_compset=3.0,         # brecha_compset         (low)
        descuento_opaco_pct=10.0,
        avg_genius_discount_pct=12.0,          # flag_genius_mayor_opaco (medium)
    )
    result = diagnose(row, "TESTE")

    assert _ids(result) == [
        "flag_precio_bkg",
        "flag_precio_compset",
        "flag_genius_mayor_opaco",
        "brecha_bkg",
        "brecha_compset",
    ]


def test_brecha_grande_vira_campanha(clean_row):
    row = clean_row(
        total_lose_logueado_pct_35d=50.0,
        profundidad_total_bkg_35d=10.0,
        delta_precio_compset_pct=10.0,
        profundidad_total_compset=25.0,
    )
    result = diagnose(row, "TESTE")

    assert "campanha_bkg" in _ids(result)
    assert "campanha_compset" in _ids(result)


# --- (c) compset NULL -------------------------------------------------------

def test_sem_compset_suprime_alavancas_de_compset(clean_row):
    row = clean_row(
        perf_compset_rn_90d_cy=None,
        perf_rn_90d_cy=1.0,
        delta_precio_compset_pct=None,
        profundidad_total_compset=None,
    )
    result = diagnose(row, "TESTE")

    compset_levers = [
        lever
        for lever in result["levers"]
        if any("compset" in ref for ref in lever["field_refs"])
    ]
    assert compset_levers == []
    assert any("sem compset definido" in note for note in result["data_quality"])
    assert any("NULL não é zero" in note for note in result["data_quality"])


def test_compset_null_nao_vira_zero_nos_ok_checks(clean_row):
    """Regra sem campo-base NAO pode ser reportada como aprovada."""
    row = clean_row(delta_precio_compset_pct=None)
    result = diagnose(row, "TESTE")

    assert not any("delta_precio_compset_pct" in ok for ok in result["ok_checks"])
    assert any("delta_precio_compset_pct" in note for note in result["data_quality"])


# --- (d) confianca ----------------------------------------------------------

def test_ajuste_de_qualidade_nivel_3_derruba_a_confianca(clean_row):
    result = diagnose(clean_row(quality_adjustment_level=3), "TESTE")
    assert result["confidence"] == "low"


def test_ajuste_nivel_3_nao_rebaixa_severidade(clean_row):
    """Rebaixar severidade esconderia um problema real de preco."""
    row = clean_row(quality_adjustment_level=3, delta_precio_compset_pct=30.0)
    lever = next(
        item for item in diagnose(row, "TESTE")["levers"] if item["id"] == "flag_precio_compset"
    )
    assert lever["severity"] == "high"
    assert any("quality_adjustment_level=3" in caveat for caveat in lever["caveats"])


def test_ajuste_nivel_2_adiciona_ressalva(clean_row):
    row = clean_row(quality_adjustment_level=2, delta_precio_compset_pct=30.0)
    lever = next(
        item for item in diagnose(row, "TESTE")["levers"] if item["id"] == "flag_precio_compset"
    )
    assert lever["severity"] == "high"
    assert any("quality_adjustment_level=2" in caveat for caveat in lever["caveats"])


def test_poucas_avaliacoes_derruba_a_confianca(clean_row):
    result = diagnose(clean_row(reviews_count=49.0), "TESTE")
    assert result["confidence"] == "medium"


def test_poucas_avaliacoes_vira_ressalva_na_nota(clean_row):
    row = clean_row(reviews_count=10.0, rate_score=5.0)
    lever = next(
        item for item in diagnose(row, "TESTE")["levers"] if item["id"] == "nota_baixa"
    )
    assert any("Poucas avaliações" in caveat for caveat in lever["caveats"])


def test_amostra_pequena_vira_ressalva_na_tendencia(clean_row):
    row = clean_row(rn_yoy_pct=-40.0, bk_35d=10.0)
    lever = next(
        item for item in diagnose(row, "TESTE")["levers"] if item["id"] == "queda_yoy"
    )
    assert any("reservas nos últimos 35 dias" in caveat for caveat in lever["caveats"])


def test_cancel_rate_alto_gera_aviso_sem_causalidade(clean_row):
    result = diagnose(clean_row(cancel_rate_pct=45.0), "TESTE")
    note = next(
        item for item in result["data_quality"] if "cancel_rate_pct" in item
    )
    assert "não afirmar que piorou" in note
    assert "cancelamento" not in _ids(result)


# --- evidencias so com valores da linha -------------------------------------

def test_evidencia_nao_contem_valor_nulo(clean_row):
    row = clean_row(rate_score=5.0, reviews_count=None, star_rating=None)
    lever = next(
        item for item in diagnose(row, "TESTE")["levers"] if item["id"] == "nota_baixa"
    )
    assert lever["evidence"] == {"rate_score": 5.0}


def test_hotel_345798_dispara_preco_e_campanha_contra_compset(repository):
    """Caso do material: 11,63% acima do compset com profundidade 21,87."""
    row = repository.get("345798")
    result = diagnose(row, "345798")

    assert _ids(result) == ["flag_precio_compset", "campanha_compset"]
    lever = result["levers"][0]
    assert lever["evidence"]["delta_precio_compset_pct"] == 11.63
    assert lever["evidence"]["profundidad_total_compset"] == 21.87


def test_hotel_sem_compset_nao_fala_de_comparacao(repository):
    row = repository.get("4794164")
    result = diagnose(row, "4794164")

    assert not any("compset" in ref for lever in result["levers"] for ref in lever["field_refs"])
    assert any("sem compset definido" in note for note in result["data_quality"])
