"""Chooser oráculo: conoce la secuencia de decisiones de la solución.

Lee el camino de decisiones de la rama (`StateText.decisions`, que el chooser real
ignora) y casa la secuencia objetivo como subsecuencia: la siguiente decisión objetivo
pendiente recibe casi toda la probabilidad. Si esa decisión no está entre las opciones
(el objetivo omite decisiones obvias), reparte uniformemente.
"""

from __future__ import annotations

import hashlib
import random
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


class NoisyOracleChooser(OracleChooser):
    """Oráculo imperfecto: simula un chooser que acierta con probabilidad `accuracy`.

    Con probabilidad `accuracy` la opción correcta recibe la mayor probabilidad; si no,
    otra opción al azar queda arriba y la correcta segunda. Las probabilidades no son
    extremas (0,4-0,8 arriba), así que la búsqueda tiene margen para recuperarse. Es
    determinista por (estado, opciones, semilla), como un modelo con caché.
    """

    def __init__(self, target: Sequence[str], accuracy: float = 0.8, seed: int = 0) -> None:
        super().__init__(target)
        if not 0.0 <= accuracy <= 1.0:
            raise ValueError("accuracy debe estar en [0, 1]")
        self.accuracy = accuracy
        self.seed = seed

    def _rng(self, state: str, options: Sequence[Option]) -> random.Random:
        key = f"{self.seed}|{state}|{'|'.join(o.id for o in options)}"
        return random.Random(hashlib.sha256(key.encode()).digest())

    def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
        i = self._matched(getattr(state, "decisions", ()))
        expected = self.target[i] if i < len(self.target) else None
        hits = [expected in (o.id, *o.members) for o in options]
        rng = self._rng(state, options)
        if expected is None or not any(hits) or len(options) < 2:
            return rank(options, [rng.random() for _ in options])
        good = hits.index(True)
        top = rng.uniform(0.4, 0.8)
        scores = [rng.random() * (1 - top) / len(options) for _ in options]
        if rng.random() < self.accuracy:
            scores[good] = top
        else:
            wrong = rng.choice([k for k in range(len(options)) if k != good])
            scores[wrong] = top
            scores[good] = (1 - top) * 0.6
        return rank(options, scores)

    def is_done(self, state: str) -> float:
        done = self._matched(getattr(state, "decisions", ())) >= len(self.target)
        rng = random.Random(hashlib.sha256(f"{self.seed}|done|{state}".encode()).digest())
        right = rng.random() < self.accuracy
        return (0.9 if done else 0.1) if right else (0.1 if done else 0.9)
