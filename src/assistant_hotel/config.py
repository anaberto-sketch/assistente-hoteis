"""Configuracao central. Nada de credencial hardcoded."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Raiz do repositorio: src/assistant_hotel/config.py -> ../../..
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data"

# Token OAuth emitido pelo Tompero CLI. O GenPlat exige `Authorization: Bearer`,
# nao `x-api-key` (verificado: x-api-key devolve 401).
DEFAULT_TOKEN_PATH = Path.home() / ".config" / "tompero" / "requester_token"


@dataclass(frozen=True)
class Settings:
    genplat_base_url: str
    model: str
    token_path: Path
    data_dir: Path
    hotels_file: Path
    dictionary_file: Path
    max_tokens: int

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("ASSISTANT_HOTEL_DATA_DIR", DEFAULT_DATA_DIR))
        return cls(
            genplat_base_url=os.environ.get(
                "ANTHROPIC_BASE_URL",
                "https://generative-ai-platform-development.ifoodcorp.com.br/api/v2",
            ),
            model=os.environ.get("ASSISTANT_HOTEL_MODEL", "claude-sonnet-5-bedrock"),
            token_path=Path(
                os.environ.get("ASSISTANT_HOTEL_TOKEN_PATH", DEFAULT_TOKEN_PATH)
            ),
            data_dir=data_dir,
            hotels_file=Path(
                os.environ.get("ASSISTANT_HOTEL_HOTELS_FILE", data_dir / "hotels.csv")
            ),
            dictionary_file=Path(
                os.environ.get(
                    "ASSISTANT_HOTEL_DICTIONARY_FILE",
                    data_dir / "field_dictionary.yaml",
                )
            ),
            # 4000 e o teto de saida, nao um alvo. Uma resposta com 5 alavancas,
            # cada uma com numero, ressalva e acao, passava de 3000 e vinha
            # truncada no meio da frase. O prompt tambem pede ~500 palavras; o
            # teto existe so para o truncamento nunca ser silencioso.
            max_tokens=int(os.environ.get("ASSISTANT_HOTEL_MAX_TOKENS", "4000")),
        )


class MissingTokenError(FileNotFoundError):
    """Token do Tompero ausente ou vazio.

    Herda de FileNotFoundError para que quem ja tratava a ausencia do arquivo
    continue funcionando sem mudanca.
    """


def read_requester_token(path: Path | None = None) -> str:
    """Le o token do Tompero. Nunca logar o retorno."""
    token_path = path or Settings.from_env().token_path
    if not token_path.exists():
        raise MissingTokenError(
            f"Token do Tompero nao encontrado em {token_path}. "
            "Rode `tompero auth get requester-token`."
        )
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise MissingTokenError(f"Token do Tompero em {token_path} esta vazio.")
    return token
