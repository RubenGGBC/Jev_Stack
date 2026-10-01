"""RandomChooser: probabilidades aleatorias con semilla, como línea base reproducible."""

from __future__ import annotations

import random

from jevsynth.chooser.base import Option, rank


class RandomChooser:
    def __init__(self, seed: int = 0, done_prob: float | None = None) -> None:
        """`done_prob=None` hace que `is_done` también sea aleatorio."""
        self._rng = random.Random(seed)
        self.done_prob = done_prob

    def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
        return rank(options, [self._rng.random() for _ in options])

    def is_done(self, state: str) -> float:
        return self._rng.random() if self.done_prob is None else self.done_prob
