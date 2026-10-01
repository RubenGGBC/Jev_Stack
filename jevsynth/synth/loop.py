"""Bucle de síntesis mínimo (fase 0): voraz, sin retroceso.

En cada paso el script calcula los componentes aplicables con el scope actual, el chooser
elige uno y el script lo inserta ligando el resultado a una variable nueva. Los argumentos
se rellenan de forma determinista con la variable compatible más reciente; los nombres
de variable los genera el script, nunca el chooser.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from jevsynth.catalog.model import Component, TypeRef
from jevsynth.chooser.base import Chooser, Option
from jevsynth.scope.model import Scope, Variable

# Nombre base de variable según el tipo; el resto usa "result".
_BASE_NAMES = {"str": "text", "int": "n", "list[str]": "items"}


@dataclass(frozen=True)
class Step:
    component: Component
    args: tuple[str, ...]
    out: str


@dataclass
class SynthResult:
    steps: list[Step]
    scope: Scope
    stop_reason: str  # "done" | "no_candidates" | "max_steps"
    trace: list[list[tuple[Option, float]]] = field(default_factory=list)

    def summary(self) -> str:
        return program_summary(self.steps)


def program_summary(steps: Sequence[Step]) -> str:
    if not steps:
        return "(vacío)"
    return "; ".join(f"{s.out} = {s.component.qualname}({', '.join(s.args)})" for s in steps)


def build_state(task: str, hole: str, steps: Sequence[Step]) -> str:
    """Estado mínimo para el chooser: tarea + hueco actual + resumen del programa parcial."""
    return f"tarea: {task}\nhueco: {hole}\nprograma: {program_summary(steps)}"


def component_option(c: Component) -> Option:
    return Option(id=c.qualname, label=f"{c.qualname}: {c.summary}", kind="component")


def bind_args(c: Component, scope: Scope) -> tuple[str, ...] | None:
    """Rellena los parámetros obligatorios con variables del scope, o None si no se puede."""
    args: list[str] = []
    for p in c.required_params:
        matches = scope.of_type(p.type)
        if not matches:
            return None
        args.append(matches[0].name)
    return tuple(args)


def fresh_name(t: TypeRef, scope: Scope) -> str:
    base = _BASE_NAMES.get(t.name, "result")
    taken = scope.names()
    if base not in taken:
        return base
    i = 2
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"


def synthesize(
    task: str,
    catalog: Sequence[Component],
    chooser: Chooser,
    scope: Scope,
    *,
    max_steps: int = 5,
    done_threshold: float = 0.5,
) -> SynthResult:
    scope = scope.copy()
    steps: list[Step] = []
    trace: list[list[tuple[Option, float]]] = []
    by_id = {c.qualname: c for c in catalog}

    while len(steps) < max_steps:
        if steps and chooser.is_done(build_state(task, "¿terminado?", steps)) >= done_threshold:
            return SynthResult(steps, scope, "done", trace)

        bound = {c.qualname: a for c in catalog if (a := bind_args(c, scope)) is not None}
        if not bound:
            return SynthResult(steps, scope, "no_candidates", trace)

        options = [component_option(by_id[q]) for q in bound]
        ranked = chooser.choose(build_state(task, "siguiente llamada", steps), options)
        trace.append(ranked)
        if not ranked or ranked[0][0].id not in bound:
            raise ValueError("el chooser devolvió una opción que no estaba entre los candidatos")
        chosen = by_id[ranked[0][0].id]

        out = fresh_name(chosen.returns, scope)
        scope.add(Variable(out, chosen.returns))
        steps.append(Step(chosen, bound[chosen.qualname], out))

    return SynthResult(steps, scope, "max_steps", trace)
