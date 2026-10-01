"""Búsqueda en haz sobre el motor de síntesis, con retroceso y parada."""

from __future__ import annotations

from dataclasses import dataclass

from jevsynth.catalog.model import Catalog
from jevsynth.chooser.base import Chooser, StateText, format_state
from jevsynth.emit.ir import HoleStmt, Program
from jevsynth.literals.extract import extract_literals
from jevsynth.literals.model import LiteralValue
from jevsynth.scope.typesys import TypeSystem
from jevsynth.synth.choice import Asker, Stats, logp
from jevsynth.synth.engine import (
    Choice,
    Engine,
    SearchState,
    StmtTask,
    SynthConfig,
    SynthTask,
    Task,
    is_decision,
)

DONE_HOLE = "¿el programa ya resuelve la tarea por completo?"


@dataclass
class SynthResult:
    code: str | None
    program: Program | None
    score: float
    stop_reason: str  # "solved" | "no_solution" | "budget"
    stats: Stats
    decisions: tuple[str, ...]
    literals: list[LiteralValue]


class Searcher:
    def __init__(self, engine: Engine, asker: Asker, task: SynthTask, config: SynthConfig) -> None:
        self.eng = engine
        self.asker = asker
        self.task = task
        self.config = config

    def state_text(self, st: SearchState, t: Task) -> StateText:
        return format_state(self.task.prompt, self.eng.hole_text(t), self.eng.summary(st, t), st.decisions)

    @staticmethod
    def _finish(st: SearchState, t: StmtTask) -> SearchState:
        if t.block and isinstance(t.block[-1], HoleStmt):
            t.block.pop()
        st.agenda.pop(0)
        st.agenda.clear()
        st.done = True
        return st

    def expand(self, st: SearchState) -> list[SearchState]:
        """Avanza `st` hasta la siguiente decisión real y devuelve sus hijos (o [] si muere)."""
        work = st.clone()
        while True:
            if not work.agenda:
                work.done = True
                return [work]
            t = work.agenda[0]
            if not is_decision(t):
                work.agenda.pop(0)
                if not self.eng.run_auto(work, t):
                    return []
                continue
            if (
                isinstance(t, StmtTask)
                and t.where == "top"
                and self.task.returns is None
                and len(t.block) > 1
            ):
                if work.steps >= self.task.max_steps:
                    return [self._finish(work, t)]
                done_state = format_state(
                    self.task.prompt, DONE_HOLE, self.eng.summary(work, t), work.decisions
                )
                p = self.asker.is_done(done_state)
                if p >= self.config.done_threshold:
                    work.score += logp(p)
                    return [self._finish(work, t)]
                work.score += logp(1 - p)
            opts = self.eng.options(work, t)
            if not opts:
                return []
            if len(opts) == 1:
                work.agenda.pop(0)
                if not self.eng.apply(work, t, opts[0]):
                    return []
                continue
            by_id: dict[str, Choice] = {c.option.id: c for c in opts}
            if len(by_id) != len(opts):
                raise ValueError(f"opciones con id repetido en {self.eng.hole_text(t)!r}")
            state = self.state_text(work, t)
            n = max(self.config.width, self.config.branch)
            ranked = self.asker.rank(state, self.eng.hole_text(t), [c.option for c in opts], n)
            kids: list[SearchState] = []
            for opt, p in ranked[:n]:
                child = work.clone()
                ct = child.agenda.pop(0)
                child.score += logp(p)
                if self.eng.apply(child, ct, by_id[opt.id]):
                    kids.append(child)
            return kids

    def run(self) -> tuple[SearchState | None, str]:
        stats = self.asker.stats
        w = self.config.width
        beam = [self.eng.initial()]
        completed: list[SearchState] = []
        discarded: list[SearchState] = []
        while stats.expansions < self.config.max_expansions:
            if not beam:
                if completed or not discarded:
                    break
                discarded.sort(key=lambda s: -s.score)
                beam, discarded = discarded[:w], discarded[w:]
                stats.backtracks += 1
            children: list[SearchState] = []
            for st in beam:
                stats.expansions += 1
                for k in self.expand(st):
                    (completed if k.done else children).append(k)
            children.sort(key=lambda s: -s.score)
            beam, rest = children[:w], children[w:]
            discarded.extend(rest)
            if completed:
                best = max(s.score for s in completed)
                if not beam or best >= beam[0].score:
                    break
        if not completed:
            return None, "budget" if stats.expansions >= self.config.max_expansions else "no_solution"
        return max(completed, key=lambda s: s.score), "solved"


_TS_CACHE: dict[int, tuple[Catalog, TypeSystem]] = {}


def type_system(catalog: Catalog) -> TypeSystem:
    """TypeSystem compartido por catálogo (sus cachés sirven entre síntesis)."""
    hit = _TS_CACHE.get(id(catalog))
    if hit is None or hit[0] is not catalog:
        hit = (catalog, TypeSystem(catalog.classes))
        _TS_CACHE[id(catalog)] = hit
    return hit[1]


def synthesize(
    task: SynthTask,
    catalog: Catalog,
    chooser: Chooser,
    config: SynthConfig | None = None,
    ts: TypeSystem | None = None,
) -> SynthResult:
    config = config or SynthConfig()
    ts = ts or type_system(catalog)
    literals = extract_literals(task.prompt)
    eng = Engine(task, catalog, ts, literals, config)
    asker = Asker(chooser, eng.group_of, config.max_options)
    best, reason = Searcher(eng, asker, task, config).run()
    if best is None:
        return SynthResult(None, None, float("-inf"), reason, asker.stats, (), literals)
    return SynthResult(
        eng.finalize(best), best.program, best.score, reason, asker.stats, best.decisions, literals
    )
