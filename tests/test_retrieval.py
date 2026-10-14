"""Retrieval lexico: foco e garantias de inclusao.

As garantias existem para que uma falha de recuperacao NUNCA vire uma resposta
errada. Por isso os testes aqui sao sobre INCLUSAO, nao sobre posicao no
ranking: com ~59 campos o retrieval e foco, nao dependencia de correcao.
"""

from __future__ import annotations

from assistant_hotel.domain.blocks import blocks_for
from assistant_hotel.retrieval.index import GUARANTEED, search
from assistant_hotel.retrieval.tokenize import normalize, tokens


def _names(docs) -> list[str]:
    return [doc["field"] for doc in docs]


# --- tokenizacao ------------------------------------------------------------

def test_normalize_remove_acentos_e_quebra_camel_case():
    assert "cvr search success" in normalize("cvrSearchSuccess")
    assert "preço" not in normalize("preço")
    assert "preco" in normalize("preço")


def test_tokens_quebra_underscore():
    assert "total" in tokens("total_lose_logueado_pct_35d")


# --- deteccao de bloco ------------------------------------------------------

def test_pergunta_de_preco_detecta_tarifas():
    assert blocks_for("quanto estou perdendo de preço?") == ["TARIFAS"]


def test_pergunta_de_venda_detecta_reservas_em_espanhol():
    assert "RESERVAS" in blocks_for("cuánto voy a vender este mes?")


def test_pergunta_de_nota_detecta_calidad():
    assert blocks_for("minha nota está boa?") == ["CALIDAD"]


def test_pergunta_vaga_nao_detecta_bloco_de_negocio():
    assert blocks_for("bom dia") == []


# --- busca ------------------------------------------------------------------

def test_pergunta_de_preco_traz_o_campo_de_perda(index):
    docs = search(index, "quanto estou perdendo de preço?", "pt")
    assert "total_lose_logueado_pct_35d" in _names(docs)


def test_pergunta_de_queda_traz_room_nights(index):
    docs = search(index, "as diárias caíram?", "pt")
    assert "rn_yoy_pct" in _names(docs)


def test_pergunta_vaga_ainda_cobre_os_cinco_blocos(index):
    docs = search(index, "bom dia", "pt")
    assert {doc["block"] for doc in docs} == {
        "Identificación",
        "EXPO",
        "RESERVAS",
        "TARIFAS",
        "CALIDAD",
    }


# --- garantia 1: inclusao obrigatoria ---------------------------------------

def test_campo_de_alavanca_entra_mesmo_sem_sinal_lexico(index):
    """O caso que faz "como esta meu hotel?" funcionar."""
    seeded = ["delta_precio_compset_pct", "profundidad_total_compset"]
    docs = search(index, "como está meu hotel?", "pt", must_include=seeded)

    names = _names(docs)
    for field in seeded:
        assert field in names

    garantidos = [doc for doc in docs if doc["score"] == GUARANTEED]
    assert {doc["field"] for doc in garantidos} == set(seeded)
    # Inclusao garantida ordena antes de qualquer match real.
    assert names[0] in seeded


def test_campo_desconhecido_em_must_include_e_ignorado(index):
    docs = search(index, "preço", "pt", must_include=["coluna_que_nao_existe"])
    assert "coluna_que_nao_existe" not in _names(docs)


# --- idioma do documento ----------------------------------------------------

def test_definicao_sai_no_idioma_pedido(index):
    pt = search(index, "preço", "pt", must_include=["target_asp"])
    es = search(index, "precio", "es", must_include=["target_asp"])

    doc_pt = next(d for d in pt if d["field"] == "target_asp")
    doc_es = next(d for d in es if d["field"] == "target_asp")
    assert doc_pt["definition"] != doc_es["definition"]


# --- garantia 4: fallback ---------------------------------------------------

def test_query_vazia_nao_devolve_lista_vazia(index):
    docs = search(index, "", "pt")
    assert docs
