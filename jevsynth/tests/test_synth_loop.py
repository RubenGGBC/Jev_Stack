import pytest

from jevsynth.catalog.toy import INT, STR, TOY_CATALOG
from jevsynth.chooser import MockChooser, Option, RandomChooser
from jevsynth.scope import Scope, Variable
from jevsynth.synth import build_state, synthesize
from jevsynth.synth.loop import Step, bind_args, fresh_name


def _path_scope() -> Scope:
    return Scope([Variable("path", STR)])


def test_toy_catalog_has_five_functions() -> None:
    assert len(TOY_CATALOG) == 5
    assert len({c.qualname for c in TOY_CATALOG}) == 5


def test_build_state_is_minimal() -> None:
    state = build_state("lee el fichero", "siguiente llamada", [])
    assert state.splitlines() == [
        "tarea: lee el fichero",
        "hueco: siguiente llamada",
        "programa: (vacío)",
    ]


def test_bind_args_uses_most_recent_compatible_var() -> None:
    scope = Scope([Variable("a", STR), Variable("b", STR)])
    to_upper = next(c for c in TOY_CATALOG if c.qualname == "toy.to_upper")
    count = next(c for c in TOY_CATALOG if c.qualname == "toy.count_items")
    assert bind_args(to_upper, scope) == ("b",)
    assert bind_args(count, scope) is None


def test_fresh_name_avoids_collisions() -> None:
    scope = Scope([Variable("text", STR), Variable("text2", STR)])
    assert fresh_name(STR, scope) == "text3"
    assert fresh_name(INT, scope) == "n"


@pytest.mark.parametrize("seed", range(10))
def test_random_chooser_runs_loop_on_toy_catalog(seed: int) -> None:
    result = synthesize(
        "lee el fichero y cuenta las líneas",
        TOY_CATALOG,
        RandomChooser(seed=seed),
        _path_scope(),
        max_steps=5,
    )
    assert result.stop_reason in {"done", "max_steps"}
    assert 1 <= len(result.steps) <= 5
    # Cada paso es type-correct y solo usa variables definidas antes.
    defined = {"path": STR}
    for step in result.steps:
        params = step.component.required_params
        assert len(step.args) == len(params)
        for arg, p in zip(step.args, params, strict=True):
            assert defined[arg] == p.type
        defined[step.out] = step.component.returns
    assert len(result.trace) == len(result.steps)


def test_random_chooser_loop_is_deterministic() -> None:
    def run() -> list[Step]:
        return synthesize("x", TOY_CATALOG, RandomChooser(seed=3), _path_scope()).steps

    assert run() == run()


def test_mock_chooser_follows_task_words() -> None:
    result = synthesize(
        "read the file, split lines, count items",
        TOY_CATALOG,
        MockChooser(),
        _path_scope(),
        max_steps=1,
    )
    assert result.stop_reason == "max_steps"
    assert result.summary() == "text = toy.read_text(path)"


def test_stops_when_done() -> None:
    result = synthesize("x", TOY_CATALOG, MockChooser(done_prob=1.0), _path_scope())
    assert result.stop_reason == "done"
    assert len(result.steps) == 1  # is_done no se consulta con el programa vacío


def test_no_candidates_with_empty_scope() -> None:
    result = synthesize("x", TOY_CATALOG, MockChooser(), Scope())
    assert result.stop_reason == "no_candidates"
    assert result.steps == []


def test_input_scope_is_not_mutated() -> None:
    scope = _path_scope()
    synthesize("x", TOY_CATALOG, RandomChooser(seed=0), scope)
    assert [v.name for v in scope.variables] == ["path"]


class _BadChooser:
    def choose(self, state: str, options: list[Option]) -> list[tuple[Option, float]]:
        return [(Option("evil.rm", "rm", "component"), 1.0)]

    def is_done(self, state: str) -> float:
        return 0.0


def test_rejects_option_outside_candidates() -> None:
    with pytest.raises(ValueError):
        synthesize("x", TOY_CATALOG, _BadChooser(), _path_scope())
