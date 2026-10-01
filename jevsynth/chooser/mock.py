"""MockChooser: elige por solapamiento de palabras entre la tarea y la etiqueta de la opción."""

from __future__ import annotations

import re

from jevsynth.chooser.base import Option, rank

_WORD = re.compile(r"[a-záéíóúñü0-9]+")

# Palabras sin contenido que no deben puntuar como solapamiento.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "of", "the", "to", "in", "on", "for", "with", "from", "into",
        "el", "la", "los", "las", "de", "del", "y", "en", "un", "una", "con", "por", "para",
    }
)  # fmt: skip

from jevsynth.chooser.base import TASK_PREFIX  # noqa: E402


def words(text: str) -> set[str]:
    """Palabras normalizadas: minúsculas, sin stopwords, separando snake_case y puntos."""
    return {w for w in _WORD.findall(text.lower().replace("_", " ")) if w not in _STOPWORDS}


def task_of(state: str) -> str:
    """Extrae la línea de tarea del estado; si no la hay, usa el estado entero."""
    for line in state.splitlines():
        if line.lower().startswith(TASK_PREFIX):
            return line[len(TASK_PREFIX) :]
    return state


class MockChooser:
    """Chooser determinista sin red, útil como línea base y para tests.

    Puntúa cada opción con `1 + |palabras(tarea) ∩ palabras(etiqueta)|` (el +1 suaviza
    para que ninguna opción tenga probabilidad 0). `is_done` devuelve un valor fijo.
    """

    def __init__(self, done_prob: float = 0.0) -> None:
        if not 0.0 <= done_prob <= 1.0:
            raise ValueError("done_prob debe estar en [0, 1]")
        self.done_prob = done_prob

    def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
        task = words(task_of(state))
        scores = [1.0 + len(task & words(o.label)) for o in options]
        return rank(options, scores)

    def is_done(self, state: str) -> float:
        return self.done_prob
