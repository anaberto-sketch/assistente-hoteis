"""Credencial do Tompero: ausencia e um estado esperado, nao um crash."""

from __future__ import annotations

from dataclasses import replace

import pytest

from assistant_hotel.config import MissingTokenError, Settings, read_requester_token
from assistant_hotel.llm import GenPlatLLM


def test_token_ausente_levanta_missing_token(tmp_path):
    with pytest.raises(MissingTokenError):
        read_requester_token(tmp_path / "nao_existe")


def test_token_vazio_levanta_missing_token(tmp_path):
    path = tmp_path / "requester_token"
    path.write_text("   \n", encoding="utf-8")

    with pytest.raises(MissingTokenError):
        read_requester_token(path)


def test_token_presente_e_lido_sem_espacos(tmp_path):
    path = tmp_path / "requester_token"
    path.write_text("  abc123\n", encoding="utf-8")

    assert read_requester_token(path) == "abc123"


def test_missing_token_continua_sendo_file_not_found():
    """Compatibilidade: quem ja tratava FileNotFoundError segue tratando."""
    assert issubclass(MissingTokenError, FileNotFoundError)


def test_construir_o_cliente_nao_le_o_token(tmp_path):
    """Credencial preguicosa: sem token, o CLI ainda sobe e o diagnostico roda."""
    settings = replace(Settings.from_env(), token_path=tmp_path / "nao_existe")

    GenPlatLLM(settings)  # nao levanta


def test_a_leitura_do_token_so_acontece_no_generate(tmp_path):
    settings = replace(Settings.from_env(), token_path=tmp_path / "nao_existe")
    client = GenPlatLLM(settings)

    with pytest.raises(MissingTokenError):
        client.generate("system", [{"role": "user", "content": "oi"}])
