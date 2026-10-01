"""Saneado de descripciones del catálogo.

El texto de la documentación se trata como no confiable: se reduce a una frase corta,
sin saltos de línea ni markdown, y se descarta si contiene patrones tipo instrucción.
"""

from __future__ import annotations

import re

MAX_SUMMARY = 120
MAX_DOC = 400

# Patrones que podrían colarse como instrucciones en el estado que ve el chooser.
INJECTION = re.compile(r"(ignore|disregard|system|assistant\s*:|user\s*:|instruction|prompt)", re.IGNORECASE)
_MARKDOWN = re.compile(r"[`*_#>|\[\]{}]")
_SIGNATURE_LINE = re.compile(r"^[\w.]+\(.*\)(\s*->.*)?$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def _paragraphs(doc: str) -> list[str]:
    lines = doc.strip().splitlines()
    # Los docstrings de C empiezan a veces con la firma ("str(object='') -> str").
    while lines and (_SIGNATURE_LINE.match(lines[0].strip()) or lines[0].strip() == "--"):
        lines.pop(0)
    text = "\n".join(lines).strip()
    # "zip(*iterables, strict=False) --> Yield tuples..." : quitar la firma inicial.
    text = re.sub(r"^[\w.]+\([^)]*\)\s*-+>?\s*", "", text)
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def clean(text: str) -> str:
    text = _MARKDOWN.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def is_safe(text: str) -> bool:
    return INJECTION.search(text) is None


def summarize(doc: str | None, fallback: str) -> str:
    """Primera frase del docstring, ≤120 caracteres, sin saltos ni markdown."""
    paras = _paragraphs(doc or "")
    if not paras:
        return fallback
    first = clean(paras[0])
    sentence = _SENTENCE_END.split(first, maxsplit=1)[0]
    summary = truncate(sentence, MAX_SUMMARY)
    if not summary or not is_safe(summary):
        return fallback
    return summary


def long_doc(doc: str | None, summary: str) -> str:
    """Docstring más completo (primer párrafo largo) para la ablación de descripciones."""
    paras = _paragraphs(doc or "")
    if not paras:
        return summary
    text = truncate(clean(" ".join(paras[:2])), MAX_DOC)
    return text if is_safe(text) else summary
