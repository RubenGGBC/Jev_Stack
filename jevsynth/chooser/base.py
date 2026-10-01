"""Interfaz común de los choosers: elegir entre opciones cerradas y estimar si se ha terminado."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

OptionKind = Literal["component", "symbol", "literal", "control"]


@dataclass(frozen=True)
class Option:
    id: str  # estable, p. ej. "csv.DictReader"
    label: str  # texto corto y uniforme que ve el chooser
    kind: OptionKind


class Chooser(Protocol):
    def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
        """Devuelve opciones con probabilidad, ordenadas de mayor a menor."""
        ...

    def is_done(self, state: str) -> float:
        """Probabilidad de que la tarea ya esté resuelta."""
        ...


def rank(options: Sequence[Option], scores: Sequence[float]) -> list[tuple[Option, float]]:
    """Normaliza puntuaciones no negativas a probabilidades y ordena de mayor a menor.

    El orden es estable: a igual probabilidad se respeta el orden de entrada.
    """
    if len(options) != len(scores):
        raise ValueError("options y scores deben tener la misma longitud")
    if not options:
        return []
    if any(s < 0 for s in scores):
        raise ValueError("las puntuaciones no pueden ser negativas")
    total = sum(scores)
    probs = [s / total for s in scores] if total > 0 else [1 / len(options)] * len(options)
    order = sorted(range(len(options)), key=lambda i: -probs[i])
    return [(options[i], probs[i]) for i in order]
