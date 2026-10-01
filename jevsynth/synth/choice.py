"""Consultas al chooser: elección jerárquica, contabilidad y registro de dudas.

Si un hueco tiene más opciones que `max_options`, primero se elige un grupo (módulo,
clase, variables, literales, control) y luego dentro de él. La probabilidad de una
opción es P(grupo) · P(opción | grupo). Solo se exploran los `width` mejores grupos.
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from jevsynth.chooser.base import Chooser, Option, StateText

GROUP_HOLE_SUFFIX = " — primero elige el grupo donde está la opción"


@dataclass
class QueryLog:
    hole: str
    n_options: int
    top: list[tuple[str, float]]
    seconds: float

    @property
    def margin(self) -> float:
        if len(self.top) < 2:
            return 1.0
        return self.top[0][1] - self.top[1][1]


@dataclass
class Stats:
    queries: int = 0  # llamadas a choose
    done_queries: int = 0  # llamadas a is_done
    seconds: float = 0.0
    backtracks: int = 0
    expansions: int = 0
    log: list[QueryLog] = field(default_factory=list)

    def low_margin(self, threshold: float = 0.1) -> list[QueryLog]:
        """Decisiones en las que el chooser dudó (top1 - top2 < umbral)."""
        return [q for q in self.log if q.n_options > 1 and q.margin < threshold]


def _short(o: Option) -> str:
    if o.kind == "component":
        return o.id.split("@")[0].split("+")[0].rsplit(".", 1)[-1]
    return o.label.split(":")[0]


def _group_key(o: Option, group_of: dict[str, str]) -> str:
    if o.kind == "component":
        return group_of.get(o.id, "otros")
    return {"symbol": "variables", "literal": "literales", "control": "control"}.get(o.kind, "otros")


def build_groups(options: Sequence[Option], group_of: dict[str, str], max_options: int) -> list[Option]:
    """Agrupa opciones; los grupos demasiado grandes se parten en trozos."""
    order: list[str] = []
    members: dict[str, list[Option]] = {}
    for o in options:
        k = _group_key(o, group_of)
        if k not in members:
            order.append(k)
            members[k] = []
        members[k].append(o)
    groups: list[Option] = []
    for k in order:
        ms = members[k]
        chunks = [ms[i : i + max_options] for i in range(0, len(ms), max_options)]
        for i, chunk in enumerate(chunks):
            name = k if len(chunks) == 1 else f"{k} ({i + 1}/{len(chunks)})"
            names: list[str] = []
            for o in chunk:
                s = _short(o)
                if s not in names:
                    names.append(s)
            shown = ", ".join(names[:8]) + (", …" if len(names) > 8 else "")
            groups.append(
                Option(
                    id=f"group:{name}",
                    label=f"{name}: {shown}",
                    kind="group",
                    members=tuple(o.id for o in chunk),
                )
            )
    return groups


class Asker:
    """Envuelve al chooser: cuenta consultas, mide latencia y hace la elección jerárquica."""

    def __init__(self, chooser: Chooser, group_of: dict[str, str], max_options: int = 30) -> None:
        self.chooser = chooser
        self.group_of = group_of
        self.max_options = max_options
        self.stats = Stats()

    def _query(self, state: StateText, options: list[Option], hole: str) -> list[tuple[Option, float]]:
        t0 = time.perf_counter()
        ranked = self.chooser.choose(state, options)
        dt = time.perf_counter() - t0
        self.stats.queries += 1
        self.stats.seconds += dt
        self.stats.log.append(QueryLog(hole, len(options), [(o.id, p) for o, p in ranked[:3]], dt))
        valid = {o.id for o in options}
        if {o.id for o, _ in ranked} - valid:
            raise ValueError("el chooser devolvió opciones que no estaban entre las candidatas")
        return ranked

    def rank(
        self, state: StateText, hole: str, options: list[Option], width: int
    ) -> list[tuple[Option, float]]:
        if len(options) <= 1:
            return [(o, 1.0) for o in options]  # decisión forzada: sin consulta
        if len(options) <= self.max_options:
            return self._query(state, options, hole)
        groups = build_groups(options, self.group_of, self.max_options)
        if len(groups) == 1:
            return self._query(state, options[: self.max_options], hole)
        by_id = {o.id: o for o in options}
        group_state = StateText(str(state).replace(hole, hole + GROUP_HOLE_SUFFIX, 1), state.decisions)
        ranked_groups = self.rank(group_state, hole + GROUP_HOLE_SUFFIX, groups, width)
        out: list[tuple[Option, float]] = []
        for g, pg in ranked_groups[:width]:
            inner = [by_id[i] for i in g.members]
            for o, p in self.rank(state, hole, inner, width):
                out.append((o, pg * p))
        out.sort(key=lambda x: -x[1])
        return out

    def is_done(self, state: StateText) -> float:
        t0 = time.perf_counter()
        p = self.chooser.is_done(state)
        self.stats.done_queries += 1
        self.stats.seconds += time.perf_counter() - t0
        return min(max(p, 0.0), 1.0)


def logp(p: float) -> float:
    return math.log(max(p, 1e-12))
