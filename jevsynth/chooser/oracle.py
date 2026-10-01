"""Chooser oráculo: conoce la secuencia de decisiones de la solución.

Lee el camino de decisiones de la rama (`StateText.decisions`, que el chooser real
ignora) y casa la secuencia objetivo como subsecuencia: la siguiente decisión objetivo
pendiente recibe casi toda la probabilidad. Si esa decisión no está entre las opciones
(el objetivo omite decisiones obvias), reparte uniformemente.
"""

from __future__ import annotations

from collections.abc import Sequence

from jevsynth.chooser.base import Option, rank

_HIT = 0.97


class OracleChooser:
    def __init__(self, target: Sequence[str]) -> None:
        self.target = tuple(target)

    def _matched(self, decisions: Sequence[str]) -> int:
        i = 0
        for d in decisions:
            if i < len(self.target) and d == self.target[i]:
                i += 1
        return i

    def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
        i = self._matched(getattr(state, "decisions", ()))
        expected = self.target[i] if i < len(self.target) else None
        hits = [expected in (o.id, *o.members) for o in options]
        if expected is None or not any(hits):
            return rank(options, [1.0] * len(options))
        miss = (1 - _HIT) / max(len(options) - 1, 1)
        return rank(options, [_HIT if h else miss for h in hits])

    def is_done(self, state: str) -> float:
        done = self._matched(getattr(state, "decisions", ())) >= len(self.target)
        return 0.99 if done else 0.01
