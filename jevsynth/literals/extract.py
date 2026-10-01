"""Extracción determinista de literales desde la petición en lenguaje natural.

Fuentes, por orden de prioridad:
1. Texto entre comillas ("x", 'x', «x», “x”, `x`).
2. Nombres de fichero (palabra.ext).
3. Identificadores de columna: tras palabras como "columna"/"campo"/"column", tras
   un agregado ("media de age", "sum of price") o con forma snake_case/dígitos.
4. Números enteros y decimales.
"""

from __future__ import annotations

import re

from jevsynth.literals.model import LiteralSource, LiteralValue

_QUOTED = re.compile(r"\"([^\"\n]+)\"|'([^'\n]+)'|«([^»\n]+)»|“([^”\n]+)”|`([^`\n]+)`")
_FILENAME = re.compile(r"(?<![\w/.-])((?:[\w-]+/)*[\w-]+\.[A-Za-z][A-Za-z0-9]{0,4})(?![\w])")
_NUMBER = re.compile(r"(?<![\w.])(-?\d+(?:[.,]\d+)?)(?![\w]|[.,]\d)")
_IDENT = r"([A-Za-z_][A-Za-z0-9_]*)(?!\w)"  # (?!\w): no cortar "números" en "n"

_STOP = frozenset(
    {
        "la", "el", "los", "las", "un", "una", "de", "del", "cada", "todas", "todos", "su", "sus",
        "the", "a", "an", "of", "each", "every", "all", "its", "their", "this", "that", "columna",
        "column", "campo", "field", "valores", "values", "datos", "data", "fichero", "archivo",
        "file", "y", "and", "en", "in", "por", "by", "con", "with",
        # sustantivos genéricos: no son nombres de columna
        "numbers", "number", "words", "word", "lines", "line", "rows", "row", "items", "item",
        "elements", "text", "list", "lista", "texto", "palabras", "lineas", "filas", "elementos",
    }
)  # fmt: skip
_CUE = r"(?:columna|campo|clave|atributo|column|field|key|attribute)"
_AGG = (
    r"(?:media|promedio|suma|total|máximo|maximo|mínimo|minimo|mediana|moda|desviación|desviacion"
    r"|varianza|mean|average|sum|max|maximum|min|minimum|median|mode|stdev|variance)"
)
_COLUMN_PATTERNS = [
    # "la columna age", "el campo precio", "column price"
    re.compile(rf"\b{_CUE}\s+(?:de\s+|of\s+)?{_IDENT}", re.IGNORECASE),
    # "la media de age", "the sum of the price"
    re.compile(
        rf"\b{_AGG}\s+(?:de\s+la\s+|de\s+los\s+|de\s+las\s+|del\s+|de\s+|of\s+the\s+|of\s+)"
        rf"(?:columna\s+|campo\s+|column\s+)?{_IDENT}",
        re.IGNORECASE,
    ),
    # "the price column"
    re.compile(rf"\b(?:the\s+)?{_IDENT}\s+(?:column|field)\b", re.IGNORECASE),
]
_SNAKE = re.compile(r"(?<![\w.])([a-z]+(?:_[a-z0-9]+)+|[a-z]+\d+)(?![\w.])")


def extract_literals(request: str) -> list[LiteralValue]:
    """Literales de la petición, en orden de aparición y sin duplicados."""
    found: list[tuple[int, LiteralValue]] = []
    taken: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        return all(end <= s or start >= e for s, e in taken)

    def add(start: int, end: int, value: str | int | float, source: LiteralSource) -> None:
        if free(start, end):
            taken.append((start, end))
            found.append((start, LiteralValue(value, source)))

    for m in _QUOTED.finditer(request):
        text = next(g for g in m.groups() if g is not None)
        add(m.start(), m.end(), text, "quoted")
    for m in _FILENAME.finditer(request):
        if not re.fullmatch(r"[\d.]+", m.group(1)):
            add(m.start(1), m.end(1), m.group(1), "filename")
    for pat in _COLUMN_PATTERNS:
        for m in pat.finditer(request):
            word = m.group(1)
            if word.lower() not in _STOP:
                add(m.start(1), m.end(1), word, "identifier")
    for m in _SNAKE.finditer(request):
        add(m.start(1), m.end(1), m.group(1), "identifier")
    for m in _NUMBER.finditer(request):
        raw = m.group(1).replace(",", ".")
        num: int | float = float(raw) if "." in raw else int(raw)
        add(m.start(1), m.end(1), num, "number")

    out: list[LiteralValue] = []
    for _, lit in sorted(found, key=lambda x: x[0]):
        if all(lit.value != o.value or type(lit.value) is not type(o.value) for o in out):
            out.append(lit)
    return out
