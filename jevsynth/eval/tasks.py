"""Tareas de evaluación: `eval/tasks/*.json`.

Formato (superconjunto de `{prompt, tests, max_steps}`):

    {
      "id": "mean_age",
      "prompt": "...",
      "params": [["path", "str"]],      # ausente o null → script
      "returns": "float",               # tipo de retorno de la función
      "tests": ["assert solve('a.csv') == 15.0"],
      "stdout": "...",                  # salida esperada (scripts)
      "files": {"a.csv": "..."},        # ficheros que se crean antes de ejecutar
      "max_steps": 5,
      "oracle": ["control:with", ...]   # decisiones de una solución (chooser oráculo)
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from jevsynth.catalog.model import TypeRef
from jevsynth.synth.engine import SynthTask

TASKS_DIR = Path(__file__).parent / "tasks"


@dataclass
class EvalTask:
    id: str
    prompt: str
    tests: list[str] = field(default_factory=list)
    max_steps: int = 6
    params: list[tuple[str, str]] | None = None
    returns: str | None = None
    stdout: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    oracle: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    prompt_en: str | None = None  # misma petición en inglés (ablación de idioma)

    def synth_task(self, lang: str = "es") -> SynthTask:
        params = [(n, TypeRef.parse(t)) for n, t in self.params] if self.params is not None else None
        returns = TypeRef.parse(self.returns) if self.returns else None
        prompt = self.prompt_en if lang == "en" and self.prompt_en else self.prompt
        return SynthTask(prompt, params, returns, self.max_steps)

    @staticmethod
    def from_json(d: dict[str, object]) -> EvalTask:
        params = d.get("params")
        return EvalTask(
            id=str(d["id"]),
            prompt=str(d["prompt"]),
            tests=[str(t) for t in d.get("tests", [])],  # type: ignore[attr-defined]
            max_steps=int(d.get("max_steps", 6)),  # type: ignore[call-overload]
            params=[(str(n), str(t)) for n, t in params] if isinstance(params, list) else None,
            returns=str(d["returns"]) if d.get("returns") else None,
            stdout=str(d["stdout"]) if d.get("stdout") is not None else None,
            files={str(k): str(v) for k, v in d.get("files", {}).items()},  # type: ignore[attr-defined]
            oracle=[str(x) for x in d.get("oracle", [])],  # type: ignore[attr-defined]
            tags=[str(x) for x in d.get("tags", [])],  # type: ignore[attr-defined]
            prompt_en=str(d["prompt_en"]) if d.get("prompt_en") else None,
        )


def load_tasks(directory: Path = TASKS_DIR) -> list[EvalTask]:
    out: list[EvalTask] = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        items = data if isinstance(data, list) else [data]
        out.extend(EvalTask.from_json(d) for d in items)
    ids = [t.id for t in out]
    if len(ids) != len(set(ids)):
        raise ValueError("ids de tarea duplicados")
    return out
