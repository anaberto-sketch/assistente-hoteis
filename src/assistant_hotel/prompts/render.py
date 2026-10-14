"""Montagem do prompt: instrucoes + dossie de limiares + dicionario + fact sheet.

Nada aqui chama a rede nem o LLM. E concatenacao de texto deterministico, para
poder ser testada sozinha.

O system prompt inteiro e estavel dentro de um mesmo hotel (instrucoes, limiares,
dicionario e fact sheet nao mudam entre turnos). Isso o torna bom candidato a
cache de prompt numa proxima iteracao.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..state import Diagnosis, FieldDoc, Lang, Lever, Threshold

PROMPTS_DIR = Path(__file__).resolve().parent

# Campos que identificam o hotel no fact sheet. Sempre expostos: sem eles o
# modelo nao sabe de quem esta falando.
IDENTITY_FIELDS: tuple[str, ...] = (
    "hotel_id",
    "hotel_name",
    "country_code",
    "destiny_code",
    "destiny",
    "star_rating",
)

NULL_TEXT: dict[str, str] = {
    "pt": "NULL (sem dado)",
    "es": "NULL (sin dato)",
}

BOOL_TEXT: dict[str, tuple[str, str]] = {
    "pt": ("sim", "não"),
    "es": ("sí", "no"),
}

NO_LEVERS: dict[str, str] = {
    "pt": "Nenhuma alavanca foi acionada: as regras do pipeline passaram.",
    "es": "No se accionó ninguna palanca: las reglas del pipeline pasaron.",
}


@lru_cache(maxsize=4)
def load_instructions(lang: Lang) -> str:
    return (PROMPTS_DIR / f"system_{lang}.md").read_text(encoding="utf-8").strip()


def format_value(value: Any, lang: Lang) -> str:
    """Formata um valor para leitura humana. Virgula decimal, como no material."""
    if value is None:
        return NULL_TEXT[lang]
    if isinstance(value, bool):
        sim, nao = BOOL_TEXT[lang]
        return sim if value else nao
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e9:
            return str(int(value))
        return f"{value:.2f}".replace(".", ",")
    return str(value)


def exposed_fields(
    row: Mapping[str, Any],
    fields: Sequence[FieldDoc],
    diagnosis: Diagnosis | None,
) -> dict[str, Any]:
    """Recorte da linha que vai para o prompt.

    Guardrail 1: o modelo so ve os campos que o retrieval selecionou mais os que
    sustentam alguma alavanca. Menos numero disponivel = menos numero a inventar.
    """
    names: list[str] = list(IDENTITY_FIELDS)
    names += [doc["field"] for doc in fields]
    if diagnosis:
        for lever in diagnosis["levers"]:
            names += list(lever["field_refs"])
            names += list(lever["evidence"].keys())

    seen: dict[str, Any] = {}
    for name in names:
        if name in seen or name not in row:
            continue
        seen[name] = row[name]
    return seen


def render_thresholds(thresholds: Iterable[Threshold], lang: Lang) -> str:
    lines = ["# LIMIARES DO PIPELINE DE RECOMENDAÇÕES", ""]
    for item in thresholds:
        meaning = item["meaning_es"] if lang == "es" else item["meaning_pt"]
        lines.append(f"- `{item['id']}` ({item['block']}): {item['rule']}")
        lines.append(f"  {meaning}")
    return "\n".join(lines)


def render_fields(fields: Sequence[FieldDoc], lang: Lang) -> str:
    if not fields:
        return "# DICIONÁRIO DE CAMPOS\n\n(nenhum campo selecionado)"

    lines = ["# DICIONÁRIO DOS CAMPOS RELEVANTES PARA ESTA PERGUNTA", ""]
    current_block = None
    for doc in fields:
        if doc["block"] != current_block:
            current_block = doc["block"]
            lines.append(f"## {current_block}")
        lines.append(f"### `{doc['field']}`")
        lines.append(f"Definição: {doc['definition']}")
        lines.append(f"Como ler: {doc['how_to_read']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_fact_sheet(
    row: Mapping[str, Any],
    diagnosis: Diagnosis,
    exposed: Mapping[str, Any],
    lang: Lang,
) -> str:
    lines = ["# FACT SHEET", ""]

    lines.append("## Identificação")
    for name in IDENTITY_FIELDS:
        if name in row:
            lines.append(f"- {name}: {format_value(row[name], lang)}")
    lines.append("")

    lines.append(f"## Confiança do diagnóstico: {diagnosis['confidence']}")
    lines.append("")

    lines.append("## Alavancas acionadas")
    if not diagnosis["levers"]:
        lines.append(NO_LEVERS[lang])
    else:
        for lever in diagnosis["levers"]:
            lines.extend(_render_lever(lever, lang))
    lines.append("")

    if diagnosis["ok_checks"]:
        lines.append("## Regras avaliadas que NÃO acionaram")
        for check in diagnosis["ok_checks"]:
            lines.append(f"- {check}")
        lines.append("")

    if diagnosis["data_quality"]:
        lines.append("## Avisos de qualidade do dado (não são alavancas)")
        for note in diagnosis["data_quality"]:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("## Valores disponíveis")
    for name, value in exposed.items():
        lines.append(f"- {name}: {format_value(value, lang)}")

    return "\n".join(lines).rstrip()


def _render_lever(lever: Lever, lang: Lang) -> list[str]:
    message = lever["message_es"] if lang == "es" else lever["message_pt"]
    lines = [
        f"### {lever['id']} — severidade {lever['severity']} ({lever['block']})",
        f"Regra: {lever['rule']}",
        f"Leitura: {message}",
    ]
    if lever["evidence"]:
        pairs = ", ".join(
            f"{name}={format_value(value, lang)}"
            for name, value in lever["evidence"].items()
        )
        lines.append(f"Evidência: {pairs}")
    for caveat in lever["caveats"]:
        lines.append(f"Ressalva: {caveat}")
    lines.append("")
    return lines


def build_system_prompt(
    lang: Lang,
    fact_sheet: str,
    fields: Sequence[FieldDoc],
    thresholds: Iterable[Threshold],
) -> str:
    return "\n\n".join(
        (
            load_instructions(lang),
            render_thresholds(thresholds, lang),
            render_fields(fields, lang),
            fact_sheet,
        )
    )


def build_context(
    lang: Lang,
    row: Mapping[str, Any],
    diagnosis: Diagnosis,
    fields: Sequence[FieldDoc],
    thresholds: Iterable[Threshold],
) -> tuple[str, str, dict[str, Any]]:
    """Devolve (system_prompt, fact_sheet, campos_expostos)."""
    exposed = exposed_fields(row, fields, diagnosis)
    fact_sheet = render_fact_sheet(row, diagnosis, exposed, lang)
    system = build_system_prompt(lang, fact_sheet, fields, thresholds)
    return system, fact_sheet, exposed


def dictionary_entry_names() -> set[str]:
    """Utilidade para testes: os campos que o dicionario conhece."""
    from ..domain.fields import field_dictionary

    return {entry.field for entry in field_dictionary()}


__all__ = [
    "build_context",
    "build_system_prompt",
    "exposed_fields",
    "format_value",
    "load_instructions",
    "render_fact_sheet",
    "render_fields",
    "render_thresholds",
]
