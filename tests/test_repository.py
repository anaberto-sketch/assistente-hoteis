"""Lookup do hotel. Este e o caminho NAO-RAG do sistema."""

from __future__ import annotations

from assistant_hotel.data.schemas import normalize_value


def test_base_tem_vinte_hoteis(repository):
    assert len(repository.all_ids()) == 20


def test_lookup_por_id(repository):
    row = repository.get("345798")
    assert row is not None
    assert row["hotel_name"] == "Hotel Atlântico Business Centro"


def test_id_inexistente_devolve_none(repository):
    assert repository.get("000000") is None


def test_lookup_por_nome_exato(repository):
    hits = repository.find_by_name("Windsor Tower Hotel")
    assert hits and hits[0]["hotel_id"] == "4479125"


def test_lookup_por_nome_parcial(repository):
    hits = repository.find_by_name("Windsor Tower")
    assert hits and hits[0]["hotel_id"] == "4479125"


def test_nome_sem_relacao_nao_casa(repository):
    assert repository.find_by_name("como está meu hotel?") == []


def test_todo_nome_da_base_resolve_para_si_mesmo(repository):
    for hotel_id in repository.all_ids():
        row = repository.get(hotel_id)
        hits = repository.find_by_name(row["hotel_name"])
        assert hits, f"{row['hotel_name']} nao resolveu"
        assert hits[0]["hotel_id"] == hotel_id


# --- normalizacao de valores ------------------------------------------------

def test_virgula_decimal_vira_ponto():
    assert normalize_value("rate_score", "7,5") == 7.5


def test_aspas_de_milhar_com_decimal():
    assert normalize_value("gb_cy", "1.494.870,06") == 1494870.06


def test_string_vazia_vira_null_e_nunca_zero():
    assert normalize_value("perf_compset_rn_90d_cy", "") is None


def test_null_do_csv_vira_none(repository):
    row = repository.get("4794164")
    assert row["perf_compset_rn_90d_cy"] is None
    assert row["perf_compset_rn_90d_cy"] != 0


def test_faixa_de_ap_permanece_string(repository):
    row = repository.get("345798")
    assert isinstance(row["worst_ap_compset"], str)
    assert row["worst_ap_compset"] == "046-090"


def test_flags_do_csv_viram_bool(repository):
    row = repository.get("345798")
    assert row["flag_precio_compset"] is True
    assert row["flag_package"] is False
