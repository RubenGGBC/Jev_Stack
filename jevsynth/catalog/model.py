"""Modelo de datos del catálogo de componentes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TypeRef:
    """Referencia a un tipo por su nombre normalizado, p. ej. "str" o "list[int]".

    En la fase 0 el casado de tipos es por igualdad; la fase 2 añade subtipos y uniones.
    """

    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Param:
    name: str
    type: TypeRef
    has_default: bool = False


@dataclass(frozen=True)
class Component:
    qualname: str
    params: tuple[Param, ...]
    returns: TypeRef
    summary: str  # una frase, saneada

    @property
    def required_params(self) -> tuple[Param, ...]:
        return tuple(p for p in self.params if not p.has_default)

    def signature(self) -> str:
        args = ", ".join(f"{p.name}: {p.type}" for p in self.params)
        return f"{self.qualname}({args}) -> {self.returns}"
