"""Fase 6 con Jev real. Excluido por defecto: `pytest -m jev` (requiere TYPESAFE_API_KEY)."""

import functools
import os

import pytest

from jevsynth.catalog import Catalog, load_stdlib
from jevsynth.eval.runner import run_code
from jevsynth.eval.tasks import EvalTask, load_tasks
from jevsynth.synth import synthesize

pytestmark = [
    pytest.mark.jev,
    pytest.mark.skipif(not os.environ.get("TYPESAFE_API_KEY"), reason="sin TYPESAFE_API_KEY"),
]


@functools.cache
def _cat() -> Catalog:
    return load_stdlib()


@pytest.mark.parametrize("task", [t for t in load_tasks() if "fase5" in t.tags], ids=lambda t: t.id)
def test_jev_solves_phase5_tasks(task: EvalTask) -> None:
    from jevsynth.chooser.jev import JevChooser

    jev = JevChooser()
    try:
        r1 = synthesize(task.synth_task(), _cat(), jev)
        r2 = synthesize(task.synth_task(), _cat(), jev)  # con caché: misma respuesta
    finally:
        jev.close()
    assert r1.stop_reason == "solved"
    assert r1.code == r2.code
    assert r1.code is not None
    result = run_code(r1.code, task)
    assert result.passed, (r1.code, result.error)
