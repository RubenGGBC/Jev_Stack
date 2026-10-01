import functools

import pytest

from jevsynth.catalog import Catalog, load_stdlib
from jevsynth.chooser import OracleChooser
from jevsynth.eval.run import classify
from jevsynth.eval.runner import run_code
from jevsynth.eval.tasks import EvalTask, load_tasks
from jevsynth.synth import synthesize


@functools.cache
def _cat() -> Catalog:
    return load_stdlib()


def test_task_set_size_and_shape() -> None:
    tasks = load_tasks()
    assert 20 <= len(tasks) <= 30
    for t in tasks:
        assert t.prompt and (t.tests or t.stdout is not None)
        assert t.max_steps >= 1


def _task(**kw: object) -> EvalTask:
    return EvalTask(id="t", prompt="p", **kw)  # type: ignore[arg-type]


def test_runner_passes_and_fails() -> None:
    t = _task(tests=["assert solve(2) == 4"])
    assert run_code("def solve(x):\n    return x * 2\n", t).passed
    bad = run_code("def solve(x):\n    return x + 1\n", t)
    assert not bad.passed and "AssertionError" in bad.error


def test_runner_files_and_stdout() -> None:
    t = _task(files={"a.txt": "hola"}, stdout="hola")
    assert run_code("print(open('a.txt').read())\n", t).passed
    assert not run_code("print('adiós')\n", t).passed


def test_runner_blocks_network() -> None:
    t = _task(tests=[])
    code = "import socket\nsocket.create_connection(('example.com', 80))\n"
    r = run_code(code, t)
    assert not r.passed and "red deshabilitada" in r.error


def test_runner_timeout() -> None:
    r = run_code("while True:\n    pass\n", _task(), timeout=1.0)
    assert not r.passed and r.error == "timeout"


def test_classify() -> None:
    with_oracle = _task(oracle=["x"])
    no_oracle = _task()
    assert classify(with_oracle, "x = 1\n", "solved", True, "") == "ok"
    assert classify(with_oracle, "def (:\n", "solved", False, "") == "emision"
    assert classify(no_oracle, "x = 1\n", "solved", False, "AssertionError") == "catalogo"
    assert classify(with_oracle, None, "budget", False, "budget") == "busqueda"
    assert classify(with_oracle, "x = 1\n", "solved", False, "TypeError: bad") == "tipos"
    assert classify(with_oracle, "x = 1\n", "solved", False, "AssertionError") == "seleccion"


@pytest.mark.parametrize("task", [t for t in load_tasks() if t.oracle], ids=lambda t: t.id)
def test_oracle_covers_every_task_with_known_solution(task: EvalTask) -> None:
    r = synthesize(task.synth_task(), _cat(), OracleChooser(task.oracle))
    assert r.code is not None
    res = run_code(r.code, task)
    assert res.passed, (r.code, res.error)


def test_tasks_without_oracle_are_tagged_as_limits() -> None:
    for t in load_tasks():
        if not t.oracle:
            assert any(tag.startswith("limite:") for tag in t.tags), t.id
