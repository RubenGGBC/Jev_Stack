# jevsynth

Síntesis de código por selección: un modelo de decisión (Jev, de TypeSafe AI) **elige**
entre candidatos cerrados y un script determinista **construye** el código. Ningún LLM
genera texto en el bucle. Ver `CLAUDE.md` para el plan y `NOTES.md` para los hallazgos.

```bash
pip install -e '.[dev]'          # añade '.[dev,jev]' para usar Jev real
pytest                           # excluye los tests marcados @pytest.mark.jev
ruff check . && ruff format --check .
mypy jevsynth
```

## Uso

```python
from jevsynth.catalog import load_stdlib, TypeRef
from jevsynth.chooser import MockChooser
from jevsynth.synth import SynthTask, synthesize

task = SynthTask(
    "lee el CSV de la ruta dada y calcula la media de la columna age",
    params=[("path", TypeRef.parse("str"))],
    returns=TypeRef.parse("float"),
    max_steps=6,
)
result = synthesize(task, load_stdlib(), MockChooser())
print(result.code)
```

Con Jev real:

```python
from jevsynth.chooser.jev import JevChooser   # lee TYPESAFE_API_KEY del entorno

result = synthesize(task, load_stdlib(), JevChooser())
```

`JevChooser` acepta `base_url=...`/`api_key=...` (o `TYPESAFE_BASE_URL`), por si el
acceso a Jev pasa por otra pasarela compatible con la API de TypeSafe.

## Piezas

| módulo | qué hace |
|---|---|
| `catalog/` | catálogo de la stdlib desde typeshed + docstrings saneados (`python -m jevsynth.catalog.build`) |
| `scope/` | variables tipadas y casado de tipos (subtipos, uniones, Literal, TypeVar) |
| `candidates/` | componentes rellenables con scope + literales; combinadores de control |
| `literals/` | literales extraídos de la petición (comillas, ficheros, columnas, números) |
| `emit/` | IR del programa parcial → `ast` → `ast.unparse` |
| `synth/` | motor de huecos, elección jerárquica, búsqueda en haz con retroceso y parada |
| `chooser/` | `Chooser` + `MockChooser`, `RandomChooser`, `OracleChooser`, `JevChooser` |
| `eval/` | 30 tareas con tests, runner aislado, métricas, ablaciones y `REPORT.md` |

## Evaluación

```bash
python -m jevsynth.eval.run           # rejilla sin Jev: random, mock, oráculo × ablaciones
python -m jevsynth.eval.run --jev     # añade Jev real
```

Resultados en `jevsynth/eval/results/results.json` e informe en `jevsynth/eval/REPORT.md`.
