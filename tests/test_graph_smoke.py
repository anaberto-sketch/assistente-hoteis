"""Topologia do grafo, sem rede.

O `FakeLLM` faz o papel do GenPlat. O que se testa aqui e o ROTEAMENTO e o que
chega no prompt -- nao a qualidade do texto que o modelo escreveria.
"""

from __future__ import annotations

from conftest import FakeLLM

from assistant_hotel.graph import Deps, build_graph


def _invoke(graph, question, hotel_id=None, history=None):
    state = {"question": question, "history": history or []}
    if hotel_id:
        state["hotel_id"] = hotel_id
    return graph.invoke(state)


# --- caminho feliz ----------------------------------------------------------

def test_responde_e_popula_o_diagnostico(graph, fake_llm):
    result = _invoke(graph, "como está meu hotel?", hotel_id="345798")

    assert result["answer"] == "Resposta de teste."
    assert result["diagnosis"]["hotel_id"] == "345798"
    assert [lever["id"] for lever in result["diagnosis"]["levers"]] == [
        "flag_precio_compset",
        "campanha_compset",
    ]
    assert len(fake_llm.calls) == 1


def test_resolve_hotel_pelo_nome(graph):
    result = _invoke(graph, "Hotel Atlântico Business Centro")
    assert result["hotel_id"] == "345798"


def test_o_prompt_recebe_o_fact_sheet_e_o_dicionario(graph, fake_llm):
    _invoke(graph, "estou caro?", hotel_id="345798")
    system = fake_llm.calls[0]["system"]

    assert "# FACT SHEET" in system
    assert "# LIMIARES DO PIPELINE DE RECOMENDAÇÕES" in system
    assert "# DICIONÁRIO DOS CAMPOS RELEVANTES PARA ESTA PERGUNTA" in system
    assert "flag_precio_compset" in system
    # A pergunta vai como mensagem do usuario, nao no system.
    assert fake_llm.calls[0]["messages"][-1]["content"] == "estou caro?"


def test_evidencia_da_alavanca_entra_no_prompt_mesmo_em_pergunta_vaga(
    graph, fake_llm
):
    _invoke(graph, "como está meu hotel?", hotel_id="345798")
    system = fake_llm.calls[0]["system"]

    assert "delta_precio_compset_pct=11,63" in system
    assert "profundidad_total_compset=21,87" in system


# --- idioma -----------------------------------------------------------------

def test_hotel_brasileiro_recebe_prompt_em_portugues(graph, fake_llm):
    _invoke(graph, "como está meu hotel?", hotel_id="345798")
    assert "Responda em português" in fake_llm.calls[0]["system"]


def test_hotel_dominicano_recebe_prompt_em_espanhol(graph, fake_llm):
    _invoke(graph, "cómo está mi hotel?", hotel_id="4038036")
    assert "Respondé en español" in fake_llm.calls[0]["system"]


# --- clarify ----------------------------------------------------------------

def test_hotel_inexistente_nao_chama_o_llm(graph, fake_llm):
    result = _invoke(graph, "Hotel Fantasma")

    assert result["hotel_id"] is None
    assert "Não encontrei esse hotel" in result["answer"]
    assert fake_llm.calls == []
    assert result.get("diagnosis") is None


def test_pergunta_nao_resolvida_mantem_o_hotel_atual(graph, fake_llm):
    """Com hotel ja definido, um texto que nao resolve nao troca o hotel.

    E o que faz "e o preco?" funcionar: a pergunta nao cita hotel nenhum, entao
    vale o hotel do turno anterior. Por isso o CLI sempre imprime de qual hotel
    esta respondendo -- sem isso, uma referencia que nao resolve passaria batido.
    """
    result = _invoke(graph, "Hotel Fantasma", hotel_id="345798")

    assert result["hotel_id"] == "345798"
    assert result["answer"] == "Resposta de teste."
    assert len(fake_llm.calls) == 1


# --- multi-turno ------------------------------------------------------------

def test_pergunta_de_acompanhamento_mantem_o_hotel(graph):
    result = _invoke(graph, "e o preço?", hotel_id="345798")
    assert result["hotel_id"] == "345798"


def test_historico_e_reenviado_ao_llm(graph, fake_llm):
    history = [
        {"role": "user", "content": "como está meu hotel?"},
        {"role": "assistant", "content": "Seu preço está acima do compset."},
    ]
    _invoke(graph, "e o preço?", hotel_id="345798", history=history)

    messages = fake_llm.calls[0]["messages"]
    assert messages[:2] == history
    assert messages[-1]["content"] == "e o preço?"


# --- guardrail numerico -----------------------------------------------------

def test_numero_sem_lastro_dispara_uma_regeneracao(repository, index):
    llm = FakeLLM(
        [
            "Você perde 45% das comparações de preço.",
            "Você está 11,63% acima do compset.",
        ]
    )
    graph = build_graph(Deps(repository=repository, index=index, llm=llm))

    result = _invoke(graph, "como está meu preço?", hotel_id="345798")

    assert len(llm.calls) == 2
    assert result["answer"] == "Você está 11,63% acima do compset."
    assert result["guardrail_flags"]
    assert "45" in result["guardrail_flags"][0]
    # A instrucao de correcao entra como ultimo turno do usuario.
    assert "45" in llm.calls[1]["messages"][-1]["content"]


def test_resposta_limpa_nao_dispara_regeneracao(graph, fake_llm):
    result = _invoke(graph, "como está meu preço?", hotel_id="345798")
    assert result["guardrail_flags"] == []
    assert len(fake_llm.calls) == 1


def test_resposta_truncada_e_sinalizada(repository, index):
    """Sem isso, um texto cortado no meio da frase passaria por completo."""
    llm = FakeLLM(["Uma resposta longa que foi cortada no meio"], stop_reason="max_tokens")
    graph = build_graph(Deps(repository=repository, index=index, llm=llm))

    result = _invoke(graph, "como está meu hotel?", hotel_id="345798")

    assert result["stop_reason"] == "max_tokens"
    assert any("truncada" in flag for flag in result["guardrail_flags"])
    # Nao adianta regenerar: bateria no mesmo teto.
    assert len(llm.calls) == 1
