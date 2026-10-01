import ast
import functools
import math

import pytest

from jevsynth.catalog import Catalog, Component, Param, TypeRef, load_stdlib
from jevsynth.catalog.toy import TOY_CATALOG
from jevsynth.chooser import MockChooser, Option, OracleChooser, RandomChooser, parse_state, rank
from jevsynth.eval.runner import run_code
from jevsynth.eval.tasks import EvalTask, load_tasks
from jevsynth.synth import SynthConfig, SynthTask, synthesize

P = TypeRef.parse


@functools.cache
def _cat() -> Catalog:
    return load_stdlib()


def _phase5() -> list[EvalTask]:
    return [t for t in load_tasks() if "fase5" in t.tags]


# -- Criterio de la fase 5 --------------------------------------------------------


@pytest.mark.parametrize("task", _phase5(), ids=lambda t: t.id)
def test_oracle_solves_phase5_tasks(task: EvalTask) -> None:
    assert 3 <= task.max_steps <= 6
    r1 = synthesize(task.synth_task(), _cat(), OracleChooser(task.oracle))
    r2 = synthesize(task.synth_task(), _cat(), OracleChooser(task.oracle))
    assert r1.stop_reason == "solved"
    assert r1.code == r2.code  # determinista
    assert r1.code is not None
    result = run_code(r1.code, task)
    assert result.passed, (r1.code, result.error)


def test_there_are_five_phase5_tasks() -> None:
    assert len(_phase5()) == 5


# -- Criterio de la fase 0, ahora con el motor completo -------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_random_chooser_on_toy_catalog(seed: int) -> None:
    task = SynthTask("lee el fichero y cuenta las líneas", [("path", P("str"))], None, max_steps=4)
    r = synthesize(task, Catalog(TOY_CATALOG), RandomChooser(seed=seed))
    assert r.stop_reason == "solved"
    assert r.code is not None
    compile(ast.parse(r.code), "<synth>", "exec")


# -- Criterio de la fase 4 sobre programas sintetizados ------------------------------


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("task", _phase5(), ids=lambda t: t.id)
def test_every_random_program_compiles(task: EvalTask, seed: int) -> None:
    r = synthesize(
        task.synth_task(), _cat(), RandomChooser(seed=seed), SynthConfig(width=2, max_expansions=60)
    )
    if r.code is not None:
        compile(ast.parse(r.code), "<synth>", "exec")
        compile(ast.parse(r.code.replace("⟨?⟩", "x")), "<synth>", "exec")


def test_mock_chooser_runs_and_compiles() -> None:
    for task in _phase5():
        r = synthesize(task.synth_task(), _cat(), MockChooser(), SynthConfig(max_expansions=60))
        if r.code is not None:
            compile(ast.parse(r.code), "<synth>", "exec")


# -- Búsqueda: retroceso, parada y límites ------------------------------------------


def _mini_catalog() -> Catalog:
    s, b, i = P("str"), P("bytes"), P("int")
    return Catalog(
        (
            Component("toy.encode", (Param("text", s),), b, "Encode text.", kind="function", module="toy"),
            Component("toy.length", (Param("text", s),), i, "Length of text.", kind="function", module="toy"),
        )
    )


class _Prefers:
    """Chooser que prefiere una opción concreta y nunca da por terminada la tarea."""

    def __init__(self, favourite: str) -> None:
        self.favourite = favourite
        self.calls = 0

    def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
        self.calls += 1
        return rank(options, [0.9 if o.id == self.favourite else 0.1 for o in options])

    def is_done(self, state: str) -> float:
        return 0.0


def test_backtracks_out_of_dead_end() -> None:
    # Con un solo paso permitido, elegir encode deja sin forma de devolver un int.
    task = SynthTask("x", [("text", P("str"))], P("int"), max_steps=1)
    r = synthesize(task, _mini_catalog(), _Prefers("toy.encode"), SynthConfig(width=1))
    assert r.stop_reason == "solved"
    assert r.code is not None and "toy.length(text)" in r.code
    assert r.stats.backtracks >= 1


def test_no_solution_reported() -> None:
    task = SynthTask("x", [("n", P("int"))], P("int"), max_steps=2)
    r = synthesize(task, _mini_catalog(), _Prefers("toy.encode"), SynthConfig(width=1))
    # n: int ya es un int: se puede devolver directamente.
    assert r.stop_reason == "solved"
    task2 = SynthTask("x", [("n", P("float"))], P("bytes"), max_steps=2)
    r2 = synthesize(task2, _mini_catalog(), _Prefers("toy.encode"), SynthConfig(width=1))
    assert r2.stop_reason == "no_solution" and r2.code is None


def test_done_threshold_and_step_limit() -> None:
    task = SynthTask("x", [("text", P("str"))], None, max_steps=3)
    always = synthesize(task, _mini_catalog(), MockChooser(done_prob=1.0))
    assert always.stop_reason == "solved"
    assert always.program is not None and len(always.program.body) == 1  # para tras la 1.ª instrucción
    never = synthesize(task, _mini_catalog(), MockChooser(done_prob=0.0))
    assert never.program is not None and len(never.program.body) == 3  # límite duro de pasos


def test_state_is_minimal_and_parseable() -> None:
    seen: list[str] = []

    class Spy(MockChooser):
        def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
            seen.append(state)
            return super().choose(state, options)

    task = _phase5()[0]
    synthesize(task.synth_task(), _cat(), Spy())
    assert seen
    for s in seen:
        t, hole, prog = parse_state(s)
        assert t == task.prompt
        assert hole
        assert "⟨?⟩" in prog  # el hueco actual está marcado en el programa parcial
        assert len(s) < 2000


def test_hierarchical_choice_keeps_queries_small() -> None:
    sizes: list[int] = []

    class Spy(MockChooser):
        def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
            sizes.append(len(options))
            return super().choose(state, options)

    task = _phase5()[0]
    synthesize(task.synth_task(), _cat(), Spy(), SynthConfig(max_options=20))
    assert sizes and max(sizes) <= 20


def test_scores_are_log_probabilities() -> None:
    task = _phase5()[0]
    r = synthesize(task.synth_task(), _cat(), OracleChooser(task.oracle))
    assert r.score <= 0 and math.isfinite(r.score)
    assert r.stats.queries > 0 and r.stats.expansions > 0
