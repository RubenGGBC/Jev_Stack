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
    queries: int = 0  # preguntas de elección
    done_queries: int = 0  # preguntas de parada
    requests: int = 0  # peticiones al chooser (un lote cuenta como una)
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


Query = tuple[StateText, str, list[Option]]  # (estado, hueco, opciones)


class Asker:
    """Envuelve al chooser: cuenta consultas, mide latencia, agrupa en lotes y hace la
    elección jerárquica.

    Si el chooser tiene `batch(state, [(hueco, opciones)...], done)`, las preguntas que
    comparten estado van en una sola petición: las elecciones dentro de los mejores
    grupos y, en scripts, la pregunta de parada junto con la siguiente instrucción.
    """

    def __init__(self, chooser: Chooser, group_of: dict[str, str], max_options: int = 30) -> None:
        self.chooser = chooser
        self.group_of = group_of
        self.max_options = max_options
        self.stats = Stats()

    def _ask(
        self, queries: list[Query], done_state: StateText | None
    ) -> tuple[list[list[tuple[Option, float]]], float | None]:
        t0 = time.perf_counter()
        batch = getattr(self.chooser, "batch", None)
        p_done: float | None = None
        if callable(batch):
            state = queries[0][0] if queries else done_state
            assert state is not None
            ranked_lists, p_done = batch(state, [(h, o) for _, h, o in queries], done_state is not None)
            self.stats.requests += 1
        else:
            ranked_lists = [self.chooser.choose(st, opts) for st, _, opts in queries]
            if done_state is not None:
                p_done = self.chooser.is_done(done_state)
            self.stats.requests += len(queries) + (done_state is not None)
        dt = time.perf_counter() - t0
        self.stats.seconds += dt
        self.stats.queries += len(queries)
        self.stats.done_queries += done_state is not None
        for (_, hole, opts), ranked in zip(queries, ranked_lists, strict=True):
            if {o.id for o, _ in ranked} - {o.id for o in opts}:
                raise ValueError("el chooser devolvió opciones que no estaban entre las candidatas")
            self.stats.log.append(
                QueryLog(hole, len(opts), [(o.id, p) for o, p in ranked[:3]], dt / max(len(queries), 1))
            )
        if p_done is not None:
            p_done = min(max(p_done, 0.0), 1.0)
        return ranked_lists, p_done

    def rank(
        self,
        state: StateText,
        hole: str,
        options: list[Option],
        width: int,
        done_state: StateText | None = None,
    ) -> tuple[list[tuple[Option, float]], float | None]:
        """Opciones ordenadas con su probabilidad (y P(terminado) si se pide `done_state`)."""
        if len(options) <= 1:
            p = self._ask([], done_state)[1] if done_state is not None else None
            return [(o, 1.0) for o in options], p  # decisión forzada: sin consulta
        if len(options) <= self.max_options:
            lists, p = self._ask([(state, hole, options)], done_state)
            return lists[0], p
        groups = build_groups(options, self.group_of, self.max_options)
        by_id = {o.id: o for o in options}
        ghole = hole + GROUP_HOLE_SUFFIX
        gstate = StateText(str(state).replace(hole, ghole, 1), state.decisions)
        if len(groups) > self.max_options:
            ranked_groups, p = self.rank(gstate, ghole, groups, width, done_state)
        else:
            lists, p = self._ask([(gstate, ghole, groups)], done_state)
            ranked_groups = lists[0]
        top = ranked_groups[:width]
        inner_queries: list[Query] = []
        for g, _ in top:
            if len(g.members) > 1:
                inner_queries.append((state, hole, [by_id[i] for i in g.members]))
        inner_lists = self._ask(inner_queries, None)[0] if inner_queries else []
        it = iter(inner_lists)
        out: list[tuple[Option, float]] = []
        for g, pg in top:
            ranked = next(it) if len(g.members) > 1 else [(by_id[g.members[0]], 1.0)]
            out.extend((o, pg * p_in) for o, p_in in ranked)
        out.sort(key=lambda x: -x[1])
        return out, p

    def is_done(self, state: StateText) -> float:
        p = self._ask([], state)[1]
        assert p is not None
        return p


def logp(p: float) -> float:
    return math.log(max(p, 1e-12))
