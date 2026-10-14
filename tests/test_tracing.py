"""Tracing no Langfuse.

O que estes testes protegem, em ordem de importancia:

1. **Sem credencial, nada muda.** E o estado em que a suite inteira roda, e o
   estado de quem clona o repo sem Langfuse. Se isto quebrar, o projeto deixa
   de funcionar para quem nao usa observabilidade.
2. **Falha do Langfuse nao custa a resposta.** Um rastro nao pode derrubar o
   chat.
3. **O que vai para a span esta certo.** Modelo, tokens e custo -- errar a
   chave de `usage_details` produz custo vazio sem erro nenhum.

Nenhum teste aqui toca a rede: o cliente do Langfuse e substituido por um falso.
"""

from __future__ import annotations

import pytest

from assistant_hotel import tracing
from assistant_hotel.config import Settings
from assistant_hotel.llm import Completion, GenPlatLLM
from assistant_hotel.tracing import TracedLLM

from conftest import FakeLLM


@pytest.fixture(autouse=True)
def sem_credencial(monkeypatch):
    """Tira qualquer LANGFUSE_* do ambiente e esquece o cliente resolvido."""
    for chave in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        monkeypatch.delenv(chave, raising=False)
    tracing.reset()
    yield
    tracing.reset()


# --- 1. sem credencial, e um no-op ------------------------------------------

def test_sem_credencial_esta_desligado():
    assert tracing.enabled() is False
    assert tracing.client() is None


def test_sem_credencial_nada_e_impresso(capsys):
    """Construir o cliente desligado imprime um aviso do SDK -- nao chegamos la."""
    tracing.client()
    tracing.flush()

    assert capsys.readouterr().out == ""


def test_o_grafo_responde_igual_com_tracing_desligado(graph, fake_llm):
    """O resultado nao ganha nem perde campo por causa do tracing."""
    resultado = graph.invoke(
        {"question": "como está meu hotel?", "hotel_id": "345798"}
    )

    assert resultado["answer"] == "Resposta de teste."
    assert resultado["diagnosis"]["hotel_id"] == "345798"
    assert len(fake_llm.calls) == 1


def test_o_grafo_aceita_config_de_metadata(graph):
    """O CLI manda session_id pelo config; sem tracing isso nao pode quebrar."""
    resultado = graph.invoke(
        {"question": "como está meu hotel?", "hotel_id": "345798"},
        {"metadata": {"session_id": "abc123"}},
    )

    assert resultado["answer"] == "Resposta de teste."


# --- 2. falha do Langfuse nao derruba a resposta ----------------------------

class ClienteQuebrado:
    """Cliente que levanta em tudo, para provar que a falha fica contida."""

    def start_as_current_observation(self, **kwargs):
        raise RuntimeError("Langfuse fora do ar")

    def flush(self):
        raise RuntimeError("Langfuse fora do ar")


@pytest.fixture
def com_tracing_quebrado(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-falsa")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-falsa")
    tracing.reset()
    monkeypatch.setattr(tracing, "client", lambda: ClienteQuebrado())
    yield
    tracing.reset()


def test_llm_quebrado_ainda_responde(com_tracing_quebrado):
    """A observabilidade nao pode custar a resposta do usuario."""
    llm = TracedLLM(FakeLLM(["Resposta mesmo com o Langfuse quebrado"]))

    completion = llm.generate("system", [{"role": "user", "content": "oi"}])

    assert completion.text == "Resposta mesmo com o Langfuse quebrado"


def test_flush_quebrado_nao_levanta(com_tracing_quebrado):
    tracing.flush()


def test_span_quebrada_deixa_a_excecao_do_grafo_subir(monkeypatch):
    """Engolir erro do corpo seria pior que perder a span."""
    from assistant_hotel.config import MissingTokenError

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-falsa")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-falsa")
    tracing.reset()
    monkeypatch.setattr(tracing, "client", lambda: ClienteQuebrado())

    class SemToken:
        def generate(self, system, messages):
            raise MissingTokenError("sem token")

    with pytest.raises(MissingTokenError):
        TracedLLM(SemToken()).generate("system", [])


# --- 3. o que vai para a span -----------------------------------------------

class SpanFalsa:
    def __init__(self, nome, kwargs):
        self.nome = nome
        self.kwargs = kwargs
        self.atualizacoes: list[dict] = []

    def update(self, **kwargs):
        self.atualizacoes.append(kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ClienteFalso:
    def __init__(self):
        self.spans: list[SpanFalsa] = []

    def start_as_current_observation(self, name, **kwargs):
        span = SpanFalsa(name, kwargs)
        self.spans.append(span)
        return span


@pytest.fixture
def cliente_falso(monkeypatch):
    falso = ClienteFalso()
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-falsa")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-falsa")
    tracing.reset()
    monkeypatch.setattr(tracing, "client", lambda: falso)
    yield falso
    tracing.reset()


def test_a_span_de_geracao_leva_modelo_e_tokens(cliente_falso):
    class LLMComUso:
        model = "gpt-4.1"

        def generate(self, system, messages):
            return Completion(
                text="ok", stop_reason="end_turn", input_tokens=1000, output_tokens=500
            )

    TracedLLM(LLMComUso()).generate("system", [{"role": "user", "content": "oi"}])

    span = cliente_falso.spans[0]
    assert span.nome == "generate"
    assert span.kwargs["as_type"] == "generation"
    assert span.kwargs["model"] == "gpt-4.1"
    atualizacao = span.atualizacoes[-1]
    assert atualizacao["output"] == "ok"
    assert atualizacao["usage_details"] == {"input": 1000, "output": 500, "total": 1500}


def test_o_custo_nao_e_calculado_por_nos(cliente_falso):
    """O Langfuse precifica a partir do `model`; nos so mandamos tokens.

    Mandar `cost_details` proprio sobrescreveria a tabela dele e congelaria um
    preco que muda sem deploy nosso.
    """
    class LLMComUso:
        def generate(self, system, messages):
            return Completion(text="ok", input_tokens=1000, output_tokens=500)

    TracedLLM(LLMComUso()).generate("system", [])

    atualizacao = cliente_falso.spans[0].atualizacoes[-1]
    assert "cost_details" not in atualizacao
    assert atualizacao["usage_details"] == {"input": 1000, "output": 500, "total": 1500}


def test_a_span_de_geracao_manda_o_modelo_para_o_langfuse_precificar(cliente_falso):
    """Sem `model` na span, o Langfuse nao tem como inferir custo nenhum."""
    class LLMComUso:
        model = "gpt-4.1"

        def generate(self, system, messages):
            return Completion(text="ok", input_tokens=1, output_tokens=1)

    TracedLLM(LLMComUso()).generate("system", [])

    assert cliente_falso.spans[0].kwargs["model"] == "gpt-4.1"


def test_erro_do_modelo_marca_a_span(cliente_falso):
    from assistant_hotel.config import MissingTokenError

    class SemToken:
        def generate(self, system, messages):
            raise MissingTokenError("sem token")

    with pytest.raises(MissingTokenError):
        TracedLLM(SemToken()).generate("system", [])

    atualizacao = cliente_falso.spans[0].atualizacoes[-1]
    assert atualizacao["level"] == "ERROR"
    assert "MissingTokenError" in atualizacao["status_message"]


def test_texto_longo_e_cortado_na_span(cliente_falso):
    """O fact sheet inteiro em cada no inflaria o trace sem informar mais."""
    class LLMComUso:
        def generate(self, system, messages):
            return Completion(text="ok")

    TracedLLM(LLMComUso()).generate("x" * 10_000, [])

    enviado = cliente_falso.spans[0].kwargs["input"]["system"]
    assert len(enviado) < 10_000
    assert "cortado" in enviado


# --- a span da request ------------------------------------------------------

class GrafoFalso:
    """Grafo compilado de mentira: devolve o mesmo dict que o real devolveria."""

    def __init__(self):
        self.chamadas = []
        self.atributo_qualquer = "delegado"

    def invoke(self, state, config=None):
        self.chamadas.append((state, config))
        return {
            "answer": "resposta",
            "hotel_id": "345798",
            "hotel_name": "Hotel Teste",
            "language": "pt",
            "diagnosis": {"confidence": "medium", "levers": [{"id": "flag_preco"}]},
            "guardrail_flags": [],
            "stop_reason": "end_turn",
        }


def test_a_span_da_request_leva_pergunta_e_resumo(cliente_falso):
    from assistant_hotel.tracing import TracedGraph

    interno = GrafoFalso()
    resultado = TracedGraph(interno).invoke({"question": "estou caro?", "hotel_id": "1"})

    assert resultado["answer"] == "resposta"
    span = cliente_falso.spans[0]
    assert span.nome == "assistant-hotel"
    assert span.kwargs["input"]["question"] == "estou caro?"
    resumo = span.atualizacoes[-1]["output"]
    assert resumo["answer"] == "resposta"
    assert resumo["levers"] == ["flag_preco"]
    assert resumo["confidence"] == "medium"


def test_a_span_da_request_nao_manda_o_estado_inteiro(cliente_falso):
    """O estado carrega system_prompt e fact_sheet; mandar tudo infla o trace."""
    from assistant_hotel.tracing import TracedGraph

    TracedGraph(GrafoFalso()).invoke(
        {
            "question": "estou caro?",
            "system_prompt": "x" * 5000,
            "fact_sheet": "y" * 5000,
        }
    )

    entrada = cliente_falso.spans[0].kwargs["input"]
    assert set(entrada) == {"question", "hotel_id", "history"}


def test_traced_graph_delega_o_resto(cliente_falso):
    """`stream`, `get_graph` etc. seguem acessiveis."""
    from assistant_hotel.tracing import TracedGraph

    assert TracedGraph(GrafoFalso()).atributo_qualquer == "delegado"


def test_traced_graph_sem_config_funciona(cliente_falso):
    from assistant_hotel.tracing import TracedGraph

    interno = GrafoFalso()
    TracedGraph(interno).invoke({"question": "oi"})

    assert interno.chamadas == [({"question": "oi"}, None)]


def test_traced_graph_repassa_o_config(cliente_falso):
    from assistant_hotel.tracing import TracedGraph

    interno = GrafoFalso()
    config = {"metadata": {"session_id": "s1"}}
    TracedGraph(interno).invoke({"question": "oi"}, config)

    assert interno.chamadas == [({"question": "oi"}, config)]


# --- o formato que o Langfuse espera ----------------------------------------

def test_usage_details_usa_as_chaves_do_langfuse():
    """`input`/`output`/`total`, nao os nomes do SDK anthropic."""
    completion = Completion(text="ok", input_tokens=10, output_tokens=4)

    assert completion.usage_details() == {"input": 10, "output": 4, "total": 14}


def test_usage_details_vazio_quando_o_provedor_nao_informa():
    assert Completion(text="ok").usage_details() == {}


def test_usage_details_com_um_lado_so():
    assert Completion(text="ok", input_tokens=10).usage_details() == {
        "input": 10,
        "output": 0,
        "total": 10,
    }


# --- o modelo ---------------------------------------------------------------

def test_o_modelo_vem_do_cliente(tmp_path):
    """`TracedLLM` descobre o modelo pelo atributo, sem acoplar ao GenPlat."""
    from dataclasses import replace

    settings = replace(Settings.from_env(), token_path=tmp_path / "nao_existe")
    assert GenPlatLLM(settings).model == settings.model
    assert TracedLLM(GenPlatLLM(settings))._model == settings.model
