"""Guardrail numerico: nenhum numero na resposta pode estar sem lastro.

O principio e simples e auto-mantido: **a resposta so pode citar numeros que
aparecem no material entregue ao modelo**. Esse material e o proprio system
prompt (fact sheet + dossie de limiares + dicionario), entao a lista de numeros
permitidos e extraida DELE, nao montada a mao. Assim o guardrail nao desatualiza
quando um limiar muda.

Detalhe que decide se isto funciona na pratica: separador de milhar e decimal
sao ambiguos. "1.494.870" e "1.494" tem a mesma forma. Em vez de adivinhar,
cada token vira um CONJUNTO de leituras plausiveis e o token so e acusado se
NENHUMA delas tiver lastro. O guardrail erra para o lado de nao acusar: quem
impede a invencao e o recorte do prompt (guardrail 1), isto aqui e a rede.
"""

from __future__ import annotations

import re
from typing import Iterable

# Numero com separador de milhar opcional e parte decimal opcional.
# Casa "42,1", "1.494.870,06", "0.70", "1494870", "-10".
_NUMBER = re.compile(r"-?\d+(?:[.\s]\d{3})*(?:[.,]\d+)?")


def _readings(token: str) -> set[float]:
    """Todas as leituras numericas plausiveis de um token."""
    token = token.replace(" ", "").replace(" ", "")
    readings: set[float] = set()

    has_comma = "," in token
    has_dot = "." in token

    if has_comma and has_dot:
        # O separador mais a direita e o decimal.
        if token.rfind(",") > token.rfind("."):
            candidates = [token.replace(".", "").replace(",", ".")]
        else:
            candidates = [token.replace(",", "")]
        # E a leitura oposta, caso o modelo tenha invertido a convencao.
        candidates.append(token.replace(",", "").replace(".", ""))
    elif has_comma:
        candidates = [token.replace(",", ".")]
        if _looks_like_thousands(token, ","):
            candidates.append(token.replace(",", ""))
    elif has_dot:
        candidates = [token]
        if _looks_like_thousands(token, "."):
            candidates.append(token.replace(".", ""))
    else:
        candidates = [token]

    for candidate in candidates:
        try:
            readings.add(float(candidate))
        except ValueError:
            continue
    return readings


def _looks_like_thousands(token: str, separator: str) -> bool:
    head, _, tail = token.rpartition(separator)
    return bool(head) and len(tail) == 3 and tail.isdigit()


def extract_numbers(text: str) -> list[float]:
    """Todos os numeros citados num texto, ja normalizados."""
    found: list[float] = []
    for match in _NUMBER.finditer(text):
        readings = _readings(match.group(0))
        if len(readings) == 1:
            found.append(next(iter(readings)))
    return found


def allowed_numbers(source: str, extra: Iterable[float] = ()) -> set[float]:
    """Numeros que aparecem no material entregue ao modelo.

    Inclui os arredondamentos de cada valor: arredondar um numero que existe e
    uma reformulacao legitima ("1.494.870" para 1494870,06), nao uma invencao.
    Sem isso o guardrail acusaria toda resposta que arredonda e gastaria uma
    regeneracao a toa.
    """
    allowed: set[float] = set(extra)
    for match in _NUMBER.finditer(source):
        for value in _readings(match.group(0)):
            allowed.add(value)
            allowed.add(round(value, 2))
            allowed.add(round(value, 1))
            allowed.add(float(round(value)))
            # Citar a magnitude de um valor negativo e reformulacao legitima:
            # "a diferenca e de 25,92%" para delta_precio_compset_pct = -25,92.
            allowed.add(abs(value))
    return allowed


def check_numbers(
    answer: str, source: str, extra: Iterable[float] = ()
) -> list[str]:
    """Tokens da resposta sem lastro no material. Devolve os tokens originais."""
    allowed = allowed_numbers(source, extra)
    offenders: list[str] = []

    for match in _NUMBER.finditer(answer):
        token = match.group(0)
        readings = _readings(token)
        if not readings:
            continue
        if readings & allowed:
            continue
        offenders.append(token)
    return offenders


# Ano de calendario. O material nao traz datas de calendario, so janelas em dias
# ("35 dias", "90 dias"). Um modelo que traduz "proximos 90 dias" em
# "13-out-2026 a 11-jan-2027" esta inventando: ele nao sabe que dia e hoje.
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def check_years(answer: str, source: str) -> list[str]:
    """Anos citados na resposta que nao aparecem no material."""
    allowed = {match.group(0) for match in _YEAR.finditer(source)}
    return [
        match.group(0)
        for match in _YEAR.finditer(answer)
        if match.group(0) not in allowed
    ]
