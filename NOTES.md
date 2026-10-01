# Notas y hallazgos

## Fase 0

- El bucle es voraz y sin retroceso; el haz y el retroceso llegan en la fase 5.
- Los argumentos se rellenan con la variable compatible más reciente (heurística del
  script). Con varias variables del mismo tipo esto puede ser una decisión real: valorar
  ofrecerla al chooser como `Option(kind="symbol")` en la fase 2.
- `is_done` no se consulta con el programa vacío.
- El casado de tipos es por igualdad de nombre (`TypeRef.name`); subtipos/uniones en fase 2.
