"""Evaluación: ejecuta tareas con distintos choosers y configuraciones.

    python -m jevsynth.eval.run                    # rejilla completa sin Jev
    python -m jevsynth.eval.run --only mock oracle --widths 3
    python -m jevsynth.eval.run --jev              # añade Jev real (TYPESAFE_API_KEY)

Escribe `eval/results/results.json` y regenera `eval/REPORT.md`.
"""

from __future__ import annotations

import argparse
import ast
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from jevsynth.catalog import Catalog, load_stdlib
from jevsynth.chooser import Chooser, MockChooser, NoisyOracleChooser, OracleChooser, RandomChooser
from jevsynth.eval.runner import run_code
from jevsynth.eval.tasks import EvalTask, load_tasks
from jevsynth.synth import SynthConfig, synthesize

EVAL_DIR = Path(__file__).parent
RESULTS = EVAL_DIR / "results" / "results.json"


@dataclass
class TaskOutcome:
    task: str
    passed: bool
    category: str  # ok | catalogo | seleccion | busqueda | emision | tipos
    stop_reason: str
    steps: int
    seconds: float
    chooser_seconds: float
    questions: int
    done_questions: int
    requests: int
    backtracks: int
    expansions: int
    low_margin: int
    error: str = ""
    code: str = ""


@dataclass
class RunSpec:
    name: str
    chooser: str  # random:<seed> | mock | oracle | jev
    width: int = 3
    description: str = "short"
    type_filter: bool = True
    lang: str = "es"  # idioma de la petición (ablación extra)
    outcomes: list[TaskOutcome] = field(default_factory=list)


def make_chooser(kind: str, task: EvalTask) -> Chooser:
    if kind.startswith("random"):
        return RandomChooser(seed=int(kind.split(":")[1]) if ":" in kind else 0)
    if kind == "mock":
        return MockChooser()
    if kind == "oracle":
        return OracleChooser(task.oracle)
    if kind.startswith("noisy"):
        _, acc, *seed = kind.split(":")
        return NoisyOracleChooser(task.oracle, accuracy=float(acc), seed=int(seed[0]) if seed else 0)
    if kind == "jev":
        from jevsynth.chooser.jev import JevChooser

        return JevChooser()
    raise ValueError(kind)


def classify(task: EvalTask, code: str | None, stop: str, passed: bool, error: str) -> str:
    """Dónde falla: catálogo (no hay solución expresable), selección, búsqueda, emisión o tipos."""
    if passed:
        return "ok"
    if code is not None:
        try:
            compile(ast.parse(code), "<synth>", "exec")
        except SyntaxError:
            return "emision"
    if not task.oracle:
        return "catalogo"
    if code is None:
        return "busqueda"
    if error.startswith(("TypeError", "AttributeError")):
        return "tipos"
    return "seleccion"


def run_spec(spec: RunSpec, tasks: list[EvalTask], catalog: Catalog, log: Callable[[str], None]) -> RunSpec:
    config = SynthConfig(width=spec.width, description=spec.description, type_filter=spec.type_filter)  # type: ignore[arg-type]
    for task in tasks:
        chooser = make_chooser(spec.chooser, task)
        t0 = time.perf_counter()
        try:
            r = synthesize(task.synth_task(spec.lang), catalog, chooser, config)
        except Exception as exc:  # un fallo del chooser no debe tumbar la evaluación
            spec.outcomes.append(
                TaskOutcome(task.id, False, "busqueda", "error", 0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, repr(exc))
            )
            continue
        dt = time.perf_counter() - t0
        res = run_code(r.code, task) if r.code is not None else None
        passed = bool(res and res.passed)
        error = res.error if res is not None else r.stop_reason
        spec.outcomes.append(
            TaskOutcome(
                task=task.id,
                passed=passed,
                category=classify(task, r.code, r.stop_reason, passed, error),
                stop_reason=r.stop_reason,
                steps=r.steps,
                seconds=round(dt, 3),
                chooser_seconds=round(r.stats.seconds, 3),
                questions=r.stats.queries,
                done_questions=r.stats.done_queries,
                requests=r.stats.requests,
                backtracks=r.stats.backtracks,
                expansions=r.stats.expansions,
                low_margin=len(r.stats.low_margin()),
                error=error[:200],
                code=r.code or "",
            )
        )
    n = len(spec.outcomes)
    ok = sum(o.passed for o in spec.outcomes)
    log(f"{spec.name:32} pass@1 {ok}/{n}")
    return spec


def default_grid(include_jev: bool) -> list[RunSpec]:
    specs: list[RunSpec] = []
    choosers = ["random:0", "random:1", "random:2", "mock", "noisy:0.9", "noisy:0.75", "oracle"]
    choosers += ["jev"] if include_jev else []
    for ch in choosers:
        for w in (1, 3, 5):
            specs.append(RunSpec(f"{ch} w={w}", ch, width=w))
    # (a) descripción corta uniforme vs. docstring completo
    for ch in ["mock"] + (["jev"] if include_jev else []):
        specs.append(RunSpec(f"{ch} w=3 doc", ch, width=3, description="doc"))
    # (b) sin filtro por tipos
    for ch in ["random:0", "mock", "noisy:0.9", "oracle"] + (["jev"] if include_jev else []):
        specs.append(RunSpec(f"{ch} w=3 sin-tipos", ch, width=3, type_filter=False))
    # (e) idioma de la petición: el catálogo está en inglés y MockChooser es léxico
    for w in (1, 3, 5):
        specs.append(RunSpec(f"mock-en w={w}", "mock", width=w, lang="en"))
    specs.append(RunSpec("mock-en w=3 doc", "mock", width=3, description="doc", lang="en"))
    specs.append(RunSpec("mock-en w=3 sin-tipos", "mock", width=3, type_filter=False, lang="en"))
    if include_jev:
        specs.append(RunSpec("jev-en w=3", "jev", width=3, lang="en"))
    return specs


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jev", action="store_true", help="incluir Jev real")
    ap.add_argument("--only", nargs="*", help="filtrar especificaciones por prefijo de chooser")
    ap.add_argument("--tasks", nargs="*", help="ids de tarea")
    ap.add_argument("--out", type=Path, default=RESULTS)
    args = ap.parse_args(argv)
    catalog = load_stdlib()
    tasks = [t for t in load_tasks() if not args.tasks or t.id in args.tasks]
    specs = default_grid(args.jev)
    if args.only:
        specs = [s for s in specs if any(s.chooser.startswith(o) for o in args.only)]
    # Se fusiona con resultados previos: una ejecución parcial solo reemplaza sus filas.
    previous: list[dict[str, object]] = []
    if args.out.exists() and not args.tasks:
        previous = json.loads(args.out.read_text())
    order = [s.name for s in default_grid(True)]
    merged = {str(d["name"]): d for d in previous}
    for spec in specs:
        run_spec(spec, tasks, catalog, print)
        merged[spec.name] = asdict(spec)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        rows = sorted(
            merged.values(), key=lambda d: order.index(str(d["name"])) if d["name"] in order else 999
        )
        args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
    from jevsynth.eval.report import write_report

    write_report(args.out, EVAL_DIR / "REPORT.md")
    print(f"resultados → {args.out}; informe → {EVAL_DIR / 'REPORT.md'}")


if __name__ == "__main__":
    main()
