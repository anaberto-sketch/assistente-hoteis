"""Idioma da resposta: derivado do pais, nunca adivinhado pelo LLM."""

from __future__ import annotations

import pytest

from assistant_hotel.domain.language import language_for


@pytest.mark.parametrize("country", ["BR", "br", " Br "])
def test_brasil_responde_em_portugues(country):
    assert language_for(country) == "pt"


@pytest.mark.parametrize("country", ["DO", "AR", "MX", "CO", "CL", "PE", "US"])
def test_outros_paises_respondem_em_espanhol(country):
    assert language_for(country) == "es"


def test_pais_ausente_cai_em_espanhol():
    assert language_for(None) == "es"
