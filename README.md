# jevsynth

Síntesis de código por selección: un modelo de decisión (Jev) elige entre candidatos
cerrados y un script determinista construye el código. Ver `CLAUDE.md` para el plan.

```bash
pip install -e '.[dev]'
pytest            # excluye los tests marcados @pytest.mark.jev
ruff check . && ruff format --check .
mypy jevsynth
```
