"""Interfaz común de los choosers: elegir entre opciones cerradas y estimar si se ha terminado."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

OptionKind = Literal["component", "symbol", "literal", "control", "group"]


@dataclass(frozen=True)
class Option:
    id: str  # estable, p. ej. "csv.DictReader"
    label: str  # texto corto y uniforme que ve el chooser
    kind: OptionKind
    # Solo para kind="group": ids de las opciones que agrupa. No se envía al chooser.
    members: tuple[str, ...] = ()

    def __deepcopy__(self, memo: dict[int, object]) -> Option:
        return self


class StateText(str):
    """Estado textual para el chooser, con metadatos que el chooser real ignora.

    `decisions`: ids elegidos hasta ahora en esta rama (lo usa el chooser oráculo).
    """

    decisions: tuple[str, ...]

    def __new__(cls, text: str, decisions: tuple[str, ...] = ()) -> StateText:
        obj = super().__new__(cls, text)
        obj.decisions = decisions
        return obj


TASK_PREFIX = "tarea:"
HOLE_PREFIX = "hueco:"
PROGRAM_PREFIX = "programa:"


def format_state(task: str, hole: str, program: str, decisions: tuple[str, ...] = ()) -> StateText:
    """Estado mínimo: tarea + hueco actual + resumen del programa parcial."""
    return StateText(f"{TASK_PREFIX} {task}\n{HOLE_PREFIX} {hole}\n{PROGRAM_PREFIX}\n{program}", decisions)


def parse_state(state: str) -> tuple[str, str, str]:
    """Inverso de `format_state`: (tarea, hueco, programa)."""
    task = hole = ""
    program_lines: list[str] = []
    in_program = False
    for line in state.splitlines():
        if in_program:
            program_lines.append(line)
        elif line.startswith(TASK_PREFIX):
            task = line[len(TASK_PREFIX) :].strip()
        elif line.startswith(HOLE_PREFIX):
            hole = line[len(HOLE_PREFIX) :].strip()
        elif line.startswith(PROGRAM_PREFIX):
            in_program = True
            rest = line[len(PROGRAM_PREFIX) :].strip()
            if rest:
                program_lines.append(rest)
    return task, hole, "\n".join(program_lines)


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
