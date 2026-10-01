"""Entorno de variables con tipo."""

from __future__ import annotations

from dataclasses import dataclass, field

from jevsynth.catalog.model import TypeRef


@dataclass(frozen=True)
class Variable:
    name: str
    type: TypeRef


@dataclass
class Scope:
    """Variables visibles en orden de definición (la última es la más reciente)."""

    variables: list[Variable] = field(default_factory=list)

    def add(self, var: Variable) -> None:
        if var.name in self.names():
            raise ValueError(f"la variable {var.name!r} ya existe")
        self.variables.append(var)

    def names(self) -> set[str]:
        return {v.name for v in self.variables}

    def get(self, name: str) -> Variable | None:
        for v in self.variables:
            if v.name == name:
                return v
        return None

    def of_type(self, t: TypeRef) -> list[Variable]:
        """Variables de tipo exactamente `t`, de la más reciente a la más antigua."""
        return [v for v in reversed(self.variables) if v.type == t]

    def copy(self) -> Scope:
        return Scope(list(self.variables))
