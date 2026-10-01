"""Genera `eval/REPORT.md` a partir de `eval/results/results.json`."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

CATEGORIES = ["ok", "catalogo", "seleccion", "busqueda", "tipos", "emision"]
CAT_TITLES = {
    "ok": "ok",
    "catalogo": "catálogo",
    "seleccion": "selección",
    "busqueda": "búsqueda",
    "tipos": "tipos",
    "emision": "emisión",
}


def _avg(xs: list[float]) -> float:
    return mean(xs) if xs else 0.0


def _row(spec: dict[str, Any]) -> dict[str, Any]:
    outs = spec["outcomes"]
    n = len(outs)
    passed = [o for o in outs if o["passed"]]
    return {
        "name": spec["name"],
        "pass": f"{len(passed)}/{n} ({100 * len(passed) / n:.0f}%)" if n else "-",
        "rate": len(passed) / n if n else 0.0,
        "steps": _avg([o["steps"] for o in passed]),
        "secs": _avg([o["seconds"] for o in outs]),
        "questions": _avg([o["questions"] + o["done_questions"] for o in outs]),
        "requests": _avg([o["requests"] for o in outs]),
        "backtracks": sum(o["backtracks"] for o in outs),
        "low": _avg([o["low_margin"] for o in outs]),
        "cats": Counter(o["category"] for o in outs),
    }


def _table(rows: list[dict[str, Any]]) -> list[str]:
    out = [
        "| configuración | pass@1 | pasos (resueltas) | latencia media (s) | preguntas/tarea "
        "| peticiones/tarea | retrocesos | dudas/tarea |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['name']} | {r['pass']} | {r['steps']:.1f} | {r['secs']:.2f} | {r['questions']:.1f} "
            f"| {r['requests']:.1f} | {r['backtracks']} | {r['low']:.1f} |"
        )
    return out


def _failures(rows: list[dict[str, Any]]) -> list[str]:
    head = "| configuración | " + " | ".join(CAT_TITLES[c] for c in CATEGORIES) + " |"
    out = [head, "|---|" + "---|" * len(CATEGORIES)]
    for r in rows:
        out.append(f"| {r['name']} | " + " | ".join(str(r["cats"].get(c, 0)) for c in CATEGORIES) + " |")
    return out


def write_report(results: Path, report: Path) -> None:
    specs: list[dict[str, Any]] = json.loads(results.read_text())
    by_name = {s["name"]: s for s in specs}
    rows = {s["name"]: _row(s) for s in specs}
    tasks = [o["task"] for o in specs[0]["outcomes"]] if specs else []

    lines = [
        "# Informe de evaluación",
        "",
        "Generado por `python -m jevsynth.eval.run` (no editar a mano; el análisis está en",
        "`jevsynth/eval/analysis.md`).",
        "",
        f"- Tareas: {len(tasks)} (`jevsynth/eval/tasks/*.json`); cada una con tests que se ejecutan",
        "  en un subproceso con timeout y sin red.",
        "- pass@1: el programa de mayor puntuación de la búsqueda pasa todos los tests.",
        "- Pasos: instrucciones insertadas. Preguntas: elecciones + paradas enviadas al chooser.",
        "  Peticiones: llamadas reales (un lote cuenta como una). Dudas: decisiones con",
        "  margen top1 - top2 < 0,1.",
        "- Categorías de fallo: **catálogo** (no hay solución expresable con el catálogo y los",
        "  combinadores: ni el oráculo la tiene), **selección** (había solución y el chooser eligió",
        "  otra cosa que no pasa los tests), **búsqueda** (no se encontró programa completo),",
        "  **tipos** (error de tipos en ejecución), **emisión** (código que no compila).",
        "",
        "## Resultados principales (ancho de haz 3)",
        "",
    ]
    main = [rows[n] for n in rows if n.endswith(" w=3")]
    lines += _table(main)
    lines += ["", "## Ablación (c): ancho de haz", ""]
    lines += _table([rows[n] for n in rows if " w=" in n and n.split(" w=")[1] in {"1", "3", "5"}])
    lines += ["", "## Ablación (a): descripción corta uniforme vs. docstring", ""]
    abl_a = [rows[n] for n in rows if n.endswith(" w=3 doc") or (n.endswith(" w=3") and f"{n} doc" in rows)]
    lines += _table(abl_a) if abl_a else ["(sin datos)"]
    lines += ["", "## Ablación (b): con y sin filtro por tipos", ""]
    abl_b = [
        rows[n] for n in rows if n.endswith(" sin-tipos") or (n.endswith(" w=3") and f"{n} sin-tipos" in rows)
    ]
    lines += _table(abl_b) if abl_b else ["(sin datos)"]
    lines += ["", "## Dónde falla", ""]
    lines += _failures(main + [rows[n] for n in rows if n.endswith(("doc", "sin-tipos"))])
    lines += ["", "## Detalle por tarea (ancho 3)", ""]
    cols = [n for n in rows if n.endswith(" w=3")]
    lines.append("| tarea | " + " | ".join(cols) + " |")
    lines.append("|---|" + "---|" * len(cols))
    for i, t in enumerate(tasks):
        cells = []
        for c in cols:
            o = by_name[c]["outcomes"][i]
            cells.append("✓" if o["passed"] else f"✗ {CAT_TITLES[o['category']]}")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    analysis = Path(__file__).parent / "analysis.md"
    if analysis.exists():
        lines += ["", analysis.read_text().rstrip()]
    report.write_text("\n".join(lines) + "\n")
