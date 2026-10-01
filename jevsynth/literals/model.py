"""Literales extraídos de la petición."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from jevsynth.catalog.model import TypeRef, literal

LiteralSource = Literal["quoted", "filename", "number", "identifier"]


@dataclass(frozen=True)
class LiteralValue:
    value: str | int | float
    source: LiteralSource

    @property
    def type(self) -> TypeRef:
        return literal(self.value)

    @property
    def code(self) -> str:
        return repr(self.value)
